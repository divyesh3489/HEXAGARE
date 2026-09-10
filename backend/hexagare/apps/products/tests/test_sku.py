"""SKU auto-suggestion service."""

from decimal import Decimal

from django.test import TestCase, override_settings

from apps.products.models import Category, Product, ProductVariant
from apps.products.services.sku import is_sku_available, suggest_sku


def _make_product(cat_code="MP"):
    category = Category.objects.create(name="Mouse Pads", code=cat_code)
    return Product.objects.create(name="Hexagare Mouse Pad", category=category, code="MP")


def _variant(product, sku, **overrides):
    defaults = dict(
        product=product,
        sku=sku,
        mrp=Decimal("1000"),
        selling_price=Decimal("1000"),
    )
    defaults.update(overrides)
    return ProductVariant.objects.create(**defaults)


class SuggestSkuTests(TestCase):
    def test_format_uses_prefix_category_and_variant_tokens(self):
        product = _make_product()
        sku = suggest_sku(category=product.category, product=product, variant_code="11x23")
        self.assertEqual(sku, "HEX-MP-11X23-001")

    @override_settings(HEXAGARE_SKU_PREFIX="ACME")
    def test_prefix_comes_from_settings(self):
        product = _make_product()
        sku = suggest_sku(category=product.category, product=product, variant_code="A")
        self.assertTrue(sku.startswith("ACME-MP-A-"))

    def test_sequence_increments_per_stem(self):
        product = _make_product()
        _variant(product, "HEX-MP-11X23-001")
        _variant(product, "HEX-MP-11X23-002")
        sku = suggest_sku(category=product.category, product=product, variant_code="11x23")
        self.assertEqual(sku, "HEX-MP-11X23-003")

    def test_skips_an_existing_out_of_sequence_sku(self):
        product = _make_product()
        _variant(product, "HEX-MP-11X23-001")
        # A manual SKU that collides with the next computed value.
        _variant(product, "HEX-MP-11X23-002")
        sku = suggest_sku(category=product.category, product=product, variant_code="11x23")
        self.assertEqual(sku, "HEX-MP-11X23-003")

    def test_derives_fragment_from_attribute_values_when_no_code(self):
        product = _make_product()
        sku = suggest_sku(
            category=product.category,
            product=product,
            attribute_values=["11 x 23 inch", "Black"],
        )
        self.assertEqual(sku, "HEX-MP-11X23INCHBLACK-001")

    def test_falls_back_to_product_initials_without_category_code(self):
        category = Category.objects.create(name="Gaming Gear")  # no code
        product = Product.objects.create(name="Wrist Rest", category=category)
        sku = suggest_sku(category=category, product=product)
        self.assertTrue(sku.startswith("HEX-GG-WR-"))


class IsSkuAvailableTests(TestCase):
    def test_reports_taken_and_free(self):
        product = _make_product()
        _variant(product, "HEX-MP-X-001")
        self.assertFalse(is_sku_available("hex-mp-x-001"))  # case-insensitive
        self.assertTrue(is_sku_available("HEX-MP-X-002"))

    def test_exclude_variant_lets_a_variant_keep_its_own_sku(self):
        product = _make_product()
        v = _variant(product, "HEX-MP-X-001")
        self.assertTrue(is_sku_available("HEX-MP-X-001", exclude_variant_id=v.pk))
