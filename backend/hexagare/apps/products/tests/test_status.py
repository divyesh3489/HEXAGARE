"""Variant availability derives from the product's status (ADR-006)."""

from decimal import Decimal

from django.test import TestCase

from apps.products.models import Category, Product, ProductVariant


class VariantEffectiveStatusTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Mouse Pads", code="MP")

    def _variant(self, product_status: str, *, is_active: bool) -> ProductVariant:
        product = Product.objects.create(
            name=f"Pad {product_status} {is_active}",
            category=self.category,
            status=product_status,
            mrp=Decimal("1000"),
            selling_price=Decimal("1000"),
        )
        return ProductVariant.objects.create(
            product=product, sku=f"HEX-MP-{product_status}-{int(is_active)}", is_active=is_active
        )

    def test_active_product_defers_to_variant_flag(self):
        on = self._variant(Product.Status.ACTIVE, is_active=True)
        self.assertEqual(on.effective_status, Product.Status.ACTIVE)
        self.assertTrue(on.is_available)

        off = self._variant(Product.Status.ACTIVE, is_active=False)
        self.assertEqual(off.effective_status, Product.Status.INACTIVE)
        self.assertFalse(off.is_available)

    def test_discontinued_product_forces_discontinued(self):
        for flag in (True, False):
            v = self._variant(Product.Status.DISCONTINUED, is_active=flag)
            self.assertEqual(v.effective_status, Product.Status.DISCONTINUED)
            self.assertFalse(v.is_available)

    def test_draft_and_inactive_products_hide_variants(self):
        for status in (Product.Status.DRAFT, Product.Status.INACTIVE):
            v = self._variant(status, is_active=True)
            self.assertEqual(v.effective_status, status)
            self.assertFalse(v.is_available)
