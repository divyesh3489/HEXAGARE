"""SerializedInventoryService -- the only path that moves a unit's status AND
the stock ledger together."""

from decimal import Decimal

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.inventory.models import InventoryBalance, InventoryTransaction, Location
from apps.products.models import Category, Product, ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import create_unit
from apps.products.services.serialized_inventory import SerializedInventoryService


class SerializedInventoryServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Mouse Pads", code="MP")
        cls.product = Product.objects.create(
            name="Pad",
            category=cls.category,
            status=Product.Status.ACTIVE,
            mrp=Decimal("1180"),
            selling_price=Decimal("1180"),
            tax_rate=Decimal("18"),
        )
        cls.variant = ProductVariant.objects.create(product=cls.product, sku="HEX-MP-A-1", code="A")
        cls.warehouse = Location.objects.get(code="warehouse")
        cls.offline = Location.objects.get(code="offline")

    def setUp(self):
        self.unit = create_unit(
            variant=self.variant, location=self.warehouse, status="AVAILABLE"
        )

    def bucket(self, location, status):
        row = InventoryBalance.objects.filter(
            variant=self.variant, location=location, status=status
        ).first()
        return row.quantity if row else 0

    def test_reserve_moves_status_event_and_ledger_together(self):
        SerializedInventoryService.reserve(self.unit, note="order #7")
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, SerializedUnit.Status.RESERVED)
        # unit event
        self.assertEqual(self.unit.events.first().to_status, "RESERVED")
        # ledger pair
        self.assertEqual(self.bucket(self.warehouse, "AVAILABLE"), 0)
        self.assertEqual(self.bucket(self.warehouse, "RESERVED"), 1)

    def test_transfer_out_keeps_location_then_receive_moves_it(self):
        SerializedInventoryService.start_transfer(self.unit)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, SerializedUnit.Status.IN_TRANSIT)
        self.assertEqual(self.unit.location, self.warehouse)  # still recorded at source
        self.assertEqual(self.bucket(self.warehouse, "IN_TRANSIT"), 1)

        SerializedInventoryService.complete_transfer(self.unit, to_location=self.offline)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, SerializedUnit.Status.AVAILABLE)
        self.assertEqual(self.unit.location, self.offline)
        self.assertEqual(self.bucket(self.warehouse, "IN_TRANSIT"), 0)
        self.assertEqual(self.bucket(self.offline, "AVAILABLE"), 1)

    def test_cancel_transfer_returns_unit_to_source(self):
        SerializedInventoryService.start_transfer(self.unit)
        SerializedInventoryService.cancel_transfer(self.unit)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, SerializedUnit.Status.AVAILABLE)
        self.assertEqual(self.unit.location, self.warehouse)
        self.assertEqual(self.bucket(self.warehouse, "AVAILABLE"), 1)
        self.assertEqual(self.bucket(self.warehouse, "IN_TRANSIT"), 0)

    def test_invalid_transition_rolls_back_both_status_and_ledger(self):
        # AVAILABLE -> SOLD is not a legal direct move.
        with self.assertRaises(ValidationError):
            SerializedInventoryService.sell(self.unit)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, SerializedUnit.Status.AVAILABLE)
        self.assertEqual(self.bucket(self.warehouse, "AVAILABLE"), 1)
        # only the OPENING row exists
        self.assertEqual(
            InventoryTransaction.objects.filter(serialized_unit=self.unit).count(), 1
        )

    def test_sell_from_reserved_writes_sale_ledger_rows(self):
        SerializedInventoryService.reserve(self.unit)
        SerializedInventoryService.sell(self.unit, note="invoice #1")
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, SerializedUnit.Status.SOLD)
        self.assertEqual(self.bucket(self.warehouse, "RESERVED"), 0)
        self.assertEqual(self.bucket(self.warehouse, "SOLD"), 1)
        self.assertTrue(
            InventoryTransaction.objects.filter(
                serialized_unit=self.unit, kind=InventoryTransaction.Kind.SALE
            ).exists()
        )

    def test_damage_then_restore(self):
        SerializedInventoryService.damage(self.unit)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, SerializedUnit.Status.DAMAGED)
        self.assertEqual(self.bucket(self.warehouse, "DAMAGED"), 1)

        SerializedInventoryService.restore(self.unit)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, SerializedUnit.Status.AVAILABLE)
        self.assertEqual(self.bucket(self.warehouse, "DAMAGED"), 0)
        self.assertEqual(self.bucket(self.warehouse, "AVAILABLE"), 1)

    def test_generate_writes_opening_row(self):
        unit = SerializedInventoryService.generate(
            variant=self.variant, location=self.offline, status="AVAILABLE"
        )
        self.assertTrue(
            InventoryTransaction.objects.filter(
                serialized_unit=unit, kind=InventoryTransaction.Kind.OPENING
            ).exists()
        )
        self.assertEqual(self.bucket(self.offline, "AVAILABLE"), 1)
