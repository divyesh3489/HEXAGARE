"""Suppliers API (Phase 12) -- CRUD, RBAC, delete-guard, aggregates."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.rbac import ensure_role_groups
from apps.purchases.models import PurchaseOrder, PurchaseOrderPayment
from apps.suppliers.models import Supplier

User = get_user_model()


class SuppliersApiTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.manager = User.objects.create_user("manager@hexagare.test", "pw-Testing-123")
        cls.manager.groups.add(Group.objects.get(name="Manager"))
        cls.warehouse_user = User.objects.create_user("wh@hexagare.test", "pw-Testing-123")
        cls.warehouse_user.groups.add(Group.objects.get(name="Warehouse"))
        cls.cashier = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.cashier.groups.add(Group.objects.get(name="Cashier"))

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client


class RbacTests(SuppliersApiTestBase):
    def test_warehouse_can_view_but_not_manage_suppliers(self):
        res = self.client_for(self.warehouse_user).get("/api/v1/suppliers/")
        self.assertEqual(res.status_code, 200)
        res = self.client_for(self.warehouse_user).post(
            "/api/v1/suppliers/", {"name": "Acme Supplies"}, format="json"
        )
        self.assertEqual(res.status_code, 403)

    def test_cashier_cannot_view_suppliers(self):
        res = self.client_for(self.cashier).get("/api/v1/suppliers/")
        self.assertEqual(res.status_code, 403)

    def test_manager_can_view_and_manage(self):
        res = self.client_for(self.manager).post(
            "/api/v1/suppliers/", {"name": "Acme Supplies"}, format="json"
        )
        self.assertEqual(res.status_code, 201, res.data)


class CreateUpdateTests(SuppliersApiTestBase):
    def test_create_supplier_with_full_fields(self):
        res = self.client_for(self.manager).post(
            "/api/v1/suppliers/",
            {
                "name": "Acme Supplies",
                "company": "Acme Pvt Ltd",
                "phone": "+91-98765-00000",
                "email": "acme@example.com",
                "address": "1 Industrial Area",
                "gstin": "27AAAAA0000A1Z5",
                "payment_terms": "Net 30",
                "notes": "Preferred vendor",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["name"], "Acme Supplies")
        self.assertEqual(res.data["payment_terms"], "Net 30")
        self.assertEqual(res.data["total_purchase_value"], Decimal("0.00"))

    def test_search_by_phone(self):
        Supplier.objects.create(name="Acme", phone="9998887770")
        Supplier.objects.create(name="Other", phone="1112223334")
        res = self.client_for(self.manager).get("/api/v1/suppliers/?search=9998887770")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data["data"]), 1)
        self.assertEqual(res.data["data"][0]["name"], "Acme")

    def test_update_full_profile(self):
        supplier = Supplier.objects.create(name="Acme")
        res = self.client_for(self.manager).patch(
            f"/api/v1/suppliers/{supplier.id}/", {"gstin": "27AAAAA0000A1Z5"}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["gstin"], "27AAAAA0000A1Z5")


class DeleteGuardTests(SuppliersApiTestBase):
    def test_delete_blocked_with_purchase_history(self):
        supplier = Supplier.objects.create(name="Acme")
        PurchaseOrder.objects.create(supplier=supplier, status=PurchaseOrder.Status.ORDERED)
        res = self.client_for(self.manager).delete(f"/api/v1/suppliers/{supplier.id}/")
        self.assertEqual(res.status_code, 400)

    def test_delete_allowed_without_history(self):
        supplier = Supplier.objects.create(name="Acme")
        res = self.client_for(self.manager).delete(f"/api/v1/suppliers/{supplier.id}/")
        self.assertEqual(res.status_code, 204)


class AggregateTests(SuppliersApiTestBase):
    def test_totals_exclude_draft_and_cancelled(self):
        supplier = Supplier.objects.create(name="Acme")
        PurchaseOrder.objects.create(
            supplier=supplier, status=PurchaseOrder.Status.DRAFT, grand_total=Decimal("500.00")
        )
        PurchaseOrder.objects.create(
            supplier=supplier,
            status=PurchaseOrder.Status.CANCELLED,
            grand_total=Decimal("300.00"),
        )
        ordered = PurchaseOrder.objects.create(
            supplier=supplier, status=PurchaseOrder.Status.ORDERED, grand_total=Decimal("1000.00")
        )
        PurchaseOrderPayment.objects.create(
            purchase_order=ordered,
            method=PurchaseOrderPayment.Method.BANK_TRANSFER,
            amount=Decimal("400.00"),
        )

        res = self.client_for(self.manager).get(f"/api/v1/suppliers/{supplier.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["total_purchase_value"], Decimal("1000.00"))
        self.assertEqual(res.data["total_paid"], Decimal("400.00"))
        self.assertEqual(res.data["outstanding_amount"], Decimal("600.00"))
        # Order history lists every order regardless of status (same as
        # CustomerDetailSerializer.get_sales) -- the aggregates above are
        # what excludes DRAFT/CANCELLED.
        self.assertEqual(len(res.data["orders"]), 3)
