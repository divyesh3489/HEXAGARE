"""``AmazonOrderImportService`` -- the core Phase 9 logic: idempotency,
order-level atomicity, unit selling, SKU mapping, and fee fallback."""

import io
from decimal import Decimal

from django.test import TestCase

from apps.integrations.amazon.models import (
    AmazonFeeConfig,
    AmazonImportBatch,
    AmazonOrderSettlement,
    AmazonSkuMapping,
)
from apps.integrations.amazon.services.importer import AmazonOrderImportService
from apps.integrations.amazon.sources import CSVAmazonOrderSource
from apps.inventory.models import Location
from apps.products.models import Category, Product, ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import create_unit
from apps.sales.models import Sale, SaleLineUnit, SalesChannel

HEADER = (
    "order_id,order_date,order_status,amazon_sku,quantity,selling_price,gst_amount,"
    "referral_fee,closing_fee,fulfillment_fee,shipping_cost,advertising_cost,other_charges,"
    "refund_amount"
)


class ImporterTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.channel = SalesChannel.objects.get(code="AMAZON")
        cls.amazon_location = Location.objects.get(code="amazon")
        category = Category.objects.create(name="Mouse Pads", code="MP")
        cls.product = Product.objects.create(
            name="Pad",
            category=category,
            status=Product.Status.ACTIVE,
            purchase_price=Decimal("400.00"),
        )
        cls.variant = ProductVariant.objects.create(
            product=cls.product, sku="HEX-MP-A-001", code="A"
        )

    def stock_amazon(self, n: int) -> list[SerializedUnit]:
        return [
            create_unit(
                variant=self.variant,
                location=self.amazon_location,
                status=SerializedUnit.Status.AVAILABLE,
            )
            for _ in range(n)
        ]

    def run_import(self, csv_text: str) -> AmazonImportBatch:
        batch = AmazonImportBatch.objects.create()
        source = CSVAmazonOrderSource(io.StringIO(csv_text))
        AmazonOrderImportService.run(batch, source)
        batch.refresh_from_db()
        return batch

    def row(self, order_id, status, quantity=1, sku=None, **overrides):
        values = {
            "order_id": order_id,
            "order_date": "2026-01-10",
            "order_status": status,
            "amazon_sku": sku or self.variant.sku,
            "quantity": quantity,
            "selling_price": "1180.00",
            "gst_amount": "180.00",
            "referral_fee": "150.00",
            "closing_fee": "20.00",
            "fulfillment_fee": "80.00",
            "shipping_cost": "80.00",
            "advertising_cost": "50.00",
            "other_charges": "10.00",
            "refund_amount": "0.00",
        }
        values.update(overrides)
        return ",".join(str(values[c]) for c in HEADER.split(","))

    def csv(self, *rows: str) -> str:
        return HEADER + "\n" + "\n".join(rows) + "\n"


class FulfilledOrderImportTests(ImporterTestBase):
    def test_shipped_order_sells_units_and_creates_settlement(self):
        units = self.stock_amazon(2)
        batch = self.run_import(self.csv(self.row("AMZ-1", "Shipped", quantity=2)))

        self.assertEqual(batch.status, AmazonImportBatch.Status.READY)
        self.assertEqual(batch.orders_created, 1)

        sale = Sale.objects.get(sales_channel=self.channel, external_reference="AMZ-1")
        self.assertEqual(sale.status, Sale.Status.SHIPPED)
        self.assertEqual(sale.lines.count(), 1)
        line = sale.lines.get()
        self.assertEqual(line.quantity, 2)
        self.assertEqual(line.units.count(), 2)

        for unit in units:
            unit.refresh_from_db()
            self.assertEqual(unit.status, SerializedUnit.Status.SOLD)

        settlement = AmazonOrderSettlement.objects.get(sale=sale, sku=self.variant.sku)
        self.assertEqual(settlement.selling_price, Decimal("2360.00"))  # 1180 * 2
        self.assertEqual(settlement.referral_fee, Decimal("150.00"))
        self.assertEqual(settlement.product_cost, Decimal("800.00"))  # 400 * 2

    def test_insufficient_stock_fails_only_that_order(self):
        self.stock_amazon(1)  # need 2
        batch = self.run_import(
            self.csv(
                self.row("AMZ-1", "Shipped", quantity=2),
                self.row("AMZ-2", "Pending", quantity=1),
            )
        )
        self.assertEqual(batch.status, AmazonImportBatch.Status.PARTIAL)
        self.assertEqual(batch.orders_failed, 1)
        self.assertEqual(batch.orders_created, 1)
        self.assertFalse(Sale.objects.filter(external_reference="AMZ-1").exists())
        self.assertTrue(Sale.objects.filter(external_reference="AMZ-2").exists())
        self.assertIn("Insufficient stock", batch.error_log[0]["message"])

    def test_pending_order_does_not_touch_stock(self):
        units = self.stock_amazon(1)
        batch = self.run_import(self.csv(self.row("AMZ-1", "Pending")))
        self.assertEqual(batch.status, AmazonImportBatch.Status.READY)
        units[0].refresh_from_db()
        self.assertEqual(units[0].status, SerializedUnit.Status.AVAILABLE)
        sale = Sale.objects.get(external_reference="AMZ-1")
        self.assertEqual(sale.status, Sale.Status.PENDING)
        self.assertEqual(sale.lines.get().units.count(), 0)


