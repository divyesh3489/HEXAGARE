"""Purchase-history aggregates (Phase 11) -- built on a real
checkout + return flow (same services Phases 8/10 use), not hand-built
totals, so a change to how ``grand_total``/``refund_total`` are computed
gets caught here too."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase

from apps.accounts.rbac import ensure_role_groups
from apps.billing.models import Payment
from apps.billing.services.checkout import CompleteSaleService
from apps.billing.services.returns import ReturnService
from apps.customers import services
from apps.customers.models import Customer
from apps.inventory.models import Location
from apps.products.models import Category, Product, ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import create_unit
from apps.sales.models import Sale, SalesChannel
from apps.sales.services.units import SaleUnitService

User = get_user_model()


class AggregateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.cashier = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.cashier.groups.add(Group.objects.get(name="Cashier"))

        cls.warehouse = Location.objects.get(code="warehouse")
        category = Category.objects.create(name="Mouse Pads", code="MP")
        cls.product = Product.objects.create(
            name="Pad",
            category=category,
            status=Product.Status.ACTIVE,
            mrp=Decimal("1180.00"),
            selling_price=Decimal("1180.00"),
            tax_rate=Decimal("18.00"),
        )
        cls.variant = ProductVariant.objects.create(
            product=cls.product, sku="HEX-MP-A-001", code="A"
        )
        cls.offline = SalesChannel.objects.get(code="OFFLINE")
        cls.customer = Customer.objects.create(name="Rahul Sharma")

    def make_unit(self):
        return create_unit(
            variant=self.variant, location=self.warehouse, status=SerializedUnit.Status.AVAILABLE
        )

    def test_total_purchases_sums_completed_sale_grand_totals(self):
        sale = Sale.objects.create(sales_channel=self.offline, customer=self.customer)
        unit = self.make_unit()
        SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)
        with self.captureOnCommitCallbacks(execute=True):
            CompleteSaleService.complete(
                sale,
                payments=[{"method": Payment.Method.CASH, "amount": Decimal("1180.00")}],
                actor=self.cashier,
            )

        self.assertEqual(services.total_purchases(self.customer), Decimal("1180.00"))
        self.assertEqual(services.outstanding_amount(self.customer), Decimal("0.00"))

    def test_draft_sales_do_not_count_toward_purchases(self):
        Sale.objects.create(sales_channel=self.offline, customer=self.customer)
        self.assertEqual(services.total_purchases(self.customer), Decimal("0.00"))

    def test_outstanding_amount_reflects_a_held_bill(self):
        sale = Sale.objects.create(sales_channel=self.offline, customer=self.customer)
        unit = self.make_unit()
        SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)
        CompleteSaleService.complete(
            sale,
            payments=[{"method": Payment.Method.CASH, "amount": Decimal("500.00")}],
            actor=self.cashier,
        )
        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.RESERVED)
        self.assertEqual(services.outstanding_amount(self.customer), Decimal("680.00"))

    def test_total_refunds_sums_returns_on_the_customers_sales(self):
        sale = Sale.objects.create(sales_channel=self.offline, customer=self.customer)
        unit = self.make_unit()
        SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)
        with self.captureOnCommitCallbacks(execute=True):
            CompleteSaleService.complete(
                sale,
                payments=[{"method": Payment.Method.CASH, "amount": Decimal("1180.00")}],
                actor=self.cashier,
            )

        ReturnService.create(
            entries=[{"code": unit.serial_number, "refund_amount": Decimal("1180.00")}],
            reason="Changed mind",
            refund_method=Payment.Method.CASH,
            actor=self.cashier,
        )

        self.assertEqual(services.total_refunds(self.customer), Decimal("1180.00"))
        serials = list(services.serial_number_history(self.customer))
        self.assertEqual([u.pk for u in serials], [unit.pk])

    def test_a_customer_with_no_sales_has_zeroed_aggregates(self):
        lonely = Customer.objects.create(name="Nobody")
        self.assertEqual(services.total_purchases(lonely), Decimal("0.00"))
        self.assertEqual(services.total_refunds(lonely), Decimal("0.00"))
        self.assertEqual(services.outstanding_amount(lonely), Decimal("0.00"))
        self.assertEqual(list(services.serial_number_history(lonely)), [])
