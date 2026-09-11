"""SalesTotalsService -- the only writer of a Sale's derived totals."""

from decimal import Decimal

from django.test import TestCase

from apps.products.models import Category, Product, ProductVariant
from apps.sales.models import Sale, SaleLine, SalesChannel
from apps.sales.services.totals import SalesTotalsService


class TotalsTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name="Mouse Pads", code="MP")
        product = Product.objects.create(
            name="Pad",
            category=category,
            status=Product.Status.ACTIVE,
            mrp=Decimal("1180.00"),
            selling_price=Decimal("1180.00"),
            tax_rate=Decimal("18.00"),
        )
        cls.variant = ProductVariant.objects.create(
            product=product, sku="HEX-MP-A-001", code="A"
        )
        cls.channel = SalesChannel.objects.get(code="OFFLINE")

    def make_sale(self) -> Sale:
        return Sale.objects.create(sales_channel=self.channel)


class RecalculateTests(TotalsTestBase):
    def test_recalculate_sums_taxable_value_discount_and_tax_from_lines(self):
        sale = self.make_sale()
        # unit_price 1180 (GST-inclusive, 18%) x 2 = 2360 gross, no discount.
        SaleLine.objects.create(
            sale=sale, variant=self.variant, quantity=2, unit_price=Decimal("1180.00"),
            tax_rate=Decimal("18.00"),
        )
        sale = SalesTotalsService.recalculate(sale)

        self.assertEqual(sale.subtotal, Decimal("2000.00"))
        self.assertEqual(sale.tax_total, Decimal("360.00"))
        self.assertEqual(sale.discount_total, Decimal("0.00"))
        self.assertEqual(sale.grand_total, Decimal("2360.00"))

    def test_recalculate_applies_per_line_discount_before_deriving_tax(self):
        sale = self.make_sale()
        # gross 1180, discount 180 -> net 1000, taxable ~847.46, tax ~152.54.
        SaleLine.objects.create(
            sale=sale, variant=self.variant, quantity=1, unit_price=Decimal("1180.00"),
            tax_rate=Decimal("18.00"), discount_amount=Decimal("180.00"),
        )
        sale = SalesTotalsService.recalculate(sale)

        self.assertEqual(sale.discount_total, Decimal("180.00"))
        self.assertEqual(sale.grand_total, Decimal("1000.00"))
        self.assertEqual(sale.subtotal + sale.tax_total, sale.grand_total)

    def test_recalculate_sums_multiple_lines(self):
        sale = self.make_sale()
        SaleLine.objects.create(
            sale=sale, variant=self.variant, quantity=1, unit_price=Decimal("1180.00"),
            tax_rate=Decimal("18.00"),
        )
        SaleLine.objects.create(
            sale=sale, variant=self.variant, quantity=3, unit_price=Decimal("1180.00"),
            tax_rate=Decimal("18.00"),
        )
        sale = SalesTotalsService.recalculate(sale)

        self.assertEqual(sale.grand_total, Decimal("4720.00"))

    def test_recalculate_with_no_lines_zeroes_out_totals(self):
        sale = self.make_sale()
        sale.subtotal = Decimal("100.00")
        sale.grand_total = Decimal("118.00")
        sale.save()

        sale = SalesTotalsService.recalculate(sale)

        self.assertEqual(sale.subtotal, Decimal("0.00"))
        self.assertEqual(sale.grand_total, Decimal("0.00"))

    def test_a_zero_tax_rate_line_has_no_tax(self):
        sale = self.make_sale()
        SaleLine.objects.create(
            sale=sale, variant=self.variant, quantity=1, unit_price=Decimal("500.00"),
            tax_rate=Decimal("0.00"),
        )
        sale = SalesTotalsService.recalculate(sale)

        self.assertEqual(sale.tax_total, Decimal("0.00"))
        self.assertEqual(sale.subtotal, Decimal("500.00"))
