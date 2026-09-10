"""InventoryService -- the only writer of the stock ledger and its cache."""

from decimal import Decimal

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.inventory.models import InventoryBalance, InventoryTransaction, Location
from apps.inventory.services.ledger import InventoryService
from apps.products.models import Category, Product, ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import create_unit, transition_unit


class LedgerTestBase(TestCase):
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
        cls.variant = ProductVariant.objects.create(
            product=cls.product, sku="HEX-MP-A-001", code="A"
        )
        cls.warehouse = Location.objects.get(code="warehouse")
        cls.offline = Location.objects.get(code="offline")

    def bucket(self, location, status):
        row = InventoryBalance.objects.filter(
            variant=self.variant, location=location, status=status
        ).first()
        return row.quantity if row else 0


class RecordTests(LedgerTestBase):
    def test_record_writes_a_transaction_and_updates_the_balance(self):
        txn = InventoryService.record(
            variant=self.variant,
            location=self.warehouse,
            status="AVAILABLE",
            quantity=3,
            kind=InventoryTransaction.Kind.ADJUSTMENT,
        )
        self.assertEqual(txn.quantity, 3)
        self.assertEqual(self.bucket(self.warehouse, "AVAILABLE"), 3)

    def test_record_rejects_a_zero_movement(self):
        with self.assertRaises(ValidationError):
            InventoryService.record(
                variant=self.variant,
                location=self.warehouse,
                status="AVAILABLE",
                quantity=0,
                kind=InventoryTransaction.Kind.ADJUSTMENT,
            )

    def test_record_refuses_to_drive_a_balance_negative(self):
        InventoryService.record(
            variant=self.variant, location=self.warehouse, status="AVAILABLE",
            quantity=2, kind=InventoryTransaction.Kind.ADJUSTMENT,
        )
        with self.assertRaises(ValidationError):
            InventoryService.record(
                variant=self.variant, location=self.warehouse, status="AVAILABLE",
                quantity=-5, kind=InventoryTransaction.Kind.ADJUSTMENT,
            )
        self.assertEqual(self.bucket(self.warehouse, "AVAILABLE"), 2)

    def test_move_unit_emits_a_paired_reference(self):
        unit = create_unit(variant=self.variant, location=self.warehouse, status="AVAILABLE")
        reference = InventoryService.move_unit(
            unit=unit,
            from_location=self.warehouse,
            from_status="AVAILABLE",
            to_location=self.offline,
            to_status="AVAILABLE",
            kind=InventoryTransaction.Kind.TRANSFER_IN,
        )
        rows = InventoryTransaction.objects.filter(reference=reference).order_by("quantity")
        self.assertEqual([r.quantity for r in rows], [-1, 1])
        self.assertEqual({r.location_id for r in rows}, {self.warehouse.id, self.offline.id})

    def test_move_unit_noop_writes_nothing(self):
        unit = create_unit(variant=self.variant, location=self.warehouse, status="AVAILABLE")
        before = InventoryTransaction.objects.count()
        InventoryService.move_unit(
            unit=unit, from_location=self.warehouse, from_status="AVAILABLE",
            to_location=self.warehouse, to_status="AVAILABLE",
            kind=InventoryTransaction.Kind.TRANSFER_IN,
        )
        self.assertEqual(InventoryTransaction.objects.count(), before)


class OpeningRowTests(LedgerTestBase):
    def test_create_unit_writes_an_opening_ledger_row_and_balance(self):
        unit = create_unit(variant=self.variant, location=self.warehouse, status="AVAILABLE")
        txn = InventoryTransaction.objects.get(serialized_unit=unit)
        self.assertEqual((txn.kind, txn.quantity, txn.status), ("OPENING", 1, "AVAILABLE"))
        self.assertEqual(self.bucket(self.warehouse, "AVAILABLE"), 1)

    def test_ledger_free_transition_leaves_the_cache_stale_until_rebuild(self):
        unit = create_unit(variant=self.variant, location=self.warehouse, status="AVAILABLE")
        transition_unit(unit, to_status="DAMAGED")  # Phase 3 path -- no ledger row
        self.assertEqual(self.bucket(self.warehouse, "AVAILABLE"), 1)  # stale
        self.assertEqual(self.bucket(self.warehouse, "DAMAGED"), 0)

        InventoryService.rebuild_balances()
        self.assertEqual(self.bucket(self.warehouse, "AVAILABLE"), 0)
        self.assertEqual(self.bucket(self.warehouse, "DAMAGED"), 1)

    def test_rebuild_folds_in_non_serialized_adjustments(self):
        create_unit(variant=self.variant, location=self.warehouse, status="AVAILABLE")
        InventoryService.adjust(
            variant=self.variant, location=self.warehouse, status="AVAILABLE", quantity=4
        )
        InventoryService.rebuild_balances()
        self.assertEqual(self.bucket(self.warehouse, "AVAILABLE"), 5)


class ImmutabilityTests(LedgerTestBase):
    def test_transaction_rows_cannot_be_edited_or_deleted(self):
        txn = InventoryService.record(
            variant=self.variant, location=self.warehouse, status="AVAILABLE",
            quantity=1, kind=InventoryTransaction.Kind.ADJUSTMENT,
        )
        txn.quantity = 99
        with self.assertRaises(ValueError):
            txn.save()
        with self.assertRaises(ValueError):
            txn.delete()

    def test_unit_status_matches_the_ledger_after_a_service_move(self):
        unit = create_unit(variant=self.variant, location=self.warehouse, status="AVAILABLE")
        from apps.products.services.serialized_inventory import SerializedInventoryService

        SerializedInventoryService.reserve(unit)
        unit.refresh_from_db()
        self.assertEqual(unit.status, SerializedUnit.Status.RESERVED)
        self.assertEqual(self.bucket(self.warehouse, "AVAILABLE"), 0)
        self.assertEqual(self.bucket(self.warehouse, "RESERVED"), 1)