class IdempotencyTests(ImporterTestBase):
    def test_reimporting_unfulfilled_order_rebuilds_it(self):
        self.run_import(self.csv(self.row("AMZ-1", "Pending", quantity=1)))
        batch = self.run_import(self.csv(self.row("AMZ-1", "Confirmed", quantity=3)))

        self.assertEqual(batch.orders_updated, 1)
        sale = Sale.objects.get(external_reference="AMZ-1")
        self.assertEqual(sale.status, Sale.Status.CONFIRMED)
        self.assertEqual(sale.lines.get().quantity, 3)
        self.assertEqual(Sale.objects.filter(external_reference="AMZ-1").count(), 1)

    def test_reimporting_fulfilled_order_only_advances_status(self):
        self.stock_amazon(1)
        self.run_import(self.csv(self.row("AMZ-1", "Shipped", quantity=1)))
        line = Sale.objects.get(external_reference="AMZ-1").lines.get()
        bound_unit_id = line.units.get().serialized_unit_id

        batch = self.run_import(self.csv(self.row("AMZ-1", "Delivered", quantity=1)))
        self.assertEqual(batch.orders_updated, 1)

        sale = Sale.objects.get(external_reference="AMZ-1")
        self.assertEqual(sale.status, Sale.Status.DELIVERED)
        line.refresh_from_db()
        self.assertEqual(line.units.get().serialized_unit_id, bound_unit_id)
        self.assertEqual(SaleLineUnit.objects.filter(sale_line__sale=sale).count(), 1)

    def test_reimporting_same_status_is_a_no_op(self):
        self.stock_amazon(1)
        self.run_import(self.csv(self.row("AMZ-1", "Shipped", quantity=1)))
        batch = self.run_import(self.csv(self.row("AMZ-1", "Shipped", quantity=1)))
        self.assertEqual(batch.orders_skipped, 1)
        self.assertEqual(batch.orders_updated, 0)

    def test_cancelling_a_fulfilled_order_is_not_auto_reversed(self):
        self.stock_amazon(1)
        self.run_import(self.csv(self.row("AMZ-1", "Shipped", quantity=1)))
        batch = self.run_import(self.csv(self.row("AMZ-1", "Cancelled", quantity=1)))

        self.assertEqual(batch.orders_failed, 1)
        sale = Sale.objects.get(external_reference="AMZ-1")
        self.assertEqual(sale.status, Sale.Status.SHIPPED)  # unchanged
        unit = sale.lines.get().units.get().serialized_unit
        self.assertEqual(unit.status, SerializedUnit.Status.SOLD)  # not reversed


class SkuMappingTests(ImporterTestBase):
    def test_unknown_sku_fails_the_order(self):
        batch = self.run_import(self.csv(self.row("AMZ-1", "Pending", sku="NOT-MAPPED")))
        self.assertEqual(batch.orders_failed, 1)
        self.assertIn("Unknown Amazon SKU", batch.error_log[0]["message"])

    def test_exact_sku_match_auto_creates_a_mapping(self):
        self.run_import(self.csv(self.row("AMZ-1", "Pending", sku=self.variant.sku)))
        mapping = AmazonSkuMapping.objects.get(amazon_sku=self.variant.sku)
        self.assertEqual(mapping.variant_id, self.variant.pk)

    def test_explicit_mapping_is_used_over_a_different_sku_string(self):
        AmazonSkuMapping.objects.create(amazon_sku="AMZ-SKU-X", variant=self.variant)
        batch = self.run_import(self.csv(self.row("AMZ-1", "Pending", sku="AMZ-SKU-X")))
        self.assertEqual(batch.orders_created, 1)
        sale = Sale.objects.get(external_reference="AMZ-1")
        self.assertEqual(sale.lines.get().variant_id, self.variant.pk)


class FeeFallbackTests(ImporterTestBase):
    def test_blank_fee_column_falls_back_to_configured_fee(self):
        AmazonFeeConfig.objects.create(
            fee_name=AmazonFeeConfig.FeeName.REFERRAL,
            fee_type=AmazonFeeConfig.FeeType.PERCENTAGE,
            value=Decimal("15.00"),
            sales_channel=self.channel,
            effective_from="2025-01-01",
        )
        self.run_import(
            self.csv(self.row("AMZ-1", "Pending", referral_fee=""))
        )
        settlement = AmazonOrderSettlement.objects.get(sale__external_reference="AMZ-1")
        # taxable_value = (1180 - 180) * 1 = 1000.00 -> 15% = 150.00
        self.assertEqual(settlement.referral_fee, Decimal("150.00"))

    def test_explicit_csv_fee_wins_over_config(self):
        AmazonFeeConfig.objects.create(
            fee_name=AmazonFeeConfig.FeeName.REFERRAL,
            fee_type=AmazonFeeConfig.FeeType.PERCENTAGE,
            value=Decimal("15.00"),
            sales_channel=self.channel,
            effective_from="2025-01-01",
        )
        self.run_import(self.csv(self.row("AMZ-1", "Pending", referral_fee="99.00")))
        settlement = AmazonOrderSettlement.objects.get(sale__external_reference="AMZ-1")
        self.assertEqual(settlement.referral_fee, Decimal("99.00"))
