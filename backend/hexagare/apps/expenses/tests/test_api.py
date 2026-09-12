"""Expenses + finance API (Phase 13) -- CRUD, RBAC, finance endpoints."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.rbac import ensure_role_groups
from apps.expenses.models import Expense
from apps.sales.models import SalesChannel

User = get_user_model()


class ExpensesApiTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.manager = User.objects.create_user("manager@hexagare.test", "pw-Testing-123")
        cls.manager.groups.add(Group.objects.get(name="Manager"))
        cls.cashier = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.cashier.groups.add(Group.objects.get(name="Cashier"))
        cls.warehouse = User.objects.create_user("wh@hexagare.test", "pw-Testing-123")
        cls.warehouse.groups.add(Group.objects.get(name="Warehouse"))
        cls.offline = SalesChannel.objects.get(code="OFFLINE")

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client


class RbacTests(ExpensesApiTestBase):
    def test_cashier_cannot_view_expenses(self):
        res = self.client_for(self.cashier).get("/api/v1/expenses/")
        self.assertEqual(res.status_code, 403)

    def test_warehouse_cannot_view_finance_summary(self):
        res = self.client_for(self.warehouse).get(
            "/api/v1/expenses/finance/summary/?date_from=2026-01-01&date_to=2026-01-31"
        )
        self.assertEqual(res.status_code, 403)

    def test_manager_can_manage_expenses_and_view_finance(self):
        res = self.client_for(self.manager).get("/api/v1/expenses/")
        self.assertEqual(res.status_code, 200)
        res = self.client_for(self.manager).get(
            "/api/v1/expenses/finance/summary/?date_from=2026-01-01&date_to=2026-01-31"
        )
        self.assertEqual(res.status_code, 200)


class ExpenseCrudTests(ExpensesApiTestBase):
    def test_create_expense(self):
        res = self.client_for(self.manager).post(
            "/api/v1/expenses/",
            {
                "category": Expense.Category.PACKAGING,
                "amount": "250.00",
                "expense_date": "2026-01-15",
                "note": "Bubble wrap rolls",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["category"], "PACKAGING")
        self.assertEqual(res.data["category_display"], "Packaging")
        self.assertIsNone(res.data["sales_channel"])
        self.assertEqual(res.data["created_by_email"], "manager@hexagare.test")

    def test_channel_scoped_expense(self):
        res = self.client_for(self.manager).post(
            "/api/v1/expenses/",
            {
                "category": Expense.Category.ADVERTISING,
                "sales_channel": self.offline.id,
                "amount": "1000.00",
                "expense_date": "2026-01-15",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["sales_channel_code"], "OFFLINE")

    def test_amount_must_be_positive(self):
        res = self.client_for(self.manager).post(
            "/api/v1/expenses/",
            {"category": Expense.Category.OTHER, "amount": "0.00", "expense_date": "2026-01-15"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_list_can_be_filtered_by_category_and_date_range(self):
        Expense.objects.create(
            category=Expense.Category.SHIPPING,
            amount=Decimal("100.00"),
            expense_date=date(2026, 1, 5),
        )
        Expense.objects.create(
            category=Expense.Category.PACKAGING,
            amount=Decimal("50.00"),
            expense_date=date(2026, 2, 5),
        )
        res = self.client_for(self.manager).get(
            "/api/v1/expenses/?category=SHIPPING&date_from=2026-01-01&date_to=2026-01-31"
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["meta"]["count"], 1)

    def test_update_and_delete(self):
        expense = Expense.objects.create(
            category=Expense.Category.OTHER, amount=Decimal("10.00"), expense_date=date(2026, 1, 1)
        )
        res = self.client_for(self.manager).patch(
            f"/api/v1/expenses/{expense.id}/", {"amount": "20.00"}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["amount"], "20.00")

        res = self.client_for(self.manager).delete(f"/api/v1/expenses/{expense.id}/")
        self.assertEqual(res.status_code, 204)


class FinanceEndpointTests(ExpensesApiTestBase):
    def test_summary_requires_date_range(self):
        res = self.client_for(self.manager).get("/api/v1/expenses/finance/summary/")
        self.assertEqual(res.status_code, 400)

    def test_summary_rejects_reversed_date_range(self):
        res = self.client_for(self.manager).get(
            "/api/v1/expenses/finance/summary/?date_from=2026-02-01&date_to=2026-01-01"
        )
        self.assertEqual(res.status_code, 400)

    def test_summary_rejects_unknown_channel(self):
        res = self.client_for(self.manager).get(
            "/api/v1/expenses/finance/summary/"
            "?date_from=2026-01-01&date_to=2026-01-31&channel=FLIPKART"
        )
        self.assertEqual(res.status_code, 400)

    def test_by_channel_returns_one_row_per_active_channel(self):
        res = self.client_for(self.manager).get(
            "/api/v1/expenses/finance/by-channel/?date_from=2026-01-01&date_to=2026-01-31"
        )
        self.assertEqual(res.status_code, 200)
        codes = {row["channel"] for row in res.data}
        self.assertEqual(codes, {"AMAZON", "OFFLINE"})

    def test_unit_profit_404s_for_an_unknown_unit(self):
        res = self.client_for(self.manager).get("/api/v1/expenses/finance/units/999999/profit/")
        self.assertEqual(res.status_code, 404)
