"""Phase 5 -- the ReportLab label-sheet renderer (``services.labels``)."""

from __future__ import annotations

import re
from decimal import Decimal

from django.test import TestCase

from apps.inventory.models import Location
from apps.products.models import (
    Category,
    LabelBatch,
    LabelBatchItem,
    LabelSize,
    Product,
    ProductVariant,
)
from apps.products.services.labels import build_label_pdf
from apps.products.services.serial_numbers import create_unit


def _page_count(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page\b", pdf))


class BuildLabelPdfTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Mouse Pads", code="MP")
        cls.product = Product.objects.create(
            name="Hexagare Mouse Pad",
            category=cls.category,
            status=Product.Status.ACTIVE,
            mrp=Decimal("1180"),
            selling_price=Decimal("1180"),
            tax_rate=Decimal("18"),
        )
        cls.variant = ProductVariant.objects.create(
            product=cls.product, sku="HEX-MP-11X23-001", code="11X23"
        )
        cls.warehouse = Location.objects.get(code="warehouse")

    def _batch(self, *, quantity, label_size, **fields):
        batch = LabelBatch.objects.create(
            variant=self.variant,
            location=self.warehouse,
            quantity=quantity,
            initial_status="AVAILABLE",
            label_size=label_size,
            **fields,
        )
        for _ in range(quantity):
            unit = create_unit(
                variant=self.variant, location=self.warehouse, status="AVAILABLE"
            )
            LabelBatchItem.objects.create(batch=batch, serialized_unit=unit)
        return batch

    def test_renders_a_pdf_for_a_multi_up_sheet(self):
        size = LabelSize.objects.get(code="a4-24up")
        batch = self._batch(
            quantity=3, label_size=size, include_mrp=True, custom_text="Fragile"
        )
        pdf = build_label_pdf(batch)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 1000)

    def test_quantity_beyond_one_page_paginates(self):
        # a4-24up is 3 x 8 = 24 per page; 25 units => 2 pages.
        size = LabelSize.objects.get(code="a4-24up")
        one_page = build_label_pdf(self._batch(quantity=24, label_size=size))
        two_pages = build_label_pdf(self._batch(quantity=25, label_size=size))
        self.assertEqual(_page_count(one_page), 1)
        self.assertEqual(_page_count(two_pages), 2)

    def test_renders_a_single_label_thermal_roll(self):
        size = LabelSize.objects.get(code="thermal-50x25")
        pdf = build_label_pdf(self._batch(quantity=2, label_size=size))
        self.assertTrue(pdf.startswith(b"%PDF"))
        # 1 x 1 grid => one page per label.
        self.assertEqual(_page_count(pdf), 2)

    def test_empty_batch_still_renders(self):
        size = LabelSize.objects.get(code="a4-24up")
        batch = LabelBatch.objects.create(
            variant=self.variant,
            location=self.warehouse,
            quantity=0,
            initial_status="AVAILABLE",
            label_size=size,
        )
        pdf = build_label_pdf(batch)
        self.assertTrue(pdf.startswith(b"%PDF"))
