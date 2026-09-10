"""Inventory alerts computed from the balance cache + StockLevelPolicy."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.rbac import ensure_role_groups
from apps.inventory.models import Location, StockLevelPolicy
from apps.inventory.services.alerts import compute_alerts
from apps.inventory.services.ledger import InventoryService
from apps.products.models import Category, Product, ProductVariant
from apps.products.services.serial_numbers import create_unit, transition_unit

User = get_user_model()


class AlertComputationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.warehouse = Location.objects.get(code="warehouse")
        cls.offline = Location.objects.get(code="offline")
        cls.category = Category.objects.create(name="Mouse Pads", code="MP")
        cls.product = Product.objects.create(
            name="Pad", category=cls.category, status=Product.Status.ACTIVE,
            mrp=Decimal("1180"), selling_price=Decimal("1180"), tax_rate=Decimal("18"),
        )
        cls.low = ProductVariant.objects.create(product=cls.product, sku="HEX-MP-LOW", code="LOW")
        cls.out = ProductVariant.objects.create(product=cls.product, sku="HEX-MP-OUT", code="OUT")
        cls.over = ProductVariant.objects.create(product=cls.product, sku="HEX-MP-OVR", code="OVR")

    def _types(self, alerts, sku):
        return {a["type"] for a in alerts if a["variant"]["sku"] == sku}

    def test_low_out_and_overstock(self):
        create_unit(variant=self.low, location=self.warehouse, status="AVAILABLE")
        StockLevelPolicy.objects.create(variant=self.low, min_quantity=5)

        StockLevelPolicy.objects.create(variant=self.out, min_quantity=2)  # 0 on hand

        for _ in range(6):
            create_unit(variant=self.over, location=self.warehouse, status="AVAILABLE")
        StockLevelPolicy.objects.create(variant=self.over, min_quantity=1, max_quantity=5)

        alerts = compute_alerts()
        self.assertEqual(self._types(alerts, "HEX-MP-LOW"), {"low_stock"})
        self.assertEqual(self._types(alerts, "HEX-MP-OUT"), {"out_of_stock"})
        self.assertEqual(self._types(alerts, "HEX-MP-OVR"), {"overstock"})

    def test_healthy_stock_raises_no_alert(self):
        for _ in range(3):
            create_unit(variant=self.low, location=self.warehouse, status="AVAILABLE")
        StockLevelPolicy.objects.create(variant=self.low, min_quantity=2, max_quantity=10)
        self.assertEqual(compute_alerts(variant_id=self.low.id), [])

    def test_location_scoped_policy_only_counts_that_location(self):
        create_unit(variant=self.low, location=self.warehouse, status="AVAILABLE")
        create_unit(variant=self.low, location=self.offline, status="AVAILABLE")
        StockLevelPolicy.objects.create(
            variant=self.low, location=self.offline, min_quantity=3
        )
        alerts = compute_alerts()
        low = [a for a in alerts if a["variant"]["sku"] == "HEX-MP-LOW"]
        self.assertEqual(len(low), 1)
        self.assertEqual(low[0]["type"], "low_stock")
        self.assertEqual(low[0]["location"]["id"], self.offline.id)

    def test_balance_mismatch_surfaces_after_a_ledger_free_transition(self):
        unit = create_unit(variant=self.low, location=self.warehouse, status="AVAILABLE")
        transition_unit(unit, to_status="DAMAGED")  # no ledger row
        mismatches = [a for a in compute_alerts() if a["type"] == "balance_mismatch"]
        self.assertTrue(mismatches)

        InventoryService.rebuild_balances()
        mismatches = [a for a in compute_alerts() if a["type"] == "balance_mismatch"]
        self.assertEqual(mismatches, [])

    def test_reconciliation_can_be_switched_off(self):
        unit = create_unit(variant=self.low, location=self.warehouse, status="AVAILABLE")
        transition_unit(unit, to_status="DAMAGED")
        alerts = compute_alerts(include_reconciliation=False)
        self.assertFalse([a for a in alerts if a["type"] == "balance_mismatch"])


class AlertsApiTests(TestCase):
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
        StockLevelPolicy.objects.create(variant=cls.variant, min_quantity=3)
        cls.viewer = User.objects.create_user("v@hexagare.test", "pw-Testing-123")
        cls.viewer.groups.add(Group.objects.get(name="Cashier"))  # inventory.view
        cls.outsider = User.objects.create_user("o@hexagare.test", "pw-Testing-123")

    def test_alerts_endpoint_returns_list(self):
        client = APIClient()
        client.force_authenticate(user=self.viewer)
        res = client.get("/api/v1/inventory/alerts/")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(any(a["type"] == "out_of_stock" for a in res.data))

    def test_alerts_endpoint_requires_inventory_view(self):
        client = APIClient()
        client.force_authenticate(user=self.outsider)
        self.assertEqual(client.get("/api/v1/inventory/alerts/").status_code, 403)
