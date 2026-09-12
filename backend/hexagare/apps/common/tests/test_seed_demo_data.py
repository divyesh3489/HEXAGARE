"""The ``seed_demo_data`` management command."""

from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.expenses.models import Expense
from apps.products.models import (
    Category,
    Product,
    ProductAttributeValue,
    ProductVariant,
    SerializedUnit,
)

User = get_user_model()


def _run(**kwargs) -> str:
    out = StringIO()
    call_command("seed_demo_data", stdout=out, **kwargs)
    return out.getvalue()


class SeedDemoDataTests(TestCase):
    def test_creates_demo_users_and_catalog(self):
        _run()

        self.assertEqual(User.objects.filter(email__endswith="@hexagare.test").count(), 4)
        admin = User.objects.get(email="admin@hexagare.test")
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.check_password("demo-Passw0rd!"))
        self.assertTrue(admin.groups.filter(name="Admin").exists())

        cashier = User.objects.get(email="cashier@hexagare.test")
        self.assertFalse(cashier.is_staff)
        self.assertTrue(cashier.groups.filter(name="Cashier").exists())

        # Category tree wired up.
        mouse_pads = Category.objects.get(name="Mouse Pads")
        self.assertEqual(mouse_pads.parent.name, "Peripherals")

        self.assertEqual(Product.objects.count(), 3)
        self.assertEqual(ProductVariant.objects.count(), 6)
        variant = ProductVariant.objects.get(sku="HEX-MP-11X23-001")
        self.assertEqual(variant.attribute_values.get().value, "11 x 23 inch")

        # Pricing sits on the product; the small pad inherits, the large one overrides.
        self.assertEqual(variant.product.selling_price, Decimal("1180.00"))
        self.assertIsNone(variant.selling_price)
        self.assertEqual(variant.effective_selling_price, Decimal("1180.00"))
        large = ProductVariant.objects.get(sku="HEX-MP-12X32-001")
        self.assertEqual(large.selling_price, Decimal("1770.00"))

        # A few serialized units, each with an opening event -- plus 15 more
        # received against the demo purchase order (Phase 12).
        self.assertEqual(SerializedUnit.objects.count(), 22)
        self.assertEqual(variant.serialized_units.count(), 3 + 15)
        unit = variant.serialized_units.order_by("sequence").first()
        self.assertEqual(unit.serial_number, "HX11X23-000001")
        self.assertEqual(unit.events.count(), 1)

    def test_is_idempotent(self):
        _run()
        _run()

        self.assertEqual(User.objects.filter(email__endswith="@hexagare.test").count(), 4)
        self.assertEqual(Product.objects.count(), 3)
        self.assertEqual(ProductVariant.objects.count(), 6)
        self.assertEqual(ProductAttributeValue.objects.count(), 6)
        # Units are not regenerated on a second run (serials are never reused).
        self.assertEqual(SerializedUnit.objects.count(), 22)
        # No duplicate group memberships.
        admin = User.objects.get(email="admin@hexagare.test")
        self.assertEqual(admin.groups.filter(name="Admin").count(), 1)
        # Expenses are matched on (category, note) -- not duplicated on rerun.
        self.assertEqual(Expense.objects.count(), 4)

    def test_custom_password(self):
        _run(password="sw0rdfish-XYZ")
        self.assertTrue(
            User.objects.get(email="manager@hexagare.test").check_password("sw0rdfish-XYZ")
        )

    def test_realigns_a_preexisting_demo_account(self):
        stale = User.objects.create_user(
            "cashier@hexagare.test", "old-password", is_active=False
        )
        _run()
        stale.refresh_from_db()
        self.assertTrue(stale.is_active)
        self.assertTrue(stale.check_password("demo-Passw0rd!"))
        self.assertTrue(stale.groups.filter(name="Cashier").exists())

    @override_settings(DJANGO_ENV="production")
    def test_refuses_in_production_without_force(self):
        with self.assertRaises(CommandError):
            _run()
        self.assertFalse(User.objects.filter(email="admin@hexagare.test").exists())

    @override_settings(DJANGO_ENV="production")
    def test_force_overrides_production_guard(self):
        _run(force=True)
        self.assertTrue(User.objects.filter(email="admin@hexagare.test").exists())

    def test_demo_groups_exist_from_post_migrate(self):
        # Sanity: the RBAC groups the command attaches users to are seeded by the
        # accounts post_migrate hook, not by this command.
        self.assertEqual(Group.objects.filter(name__in=["Admin", "Cashier"]).count(), 2)
