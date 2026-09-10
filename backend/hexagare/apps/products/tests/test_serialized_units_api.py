"""Serialized-unit API: envelopes, RBAC, filters, transition, barcode, lookup."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.rbac import ensure_role_groups
from apps.inventory.models import Location
from apps.products.models import Category, Product, ProductVariant
from apps.products.services.serial_numbers import create_unit

User = get_user_model()
BASE = "/api/v1/products/serialized-units/"


class SerializedUnitApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        # Cashier: serials.view + barcode.scan, no serials.manage.
        cls.viewer = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.viewer.groups.add(Group.objects.get(name="Cashier"))
        # Warehouse: serials.view + serials.manage + barcode.scan.
        cls.manager = User.objects.create_user("wh@hexagare.test", "pw-Testing-123")
        cls.manager.groups.add(Group.objects.get(name="Warehouse"))

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
        cls.other_variant = ProductVariant.objects.create(
            product=cls.product, sku="HEX-MP-12X24-002", code="12X24"
        )
        cls.warehouse = Location.objects.get(code="warehouse")
        cls.offline = Location.objects.get(code="offline")

        cls.u_avail = create_unit(
            variant=cls.variant, location=cls.warehouse, status="AVAILABLE"
        )
        cls.u_gen = create_unit(variant=cls.variant, location=cls.warehouse)
        cls.u_other = create_unit(variant=cls.other_variant, location=cls.offline)

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    # -- list / envelopes / filters ---------------------------------------
    def test_list_uses_pagination_envelope(self):
        res = self.client_for(self.viewer).get(BASE)
        self.assertEqual(res.status_code, 200)
        self.assertIn("data", res.data)
        self.assertEqual(res.data["meta"]["count"], 3)
        row = res.data["data"][0]
        self.assertIn("serial_number", row)
        self.assertIn("product_name", row)
        self.assertIn("location_name", row)

    def test_filter_by_status(self):
        res = self.client_for(self.viewer).get(BASE, {"status": "AVAILABLE"})
        self.assertEqual(res.data["meta"]["count"], 1)
        self.assertEqual(res.data["data"][0]["serial_number"], self.u_avail.serial_number)

    def test_filter_by_location_and_variant(self):
        res = self.client_for(self.viewer).get(BASE, {"location": self.offline.pk})
        self.assertEqual(res.data["meta"]["count"], 1)
        res = self.client_for(self.viewer).get(BASE, {"variant": self.variant.pk})
        self.assertEqual(res.data["meta"]["count"], 2)

    def test_search_by_serial(self):
        res = self.client_for(self.viewer).get(BASE, {"search": self.u_other.serial_number})
        self.assertEqual(res.data["meta"]["count"], 1)

    # -- retrieve: full chain + pricing + history -----------------------
    def test_retrieve_returns_chain_pricing_and_events(self):
        res = self.client_for(self.viewer).get(f"{BASE}{self.u_avail.pk}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["product"]["name"], "Hexagare Mouse Pad")
        self.assertEqual(res.data["variant"]["sku"], "HEX-MP-11X23-001")
        self.assertEqual(res.data["pricing"]["gst_amount"], "180.00")
        self.assertEqual(res.data["pricing"]["base_price"], "1000.00")
        self.assertEqual(len(res.data["events"]), 1)
        self.assertIn("RESERVED", res.data["allowed_transitions"])

    # -- create ---------------------------------------------------------
    def test_create_allocates_a_serial(self):
        res = self.client_for(self.manager).post(
            BASE,
            {"variant": self.variant.pk, "location": self.warehouse.pk, "status": "AVAILABLE"},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data["serial_number"].startswith("HX11X23-"))
        self.assertEqual(res.data["status"], "AVAILABLE")

    def test_create_rejects_non_initial_status(self):
        res = self.client_for(self.manager).post(
            BASE,
            {"variant": self.variant.pk, "location": self.warehouse.pk, "status": "SOLD"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["error"]["code"], "validation_error")

    def test_viewer_cannot_create(self):
        res = self.client_for(self.viewer).post(
            BASE, {"variant": self.variant.pk, "location": self.warehouse.pk}, format="json"
        )
        self.assertEqual(res.status_code, 403)

    def test_put_and_delete_are_not_allowed(self):
        c = self.client_for(self.manager)
        self.assertEqual(c.put(f"{BASE}{self.u_avail.pk}/", {}, format="json").status_code, 405)
        self.assertEqual(c.delete(f"{BASE}{self.u_avail.pk}/").status_code, 405)

    # -- transition ---------------------------------------------------
    def test_transition_valid(self):
        res = self.client_for(self.manager).post(
            f"{BASE}{self.u_avail.pk}/transition/",
            {"status": "RESERVED", "note": "order #1"},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["status"], "RESERVED")
        self.assertEqual(res.data["events"][0]["to_status"], "RESERVED")

    def test_transition_invalid_returns_error_envelope(self):
        res = self.client_for(self.manager).post(
            f"{BASE}{self.u_gen.pk}/transition/", {"status": "SOLD"}, format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["error"]["code"], "validation_error")
        self.assertIn("status", res.data["error"]["fields"])

    def test_transition_requires_manage(self):
        res = self.client_for(self.viewer).post(
            f"{BASE}{self.u_avail.pk}/transition/", {"status": "RESERVED"}, format="json"
        )
        self.assertEqual(res.status_code, 403)

    # -- barcode ----------------------------------------------------
    def test_barcode_returns_png(self):
        res = self.client_for(self.viewer).get(f"{BASE}{self.u_avail.pk}/barcode/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "image/png")
        self.assertEqual(res.content[:8], b"\x89PNG\r\n\x1a\n")

    # -- lookup (rule 4) -----------------------------------------
    def test_lookup_by_serial_returns_full_chain(self):
        res = self.client_for(self.viewer).get(
            f"{BASE}lookup/", {"code": self.u_avail.serial_number.lower()}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["serial_number"], self.u_avail.serial_number)
        self.assertEqual(res.data["product"]["name"], "Hexagare Mouse Pad")
        self.assertEqual(res.data["variant"]["sku"], "HEX-MP-11X23-001")
        self.assertIn("pricing", res.data)
        self.assertIn("events", res.data)
        self.assertEqual(res.data["location_name"], "Warehouse")

    def test_lookup_unknown_returns_404_envelope(self):
        res = self.client_for(self.viewer).get(f"{BASE}lookup/", {"code": "HX-NOPE-000001"})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.data["error"]["code"], "not_found")

    def test_lookup_requires_barcode_scan_permission(self):
        stranger = User.objects.create_user("mgr2@hexagare.test", "pw-Testing-123")
        # Manager role lacks nothing here, so use a bare user with no groups.
        res = self.client_for(stranger).get(
            f"{BASE}lookup/", {"code": self.u_avail.serial_number}
        )
        self.assertEqual(res.status_code, 403)
