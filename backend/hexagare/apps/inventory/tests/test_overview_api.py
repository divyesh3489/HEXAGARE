"""Live inventory overview + manual adjustment endpoints."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.rbac import ensure_role_groups
from apps.inventory.models import InventoryBalance, Location
from apps.products.models import Category, Product, ProductVariant
from apps.products.services.serial_numbers import create_unit, transition_unit
from apps.products.services.serialized_inventory import SerializedInventoryService

User = get_user_model()


class OverviewApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.warehouse = Location.objects.get(code="warehouse")
        cls.offline = Location.objects.get(code="offline")
        cls.category = Category.objects.create(name="Mouse Pads", code="MP")
        cls.product = Product.objects.create(
            name="Pad", category=cls.category, status=Product.Status.ACTIVE,
            mrp=Decimal("1180"), selling_price=Decimal("1180"), tax_rate=Decimal("18"),
        )
        cls.variant = ProductVariant.objects.create(product=cls.product, sku="HEX-MP-A", code="A")

        cls.viewer = User.objects.create_user("v@hexagare.test", "pw-Testing-123")
        cls.viewer.groups.add(Group.objects.get(name="Cashier"))  # inventory.view, no adjust
        cls.warehouse_user = User.objects.create_user("w@hexagare.test", "pw-Testing-123")
        cls.warehouse_user.groups.add(Group.objects.get(name="Warehouse"))  # stock_adjustments

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.viewer)

    def test_overview_is_computed_live_from_units(self):
        create_unit(variant=self.variant, location=self.warehouse, status="AVAILABLE")
        create_unit(variant=self.variant, location=self.warehouse, status="AVAILABLE")
        create_unit(variant=self.variant, location=self.offline, status="GENERATED")

        res = self.client.get("/api/v1/inventory/overview/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["computed_from"], "serialized_units")
        self.assertEqual(res.data["totals_by_status"]["AVAILABLE"], 2)
        self.assertEqual(res.data["totals_by_status"]["GENERATED"], 1)
        self.assertTrue(res.data["cache_matches"])

    def test_overview_reports_cache_drift_after_ledger_free_transition(self):
        unit = create_unit(variant=self.variant, location=self.warehouse, status="AVAILABLE")
        transition_unit(unit, to_status="DAMAGED")  # no ledger row

        res = self.client.get("/api/v1/inventory/overview/")
        self.assertFalse(res.data["cache_matches"])
        # the live view still reflects reality
        self.assertEqual(res.data["totals_by_status"].get("DAMAGED"), 1)

    def test_overview_matches_cache_after_service_moves(self):
        unit = create_unit(variant=self.variant, location=self.warehouse, status="AVAILABLE")
        SerializedInventoryService.reserve(unit)
        res = self.client.get("/api/v1/inventory/overview/")
        self.assertTrue(res.data["cache_matches"])

    def test_overview_requires_inventory_view(self):
        client = APIClient()
        outsider = User.objects.create_user("x@hexagare.test", "pw-Testing-123")
        client.force_authenticate(user=outsider)
        self.assertEqual(client.get("/api/v1/inventory/overview/").status_code, 403)


class AdjustmentApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.warehouse = Location.objects.get(code="warehouse")
        cls.category = Category.objects.create(name="Mouse Pads", code="MP")
        cls.product = Product.objects.create(
            name="Pad", category=cls.category, status=Product.Status.ACTIVE,
            mrp=Decimal("1180"), selling_price=Decimal("1180"), tax_rate=Decimal("18"),
        )
        cls.variant = ProductVariant.objects.create(product=cls.product, sku="HEX-MP-A", code="A")
        cls.viewer = User.objects.create_user("v@hexagare.test", "pw-Testing-123")
        cls.viewer.groups.add(Group.objects.get(name="Cashier"))
        cls.warehouse_user = User.objects.create_user("w@hexagare.test", "pw-Testing-123")
        cls.warehouse_user.groups.add(Group.objects.get(name="Warehouse"))

    def test_adjustment_requires_stock_adjustments_permission(self):
        client = APIClient()
        client.force_authenticate(user=self.viewer)
        res = client.post(
            "/api/v1/inventory/adjustments/",
            {"variant": self.variant.id, "location": self.warehouse.id,
             "status": "AVAILABLE", "quantity": 5},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_adjustment_writes_a_ledger_row_and_balance(self):
        client = APIClient()
        client.force_authenticate(user=self.warehouse_user)
        res = client.post(
            "/api/v1/inventory/adjustments/",
            {"variant": self.variant.id, "location": self.warehouse.id,
             "status": "AVAILABLE", "quantity": 5, "note": "found a box"},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["kind"], "ADJUSTMENT")
        balance = InventoryBalance.objects.get(
            variant=self.variant, location=self.warehouse, status="AVAILABLE"
        )
        self.assertEqual(balance.quantity, 5)

    def test_adjustment_cannot_drive_negative(self):
        client = APIClient()
        client.force_authenticate(user=self.warehouse_user)
        res = client.post(
            "/api/v1/inventory/adjustments/",
            {"variant": self.variant.id, "location": self.warehouse.id,
             "status": "AVAILABLE", "quantity": -3},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
