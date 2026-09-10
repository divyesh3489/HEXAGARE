"""Catalog model invariants."""

from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase

from apps.products.models import (
    Category,
    Product,
    ProductAttribute,
    ProductAttributeValue,
    ProductVariant,
)


class CategoryTests(TestCase):
    def test_slug_and_code_are_normalised_on_save(self):
        parent = Category.objects.create(name="Peripherals", code=" per ")
        child = Category.objects.create(name="Mouse Pads", parent=parent)
        self.assertEqual(parent.code, "PER")
        self.assertEqual(child.slug, "mouse-pads")
        self.assertEqual(child.parent, parent)

    def test_category_with_products_cannot_be_deleted(self):
        category = Category.objects.create(name="Mouse Pads")
        Product.objects.create(name="Pad", category=category)
        with self.assertRaises(ProtectedError):
            category.delete()


class VariantTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Mouse Pads", code="MP")
        self.product = Product.objects.create(name="Pad", category=self.category)

    def _variant(self, sku, **kw):
        return ProductVariant.objects.create(
            product=self.product,
            sku=sku,
            mrp=Decimal("1000"),
            selling_price=Decimal("1000"),
            **kw,
        )

    def test_sku_is_globally_unique(self):
        self._variant("HEX-MP-A-001")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._variant("HEX-MP-A-001")

    def test_one_value_per_attribute_per_variant(self):
        variant = self._variant("HEX-MP-A-001")
        size = ProductAttribute.objects.create(name="Size", code="size")
        ProductAttributeValue.objects.create(variant=variant, attribute=size, value="S")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ProductAttributeValue.objects.create(
                    variant=variant, attribute=size, value="M"
                )

    def test_attribute_in_use_is_protected(self):
        variant = self._variant("HEX-MP-A-001")
        colour = ProductAttribute.objects.create(name="Colour", code="colour")
        ProductAttributeValue.objects.create(variant=variant, attribute=colour, value="Red")
        with self.assertRaises(ProtectedError):
            colour.delete()
