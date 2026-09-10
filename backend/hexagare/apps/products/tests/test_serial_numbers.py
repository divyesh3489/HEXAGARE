"""Serial-number allocation + the serialized-unit lifecycle service."""

from decimal import Decimal

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.inventory.models import Location
from apps.products.models import Category, Product, ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import (
    create_unit,
    format_serial,
    resolve_unit,
    transition_unit,
)


class SerialAllocationTests(TestCase):
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
        cls.v1 = ProductVariant.objects.create(
            product=cls.product, sku="HEX-MP-A-001", code="11X23"
        )
        cls.v2 = ProductVariant.objects.create(
            product=cls.product, sku="HEX-MP-B-002", code="12X24"
        )
        cls.warehouse = Location.objects.get(code="warehouse")

    def test_serial_format_uses_prefix_variant_token_and_padding(self):
        self.assertEqual(format_serial(self.v1, 1), "HX11X23-000001")
        self.assertEqual(format_serial(self.v1, 42), "HX11X23-000042")

    def test_sequence_is_per_variant_and_increments(self):
        a = create_unit(variant=self.v1, location=self.warehouse)
        b = create_unit(variant=self.v1, location=self.warehouse)
        c = create_unit(variant=self.v2, location=self.warehouse)
        self.assertEqual((a.sequence, b.sequence, c.sequence), (1, 2, 1))
        self.assertEqual(a.serial_number, "HX11X23-000001")
        self.assertEqual(b.serial_number, "HX11X23-000002")
        self.assertEqual(c.serial_number, "HX12X24-000001")

    def test_variant_without_code_falls_back_to_sku_token(self):
        v = ProductVariant.objects.create(product=self.product, sku="HEX-MP-NOCODE-9")
        unit = create_unit(variant=v, location=self.warehouse)
        # SKU prefix "HEX" stripped, separators removed.
        self.assertEqual(unit.serial_number, "HXMPNOCODE9-000001")

    def test_create_writes_opening_event(self):
        unit = create_unit(variant=self.v1, location=self.warehouse, status="AVAILABLE")
        events = list(unit.events.all())
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0].from_status, events[0].to_status), ("", "AVAILABLE"))

    def test_create_rejects_non_initial_status(self):
        with self.assertRaises(ValidationError):
            create_unit(variant=self.v1, location=self.warehouse, status="SOLD")


class TransitionTests(TestCase):
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
        cls.variant = ProductVariant.objects.create(product=cls.product, sku="HEX-MP-A-1")
        cls.warehouse = Location.objects.get(code="warehouse")
        cls.offline = Location.objects.get(code="offline")

    def test_valid_transition_updates_status_and_logs_event(self):
        unit = create_unit(variant=self.variant, location=self.warehouse, status="AVAILABLE")
        transition_unit(unit, to_status="RESERVED", note="order #7")
        unit.refresh_from_db()
        self.assertEqual(unit.status, "RESERVED")
        latest = unit.events.first()
        self.assertEqual((latest.from_status, latest.to_status, latest.note),
                         ("AVAILABLE", "RESERVED", "order #7"))

    def test_transition_can_move_location(self):
        unit = create_unit(variant=self.variant, location=self.warehouse, status="AVAILABLE")
        transition_unit(unit, to_status="IN_TRANSIT")
        transition_unit(unit, to_status="AVAILABLE", location=self.offline)
        unit.refresh_from_db()
        self.assertEqual(unit.status, "AVAILABLE")
        self.assertEqual(unit.location, self.offline)

    def test_invalid_transition_is_rejected(self):
        unit = create_unit(variant=self.variant, location=self.warehouse)  # GENERATED
        with self.assertRaises(ValidationError):
            transition_unit(unit, to_status="SOLD")

    def test_no_op_transition_is_rejected(self):
        unit = create_unit(variant=self.variant, location=self.warehouse, status="AVAILABLE")
        with self.assertRaises(ValidationError):
            transition_unit(unit, to_status="AVAILABLE")

    def test_terminal_status_has_no_moves(self):
        unit = create_unit(variant=self.variant, location=self.warehouse)
        transition_unit(unit, to_status="CANCELLED")
        unit.refresh_from_db()
        self.assertTrue(unit.is_terminal)
        self.assertEqual(unit.allowed_transitions, [])


class ImmutabilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Mouse Pads", code="MP")
        cls.product = Product.objects.create(
            name="Pad", category=cls.category, status=Product.Status.ACTIVE,
            mrp=Decimal("1180"), selling_price=Decimal("1180"), tax_rate=Decimal("18"),
        )
        cls.v1 = ProductVariant.objects.create(product=cls.product, sku="HEX-MP-A-1", code="A")
        cls.v2 = ProductVariant.objects.create(product=cls.product, sku="HEX-MP-B-2", code="B")
        cls.warehouse = Location.objects.get(code="warehouse")

    def test_variant_cannot_be_changed_after_creation(self):
        unit = create_unit(variant=self.v1, location=self.warehouse)
        unit.variant = self.v2
        with self.assertRaises(ValueError):
            unit.save()
        unit.refresh_from_db()
        self.assertEqual(unit.variant, self.v1)
        self.assertTrue(unit.serial_number.startswith("HXA-"))

    def test_serial_number_cannot_be_changed(self):
        unit = create_unit(variant=self.v1, location=self.warehouse)
        unit.serial_number = "HXHACKED-000001"
        with self.assertRaises(ValueError):
            unit.save()

    def test_status_and_location_still_save_normally(self):
        unit = create_unit(variant=self.v1, location=self.warehouse, status="AVAILABLE")
        transition_unit(unit, to_status="RESERVED")  # exercises save(update_fields=...)
        unit.refresh_from_db()
        self.assertEqual(unit.status, "RESERVED")


class AdminTests(TestCase):
    def test_serialized_unit_admin_is_view_only(self):
        from django.contrib import admin

        from apps.products.models import SerializedUnit, SerializedUnitEvent

        for model in (SerializedUnit, SerializedUnitEvent):
            ma = admin.site._registry[model]
            self.assertFalse(ma.has_add_permission(None))
            self.assertFalse(ma.has_change_permission(None))
            self.assertFalse(ma.has_delete_permission(None))
            self.assertEqual(
                set(ma.get_readonly_fields(None)),
                {f.name for f in model._meta.fields},
            )


class ResolveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(name="Mouse Pads", code="MP")
        cls.product = Product.objects.create(
            name="Pad", category=cls.category, status=Product.Status.ACTIVE,
            mrp=Decimal("1180"), selling_price=Decimal("1180"), tax_rate=Decimal("18"),
        )
        cls.variant = ProductVariant.objects.create(product=cls.product, sku="HEX-MP-A-1")
        cls.warehouse = Location.objects.get(code="warehouse")

    def test_resolve_is_case_insensitive_and_returns_the_unit(self):
        unit = create_unit(variant=self.variant, location=self.warehouse)
        found = resolve_unit(unit.serial_number.lower())
        self.assertEqual(found.pk, unit.pk)

    def test_resolve_unknown_raises_404(self):
        from django.http import Http404

        with self.assertRaises(Http404):
            resolve_unit("HX-NOPE-000999")


class StateMachineIntegrityTests(TestCase):
    def test_transition_table_only_references_valid_statuses(self):
        valid = set(SerializedUnit.Status.values)
        for source, targets in SerializedUnit.ALLOWED_TRANSITIONS.items():
            self.assertIn(source, valid)
            self.assertTrue(set(targets) <= valid, f"bad targets from {source}: {targets}")
        # Every status appears as a key.
        self.assertEqual(set(SerializedUnit.ALLOWED_TRANSITIONS) , valid)
        # CANCELLED is the only terminal status.
        terminal = {s for s, t in SerializedUnit.ALLOWED_TRANSITIONS.items() if not t}
        self.assertEqual(terminal, {SerializedUnit.Status.CANCELLED})
