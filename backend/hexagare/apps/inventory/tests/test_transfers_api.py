"""Scan-based stock transfer flow (``/api/v1/inventory/transfers/``)."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.rbac import ensure_role_groups
from apps.inventory.models import InventoryBalance, Location, StockTransfer
from apps.products.models import Category, Product, ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import create_unit

User = get_user_model()


class StockTransferApiTests(TestCase):
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
        cls.variant = ProductVariant.objects.create(product=cls.product, sku="HEX-MP-A-1", code="A")

        # Warehouse role holds inventory.transfer.
        cls.wh_user = User.objects.create_user("wh@hexagare.test", "pw-Testing-123")
        cls.wh_user.groups.add(Group.objects.get(name="Warehouse"))
        # Cashier role does not.
        cls.cashier = User.objects.create_user("ca@hexagare.test", "pw-Testing-123")
        cls.cashier.groups.add(Group.objects.get(name="Cashier"))

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.wh_user)
        self.unit_a = create_unit(variant=self.variant, location=self.warehouse, status="AVAILABLE")
        self.unit_b = create_unit(variant=self.variant, location=self.warehouse, status="AVAILABLE")

    def _open_transfer(self):
        res = self.client.post(
            "/api/v1/inventory/transfers/",
            {"from_location": self.warehouse.id, "to_location": self.offline.id, "note": "restock"},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        return res.data["id"]

    def bucket(self, location, status):
        row = InventoryBalance.objects.filter(
            variant=self.variant, location=location, status=status
        ).first()
        return row.quantity if row else 0

    def test_requires_inventory_transfer_permission(self):
        client = APIClient()
        client.force_authenticate(user=self.cashier)
        res = client.post(
            "/api/v1/inventory/transfers/",
            {"from_location": self.warehouse.id, "to_location": self.offline.id},
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_same_source_and_destination_is_rejected(self):
        res = self.client.post(
            "/api/v1/inventory/transfers/",
            {"from_location": self.warehouse.id, "to_location": self.warehouse.id},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_full_flow_scan_then_receive(self):
        transfer_id = self._open_transfer()

        scan = self.client.post(
            f"/api/v1/inventory/transfers/{transfer_id}/scan/",
            {"serial": self.unit_a.serial_number},
            format="json",
        )
        self.assertEqual(scan.status_code, 201, scan.data)
        self.unit_a.refresh_from_db()
        self.assertEqual(self.unit_a.status, SerializedUnit.Status.IN_TRANSIT)
        self.assertEqual(self.bucket(self.warehouse, "IN_TRANSIT"), 1)
        self.assertEqual(self.bucket(self.warehouse, "AVAILABLE"), 1)  # unit_b still here

        received = self.client.post(f"/api/v1/inventory/transfers/{transfer_id}/receive/")
        self.assertEqual(received.status_code, 200)
        self.assertEqual(received.data["status"], "COMPLETED")
        self.unit_a.refresh_from_db()
        self.assertEqual(self.unit_a.status, SerializedUnit.Status.AVAILABLE)
        self.assertEqual(self.unit_a.location, self.offline)
        self.assertEqual(self.bucket(self.offline, "AVAILABLE"), 1)
        self.assertEqual(self.bucket(self.warehouse, "IN_TRANSIT"), 0)

    def test_scan_rejects_a_unit_not_at_the_source(self):
        transfer_id = self._open_transfer()
        other = create_unit(variant=self.variant, location=self.offline, status="AVAILABLE")
        res = self.client.post(
            f"/api/v1/inventory/transfers/{transfer_id}/scan/",
            {"serial": other.serial_number},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        # The specific reason must reach the client under error.fields.serial,
        # not just the generic "Validation failed." envelope message.
        self.assertIn("error", res.data)
        message = res.data["error"]["fields"]["serial"][0]
        self.assertIn(other.serial_number, message)
        self.assertIn("Offline", message)  # where it actually is
        self.assertIn("Warehouse", message)  # the transfer's source

    def test_scan_rejects_a_non_available_unit(self):
        transfer_id = self._open_transfer()
        create_unit(variant=self.variant, location=self.warehouse, status="GENERATED")
        generated = SerializedUnit.objects.filter(status="GENERATED").first()
        res = self.client.post(
            f"/api/v1/inventory/transfers/{transfer_id}/scan/",
            {"serial": generated.serial_number},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_scan_rejects_an_unknown_serial(self):
        transfer_id = self._open_transfer()
        res = self.client.post(
            f"/api/v1/inventory/transfers/{transfer_id}/scan/",
            {"serial": "HXNOPE-000999"},
            format="json",
        )
        self.assertEqual(res.status_code, 404)

    def test_scan_twice_rejects_duplicate(self):
        transfer_id = self._open_transfer()
        payload = {"serial": self.unit_a.serial_number}
        self.client.post(f"/api/v1/inventory/transfers/{transfer_id}/scan/", payload, format="json")
        again = self.client.post(
            f"/api/v1/inventory/transfers/{transfer_id}/scan/", payload, format="json"
        )
        self.assertEqual(again.status_code, 400)

    def test_cancel_returns_units_to_source(self):
        transfer_id = self._open_transfer()
        self.client.post(
            f"/api/v1/inventory/transfers/{transfer_id}/scan/",
            {"serial": self.unit_a.serial_number},
            format="json",
        )
        cancelled = self.client.post(f"/api/v1/inventory/transfers/{transfer_id}/cancel/")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.data["status"], "CANCELLED")
        self.unit_a.refresh_from_db()
        self.assertEqual(self.unit_a.status, SerializedUnit.Status.AVAILABLE)
        self.assertEqual(self.unit_a.location, self.warehouse)
        self.assertEqual(self.bucket(self.warehouse, "AVAILABLE"), 2)

    def test_cannot_scan_onto_a_completed_transfer(self):
        transfer_id = self._open_transfer()
        self.client.post(
            f"/api/v1/inventory/transfers/{transfer_id}/scan/",
            {"serial": self.unit_a.serial_number},
            format="json",
        )
        self.client.post(f"/api/v1/inventory/transfers/{transfer_id}/receive/")
        res = self.client.post(
            f"/api/v1/inventory/transfers/{transfer_id}/scan/",
            {"serial": self.unit_b.serial_number},
            format="json",
        )
        self.assertEqual(res.status_code, 400)

    def test_transfer_list_is_enveloped(self):
        self._open_transfer()
        res = self.client.get("/api/v1/inventory/transfers/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("data", res.data)
        self.assertIn("meta", res.data)
        self.assertEqual(res.data["data"][0]["status"], StockTransfer.Status.OPEN)
