"""``ReportsService`` (Phase 14) -- built on the real checkout flow, same
reasoning as ``apps.expenses.tests.test_services``, not hand-built totals."""

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from apps.accounts.rbac import ensure_role_groups
from apps.billing.models import Payment
from apps.billing.services.checkout import CompleteSaleService
from apps.inventory.models import Location
from apps.products.models import Category, Product, ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import create_unit
from apps.products.services.serialized_inventory import SerializedInventoryService
from apps.reports.services import ReportsService
from apps.sales.models import Sale, SalesChannel
from apps.sales.services.units import SaleUnitService

User = get_user_model()


class ReportsServiceTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.cashier = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.cashier.groups.add(Group.objects.get(name="Cashier"))

        cls.warehouse = Location.objects.get(code="warehouse")
        cls.category = Category.objects.create(name="Mouse Pads", code="MP")
        cls.product = Product.objects.create(
            name="Pad",
            category=cls.category,
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
        cls.amazon = SalesChannel.objects.get(code="AMAZON")

    def complete_offline_sale(self, purchase_cost=None) -> tuple[Sale, SerializedUnit]:
        unit = create_unit(
            variant=self.variant,
            location=self.warehouse,
            status=SerializedUnit.Status.AVAILABLE,
            purchase_cost=purchase_cost,
        )
        sale = Sale.objects.create(sales_channel=self.offline)
        SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)
        with self.captureOnCommitCallbacks(execute=True):
            CompleteSaleService.complete(
                sale,
                payments=[{"method": Payment.Method.CASH, "amount": Decimal("1180.00")}],
                actor=self.cashier,
            )
        unit.refresh_from_db()
        return sale, unit


class SalesReportTests(ReportsServiceTestBase):
    def test_summary_matches_finance_service(self):
        self.complete_offline_sale(purchase_cost=Decimal("300.00"))
        summary, rows = ReportsService.sales(date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(summary["orders"], 1)
        self.assertEqual(summary["units_sold"], 1)
        self.assertEqual(summary["taxable_sales"], Decimal("1000.00"))
        self.assertEqual(summary["profit"], Decimal("700.00"))
        self.assertEqual(rows, [summary])

    def test_group_by_variant(self):
        self.complete_offline_sale(purchase_cost=Decimal("300.00"))
        _summary, rows = ReportsService.sales(
            date(2026, 1, 1), date(2026, 12, 31), group_by="variant"
        )
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["name"], "HEX-MP-A-001")
        self.assertEqual(row["units_sold"], 1)
        self.assertEqual(row["taxable_sales"], Decimal("1000.00"))
        self.assertEqual(row["gross_profit"], Decimal("700.00"))

    def test_group_by_serial(self):
        sale, unit = self.complete_offline_sale(purchase_cost=Decimal("300.00"))
        _summary, rows = ReportsService.sales(
            date(2026, 1, 1), date(2026, 12, 31), group_by="serial"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["serial_number"], unit.serial_number)
        self.assertEqual(rows[0]["sale_id"], sale.id)
        self.assertEqual(rows[0]["gross_profit"], Decimal("700.00"))

    def test_channel_filter_isolates_the_summary(self):
        self.complete_offline_sale(purchase_cost=Decimal("300.00"))
        summary, _rows = ReportsService.sales(date(2026, 1, 1), date(2026, 12, 31), self.amazon)
        self.assertEqual(summary["orders"], 0)
        self.assertEqual(summary["taxable_sales"], Decimal("0.00"))


class InventoryReportTests(ReportsServiceTestBase):
    def test_current_stock_and_valuation(self):
        create_unit(
            variant=self.variant, location=self.warehouse, status=SerializedUnit.Status.AVAILABLE
        )
        create_unit(
            variant=self.variant, location=self.warehouse, status=SerializedUnit.Status.AVAILABLE
        )
        summary, rows = ReportsService.inventory(location=self.warehouse)
        self.assertEqual(summary["by_status"]["AVAILABLE"], 2)
        self.assertEqual(summary["valuation_available"], Decimal("800.00"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["quantity"], 2)

    def test_location_filter(self):
        amazon_location = Location.objects.get(code="amazon")
        create_unit(
            variant=self.variant, location=self.warehouse, status=SerializedUnit.Status.AVAILABLE
        )
        summary, _rows = ReportsService.inventory(location=amazon_location)
        self.assertEqual(summary.get("by_status", {}), {})


class SerialNumbersReportTests(ReportsServiceTestBase):
    def test_counts_by_status(self):
        create_unit(
            variant=self.variant, location=self.warehouse, status=SerializedUnit.Status.AVAILABLE
        )
        damaged = create_unit(
            variant=self.variant, location=self.warehouse, status=SerializedUnit.Status.AVAILABLE
        )
        SerializedInventoryService.damage(damaged, actor=self.cashier)
        summary, rows = ReportsService.serial_numbers()
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["by_status"]["AVAILABLE"], 1)
        self.assertEqual(summary["by_status"]["DAMAGED"], 1)
        self.assertEqual(len(rows), 2)


class SerialNumberHistoryReportTests(ReportsServiceTestBase):
    def test_history_reflects_the_sale_lifecycle(self):
        _sale, unit = self.complete_offline_sale(purchase_cost=Decimal("300.00"))
        summary, rows = ReportsService.serial_number_history(unit)
        self.assertEqual(summary["serial_number"], unit.serial_number)
        self.assertEqual(summary["current_status"], SerializedUnit.Status.SOLD)
        statuses = [row["new_status"] for row in rows]
        self.assertIn(SerializedUnit.Status.SOLD, statuses)


class ProductsReportTests(ReportsServiceTestBase):
    def test_sold_and_never_sold_products(self):
        self.complete_offline_sale(purchase_cost=Decimal("300.00"))
        unsold_product = Product.objects.create(
            name="Coaster",
            category=self.category,
            status=Product.Status.ACTIVE,
        )
        ProductVariant.objects.create(product=unsold_product, sku="HEX-CO-A-001", code="A")

        summary, rows = ReportsService.products(date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(summary["products_sold"], 1)
        self.assertEqual(summary["products_never_sold"], 1)
        sold_row = next(r for r in rows if r["sku"] == "HEX-MP-A-001")
        self.assertEqual(sold_row["units_sold"], 1)
        self.assertEqual(sold_row["gross_profit"], Decimal("700.00"))


class FinancialReportTests(ReportsServiceTestBase):
    def test_summary_includes_outstanding_amount(self):
        sale, _unit = self.complete_offline_sale(purchase_cost=Decimal("300.00"))
        summary, rows = ReportsService.financial(date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(summary["net_profit"], Decimal("700.00"))
        self.assertEqual(summary["outstanding_amount"], Decimal("0.00"))
        codes = {row["channel"] for row in rows}
        self.assertEqual(codes, {"AMAZON", "OFFLINE"})

    def test_outstanding_amount_for_a_partially_paid_sale(self):
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
                payments=[{"method": Payment.Method.CASH, "amount": Decimal("500.00")}],
                actor=self.cashier,
            )
        summary, _rows = ReportsService.financial(
            date(2026, 1, 1), date(2026, 12, 31), self.offline
        )
        self.assertEqual(summary["outstanding_amount"], Decimal("680.00"))
