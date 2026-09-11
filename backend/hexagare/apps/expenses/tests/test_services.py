"""``FinanceService`` (Phase 13) -- built on real checkout / Amazon-import
flows (same reasoning as apps.customers.tests.test_services), not hand-built
totals, so a change to how Sale/AmazonOrderSettlement totals are computed
gets caught here too."""

import io
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from apps.accounts.rbac import ensure_role_groups
from apps.billing.models import Payment
from apps.billing.services.checkout import CompleteSaleService
from apps.expenses.models import Expense
from apps.expenses.services import FinanceService
from apps.integrations.amazon.models import AmazonImportBatch
from apps.integrations.amazon.services.importer import AmazonOrderImportService
from apps.integrations.amazon.sources import CSVAmazonOrderSource
from apps.inventory.models import Location
from apps.products.models import Category, Product, ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import create_unit
from apps.sales.models import Sale, SalesChannel
from apps.sales.services.units import SaleUnitService

User = get_user_model()

AMAZON_CSV_HEADER = (
    "order_id,order_date,order_status,amazon_sku,quantity,selling_price,gst_amount,"
    "referral_fee,closing_fee,fulfillment_fee,shipping_cost,advertising_cost,other_charges,"
    "refund_amount"
)


class FinanceServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.cashier = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.cashier.groups.add(Group.objects.get(name="Cashier"))

        cls.warehouse = Location.objects.get(code="warehouse")
        cls.amazon_location = Location.objects.get(code="amazon")
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

    def import_amazon_order(self) -> tuple[Sale, SerializedUnit]:
        create_unit(
            variant=self.variant,
            location=self.amazon_location,
            status=SerializedUnit.Status.AVAILABLE,
        )
        row = (
            f"AMZ-1,2026-01-10,Shipped,{self.variant.sku},1,1180.00,180.00,150.00,20.00,80.00,"
            "80.00,50.00,10.00,0.00"
        )
        csv_text = AMAZON_CSV_HEADER + "\n" + row + "\n"
        batch = AmazonImportBatch.objects.create()
        AmazonOrderImportService.run(batch, CSVAmazonOrderSource(io.StringIO(csv_text)))
        sale = Sale.objects.get(sales_channel=self.amazon, external_reference="AMZ-1")
        unit = SerializedUnit.objects.get(sale_line_unit__sale_line__sale=sale)
        return sale, unit

    def test_offline_sale_uses_the_units_own_purchase_cost(self):
        self.complete_offline_sale(purchase_cost=Decimal("300.00"))
        summary = FinanceService.summary(date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(summary["taxable_sales"], Decimal("1000.00"))
        self.assertEqual(summary["gst_collected"], Decimal("180.00"))
        self.assertEqual(summary["product_cost"], Decimal("300.00"))
        self.assertEqual(summary["gross_profit"], Decimal("700.00"))
        self.assertEqual(summary["net_profit"], Decimal("700.00"))

    def test_offline_sale_falls_back_to_effective_purchase_price(self):
        self.complete_offline_sale(purchase_cost=None)
        summary = FinanceService.summary(date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(summary["product_cost"], Decimal("400.00"))

    def test_expenses_reduce_net_profit_by_bucket(self):
        self.complete_offline_sale(purchase_cost=Decimal("300.00"))
        Expense.objects.create(
            category=Expense.Category.PACKAGING,
            amount=Decimal("50.00"),
            expense_date=date(2026, 1, 10),
        )
        Expense.objects.create(
            category=Expense.Category.COURIER,
            amount=Decimal("30.00"),
            expense_date=date(2026, 1, 10),
        )
        summary = FinanceService.summary(date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(summary["packaging"], Decimal("50.00"))
        self.assertEqual(summary["shipping"], Decimal("30.00"))
        self.assertEqual(summary["gross_profit"], Decimal("700.00"))
        self.assertEqual(summary["net_profit"], Decimal("620.00"))

    def test_expense_outside_date_range_is_excluded(self):
        self.complete_offline_sale(purchase_cost=Decimal("300.00"))
        Expense.objects.create(
            category=Expense.Category.PACKAGING,
            amount=Decimal("50.00"),
            expense_date=date(2026, 3, 1),
        )
        summary = FinanceService.summary(date(2026, 1, 1), date(2026, 1, 31))
        self.assertEqual(summary["packaging"], Decimal("0.00"))

    def test_channel_filter_isolates_the_summary(self):
        self.complete_offline_sale(purchase_cost=Decimal("300.00"))
        summary = FinanceService.summary(date(2026, 1, 1), date(2026, 12, 31), self.amazon)
        self.assertEqual(summary["taxable_sales"], Decimal("0.00"))
        self.assertEqual(summary["channel"], "AMAZON")

    def test_draft_and_cancelled_sales_are_excluded(self):
        Sale.objects.create(sales_channel=self.offline)  # DRAFT
        summary = FinanceService.summary(date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(summary["gross_sales"], Decimal("0.00"))

    def test_amazon_settlement_fees_flow_into_the_amazon_channel_summary(self):
        self.import_amazon_order()
        summary = FinanceService.summary(date(2026, 1, 1), date(2026, 12, 31), self.amazon)
        # referral 150 + closing 20 + fulfillment 80
        self.assertEqual(summary["amazon_fees"], Decimal("250.00"))
        self.assertEqual(summary["shipping"], Decimal("80.00"))
        self.assertEqual(summary["advertising"], Decimal("50.00"))
        self.assertEqual(summary["other_expenses"], Decimal("10.00"))
        self.assertEqual(summary["taxable_sales"], Decimal("1000.00"))
        # 400 product cost (effective_purchase_price, no per-unit cost from Phase 12
        # for an Amazon-imported unit) -- net = 1000 - 400 - 250 - 80 - 50 - 10 = 210
        self.assertEqual(summary["net_profit"], Decimal("210.00"))

    def test_unit_profit_for_an_amazon_sold_unit(self):
        _, unit = self.import_amazon_order()
        profit = FinanceService.unit_profit(unit)
        self.assertEqual(profit["sales_channel"], "AMAZON")
        self.assertEqual(profit["purchase_cost"], Decimal("400.00"))
        self.assertEqual(profit["taxable_selling_value"], Decimal("1000.00"))
        self.assertEqual(profit["amazon_fees"], Decimal("250.00"))
        self.assertEqual(profit["courier"], Decimal("80.00"))
        self.assertEqual(profit["advertising"], Decimal("50.00"))
        self.assertEqual(profit["other_charges"], Decimal("10.00"))
        self.assertEqual(profit["unit_profit"], Decimal("210.00"))

    def test_unit_profit_for_an_offline_sold_unit_has_no_amazon_fees(self):
        _, unit = self.complete_offline_sale(purchase_cost=Decimal("300.00"))
        profit = FinanceService.unit_profit(unit)
        self.assertEqual(profit["sales_channel"], "OFFLINE")
        self.assertEqual(profit["purchase_cost"], Decimal("300.00"))
        self.assertEqual(profit["taxable_selling_value"], Decimal("1000.00"))
        self.assertEqual(profit["amazon_fees"], Decimal("0.00"))
        self.assertEqual(profit["unit_profit"], Decimal("700.00"))

    def test_unit_profit_rejects_a_unit_that_was_never_sold(self):
        from rest_framework.exceptions import ValidationError

        unit = create_unit(
            variant=self.variant, location=self.warehouse, status=SerializedUnit.Status.AVAILABLE
        )
        with self.assertRaises(ValidationError):
            FinanceService.unit_profit(unit)

    def test_refunds_are_reported_but_not_subtracted_from_net_profit(self):
        from apps.billing.services.returns import ReturnService

        sale, unit = self.complete_offline_sale(purchase_cost=Decimal("300.00"))
        ReturnService.create(
            entries=[{"code": unit.serial_number, "refund_amount": Decimal("1180.00")}],
            reason="Changed mind",
            refund_method=Payment.Method.CASH,
            actor=self.cashier,
        )
        summary = FinanceService.summary(date(2026, 1, 1), date(2026, 12, 31))
        self.assertEqual(summary["refunds"], Decimal("1180.00"))
        self.assertEqual(summary["net_profit"], Decimal("700.00"))
