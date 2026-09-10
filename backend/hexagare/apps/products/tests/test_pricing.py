"""GST-inclusive pricing + inheritance + discount on ``ProductVariant``
(HEXAGARE_FEATURES.md section 5, ADR-005)."""

from decimal import Decimal

from django.test import TestCase

from apps.products.models import Category, Product, ProductVariant

_product_seq = 0


def _product(**pricing) -> Product:
    global _product_seq
    _product_seq += 1
    category, _ = Category.objects.get_or_create(name="Mouse Pads", defaults={"code": "MP"})
    return Product.objects.create(
        name=f"Hexagare Mouse Pad {_product_seq}", category=category, **pricing
    )


def _variant(**overrides) -> ProductVariant:
    product = overrides.pop("product", None) or _product()
    defaults = dict(
        product=product,
        sku="HEX-MP-TEST-001",
        mrp=Decimal("1500.00"),
        selling_price=Decimal("1180.00"),
        tax_rate=Decimal("18.00"),
    )
    defaults.update(overrides)
    return ProductVariant.objects.create(**defaults)


class GstPricingTests(TestCase):
    def test_spec_example_1180_at_18_percent(self):
        v = _variant()
        self.assertEqual(v.base_price, Decimal("1000.00"))
        self.assertEqual(v.gst_amount, Decimal("180.00"))

    def test_cgst_sgst_split_sums_to_gst(self):
        v = _variant()
        self.assertEqual(v.cgst_amount, Decimal("90.00"))
        self.assertEqual(v.sgst_amount, Decimal("90.00"))
        self.assertEqual(v.cgst_amount + v.sgst_amount, v.gst_amount)

    def test_zero_tax_rate_leaves_price_untaxed(self):
        v = _variant(tax_rate=Decimal("0.00"), selling_price=Decimal("999.00"))
        self.assertEqual(v.base_price, Decimal("999.00"))
        self.assertEqual(v.gst_amount, Decimal("0.00"))

    def test_rounding_is_half_up_to_two_places(self):
        v = _variant(selling_price=Decimal("999.99"), tax_rate=Decimal("12.00"))
        # 999.99 / 1.12 = 892.848...  -> 892.85 ; gst = 107.14
        self.assertEqual(v.base_price, Decimal("892.85"))
        self.assertEqual(v.gst_amount, Decimal("107.14"))
        self.assertEqual(v.base_price + v.gst_amount, Decimal("999.99"))


class PricingInheritanceTests(TestCase):
    def test_variant_with_null_prices_inherits_the_product(self):
        product = _product(
            mrp=Decimal("1500.00"),
            selling_price=Decimal("1180.00"),
            purchase_price=Decimal("600.00"),
            tax_rate=Decimal("18.00"),
        )
        v = ProductVariant.objects.create(product=product, sku="HEX-MP-INH-001")
        self.assertIsNone(v.selling_price)
        self.assertEqual(v.effective_mrp, Decimal("1500.00"))
        self.assertEqual(v.effective_selling_price, Decimal("1180.00"))
        self.assertEqual(v.effective_purchase_price, Decimal("600.00"))
        self.assertEqual(v.effective_tax_rate, Decimal("18.00"))
        self.assertEqual(v.base_price, Decimal("1000.00"))
        self.assertEqual(v.gst_amount, Decimal("180.00"))

    def test_variant_override_wins_field_by_field(self):
        product = _product(
            mrp=Decimal("1500.00"),
            selling_price=Decimal("1180.00"),
            tax_rate=Decimal("18.00"),
        )
        v = ProductVariant.objects.create(
            product=product, sku="HEX-MP-OVR-001", selling_price=Decimal("2360.00")
        )
        self.assertEqual(v.effective_selling_price, Decimal("2360.00"))
        self.assertEqual(v.effective_mrp, Decimal("1500.00"))  # still inherited
        self.assertEqual(v.effective_tax_rate, Decimal("18.00"))
        self.assertEqual(v.base_price, Decimal("2000.00"))

    def test_effective_values_default_to_zero_when_nothing_set(self):
        product = _product()
        v = ProductVariant.objects.create(product=product, sku="HEX-MP-ZERO-001")
        self.assertEqual(v.effective_selling_price, Decimal("0.00"))
        self.assertEqual(v.effective_tax_rate, Decimal("0.00"))
        self.assertEqual(v.base_price, Decimal("0.00"))


class DiscountTests(TestCase):
    def test_discount_amount_and_percent(self):
        v = _variant(mrp=Decimal("1500.00"), selling_price=Decimal("1180.00"))
        self.assertEqual(v.discount_amount, Decimal("320.00"))
        # 320 / 1500 * 100 = 21.333... -> 21.33
        self.assertEqual(v.discount_percent, Decimal("21.33"))

    def test_discount_is_zero_when_selling_ge_mrp(self):
        equal = _variant(mrp=Decimal("1000.00"), selling_price=Decimal("1000.00"))
        self.assertEqual(equal.discount_amount, Decimal("0.00"))
        self.assertEqual(equal.discount_percent, Decimal("0.00"))
        above = _variant(
            sku="HEX-MP-TEST-002", mrp=Decimal("1000.00"), selling_price=Decimal("1200.00")
        )
        self.assertEqual(above.discount_amount, Decimal("0.00"))

    def test_discount_is_zero_when_mrp_missing(self):
        product = _product(selling_price=Decimal("1180.00"), tax_rate=Decimal("18.00"))
        v = ProductVariant.objects.create(product=product, sku="HEX-MP-NOMRP-001")
        # effective_mrp resolves to 0 -> no discount, no ZeroDivisionError
        self.assertEqual(v.discount_amount, Decimal("0.00"))
        self.assertEqual(v.discount_percent, Decimal("0.00"))

    def test_discount_inherits_from_product_defaults(self):
        product = _product(mrp=Decimal("2000.00"), selling_price=Decimal("1600.00"))
        v = ProductVariant.objects.create(product=product, sku="HEX-MP-DISC-001")
        self.assertEqual(v.discount_amount, Decimal("400.00"))
        self.assertEqual(v.discount_percent, Decimal("20.00"))
        # Product-level derivation matches.
        self.assertEqual(product.discount_amount, Decimal("400.00"))
        self.assertEqual(product.discount_percent, Decimal("20.00"))
