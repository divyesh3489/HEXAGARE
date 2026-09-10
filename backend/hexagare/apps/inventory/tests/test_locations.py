"""Location bootstrap + read-only API (Phase 3; full ledger is Phase 4)."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.rbac import ensure_role_groups
from apps.inventory.models import Location

User = get_user_model()


class LocationBootstrapTests(TestCase):
    def test_reference_locations_are_seeded_by_post_migrate(self):
        codes = set(Location.objects.values_list("code", flat=True))
        self.assertTrue({"warehouse", "amazon", "offline"} <= codes)
        self.assertEqual(Location.objects.get(code="amazon").kind, Location.Kind.MARKETPLACE)


class LocationApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.viewer = User.objects.create_user("wh@hexagare.test", "pw-Testing-123")
        cls.viewer.groups.add(Group.objects.get(name="Warehouse"))  # inventory.view
        # No groups -> no operational permissions at all.
        cls.outsider = User.objects.create_user("cx@hexagare.test", "pw-Testing-123")

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_list_uses_pagination_envelope(self):
        res = self.client_for(self.viewer).get("/api/v1/inventory/locations/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("data", res.data)
        self.assertIn("meta", res.data)
        self.assertGreaterEqual(res.data["meta"]["count"], 3)

    def test_kind_filter(self):
        res = self.client_for(self.viewer).get(
            "/api/v1/inventory/locations/", {"kind": "warehouse"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(all(row["kind"] == "warehouse" for row in res.data["data"]))

    def test_requires_inventory_view(self):
        res = self.client_for(self.outsider).get("/api/v1/inventory/locations/")
        self.assertEqual(res.status_code, 403)

    def test_is_read_only(self):
        res = self.client_for(self.viewer).post(
            "/api/v1/inventory/locations/", {"name": "New WH", "code": "new-wh"}, format="json"
        )
        self.assertEqual(res.status_code, 405)
