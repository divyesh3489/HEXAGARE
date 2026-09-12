"""Dashboard widget-group API (Phase 16) -- RBAC per group + response shape."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.rbac import ensure_role_groups
from apps.billing.models import Payment
from apps.billing.services.checkout import CompleteSaleService
from apps.inventory.models import Location
from apps.products.models import Category, Product, ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import create_unit
from apps.sales.models import Sale, SalesChannel
from apps.sales.services.units import SaleUnitService

User = get_user_model()


class DashboardApiTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.admin = User.objects.create_user("admin@hexagare.test", "pw-Testing-123")
        cls.admin.groups.add(Group.objects.get(name="Admin"))
        cls.cashier = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.cashier.groups.add(Group.objects.get(name="Cashier"))
        cls.warehouse_user = User.objects.create_user("warehouse@hexagare.test", "pw-Testing-123")
        cls.warehouse_user.groups.add(Group.objects.get(name="Warehouse"))

        cls.warehouse = Location.objects.get(code="warehouse")
        category = Category.objects.create(name="Mouse Pads", code="MP")
        cls.product = Product.objects.create(
            name="Pad",
            category=category,
            status=Product.Status.ACTIVE,
            mrp=Decimal("1180.00"),
            selling_price=Decimal("1180.00"),
            purchase_price=Decimal("400.00"),
            tax_rate=Decimal("18.00"),
        )
        cls.variant = ProductVariant.objects.create(
            product=cls.product, sku="HEX-MP-A-001", code="A"
        )
        cls.offline = SalesChannel.objects.get(code="OFFLINE")

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def complete_offline_sale(self):
        unit = create_unit(
            variant=self.variant,
            location=self.warehouse,
            status=SerializedUnit.Status.AVAILABLE,
            purchase_cost=Decimal("300.00"),
        )
        sale = Sale.objects.create(sales_channel=self.offline)
        SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)
        with self.captureOnCommitCallbacks(execute=True):
            CompleteSaleService.complete(
                sale,
                payments=[{"method": Payment.Method.CASH, "amount": Decimal("1180.00")}],
                actor=self.cashier,
            )
        return sale, unit


class RbacTests(DashboardApiTestBase):
    """Sales/Inventory gate on the same view permission Cashier/Warehouse
    already hold; Finance/Analytics stay Admin/Manager-only."""

    def test_cashier_can_view_sales_and_inventory(self):
        client = self.client_for(self.cashier)
        self.assertEqual(client.get("/api/v1/reports/dashboard/sales/").status_code, 200)
        self.assertEqual(client.get("/api/v1/reports/dashboard/inventory/").status_code, 200)

    def test_cashier_cannot_view_finance_or_analytics(self):
        client = self.client_for(self.cashier)
        self.assertEqual(client.get("/api/v1/reports/dashboard/finance/").status_code, 403)
        self.assertEqual(client.get("/api/v1/reports/dashboard/analytics/").status_code, 403)

    def test_warehouse_can_view_inventory_not_sales_or_finance(self):
        client = self.client_for(self.warehouse_user)
        self.assertEqual(client.get("/api/v1/reports/dashboard/inventory/").status_code, 200)
        self.assertEqual(client.get("/api/v1/reports/dashboard/sales/").status_code, 403)
        self.assertEqual(client.get("/api/v1/reports/dashboard/finance/").status_code, 403)

    def test_admin_can_view_every_group(self):
        client = self.client_for(self.admin)
        for group in ("sales", "inventory", "finance", "analytics"):
            with self.subTest(group=group):
                res = client.get(f"/api/v1/reports/dashboard/{group}/")
                self.assertEqual(res.status_code, 200, res.data)


class SalesWidgetTests(DashboardApiTestBase):
    def test_reflects_a_completed_sale(self):
        self.complete_offline_sale()
        res = self.client_for(self.admin).get("/api/v1/reports/dashboard/sales/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(Decimal(res.data["total_sales"]), Decimal("1180.00"))
        self.assertEqual(Decimal(res.data["by_channel"]["OFFLINE"]), Decimal("1180.00"))
        self.assertEqual(res.data["total_orders"], 1)
        self.assertEqual(res.data["units_sold"], 1)


class InventoryWidgetTests(DashboardApiTestBase):
    def test_counts_by_status(self):
        create_unit(
            variant=self.variant, location=self.warehouse, status=SerializedUnit.Status.AVAILABLE
        )
        res = self.client_for(self.admin).get("/api/v1/reports/dashboard/inventory/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["available_units"], 1)
        self.assertEqual(res.data["total_serialized_units"], 1)


class FinanceWidgetTests(DashboardApiTestBase):
    def test_defaults_to_current_month(self):
        res = self.client_for(self.admin).get("/api/v1/reports/dashboard/finance/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIn("net_profit", res.data)

    def test_accepts_an_explicit_range(self):
        self.complete_offline_sale()
        res = self.client_for(self.admin).get(
            "/api/v1/reports/dashboard/finance/?date_from=2026-01-01&date_to=2026-12-31"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertGreater(Decimal(res.data["revenue"]), Decimal("0"))


class AnalyticsWidgetTests(DashboardApiTestBase):
    def test_includes_the_completed_sale_in_recent_orders_and_the_trend(self):
        self.complete_offline_sale()
        res = self.client_for(self.admin).get("/api/v1/reports/dashboard/analytics/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(len(res.data["recent_orders"]), 1)
        self.assertEqual(res.data["recent_orders"][0]["channel"], "OFFLINE")
        total_trend = sum(Decimal(row["total"]) for row in res.data["sales_graph"])
        self.assertEqual(total_trend, Decimal("1180.00"))
