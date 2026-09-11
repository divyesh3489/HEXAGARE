"""SalesChannel bootstrap + read API."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.rbac import ensure_role_groups
from apps.sales.models import SalesChannel

User = get_user_model()


class SalesChannelBootstrapTests(TestCase):
    def test_reference_channels_are_seeded_by_post_migrate(self):
        codes = set(SalesChannel.objects.values_list("code", flat=True))
        self.assertTrue({"AMAZON", "OFFLINE"} <= codes)
        self.assertTrue(SalesChannel.objects.get(code="AMAZON").is_active)


class SalesChannelApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.reader = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.reader.groups.add(Group.objects.get(name="Cashier"))
        cls.outsider = User.objects.create_user("outsider@hexagare.test", "pw-Testing-123")

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def test_list_uses_pagination_envelope(self):
        res = self.client_for(self.reader).get("/api/v1/sales/channels/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("data", res.data)
        self.assertIn("meta", res.data)
        self.assertGreaterEqual(res.data["meta"]["count"], 2)

    def test_requires_sales_view(self):
        res = self.client_for(self.outsider).get("/api/v1/sales/channels/")
        self.assertEqual(res.status_code, 403)
