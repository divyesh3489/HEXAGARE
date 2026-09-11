"""Customers API (Phase 11) -- CRUD, search, RBAC, delete-guard."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.rbac import ensure_role_groups
from apps.customers.models import Customer
from apps.sales.models import Sale, SalesChannel

User = get_user_model()


class CustomersApiTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.cashier = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.cashier.groups.add(Group.objects.get(name="Cashier"))
        cls.warehouse_user = User.objects.create_user("wh@hexagare.test", "pw-Testing-123")
        cls.warehouse_user.groups.add(Group.objects.get(name="Warehouse"))
        cls.offline = SalesChannel.objects.get(code="OFFLINE")

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client


class RbacTests(CustomersApiTestBase):
    def test_warehouse_role_cannot_view_customers(self):
        res = self.client_for(self.warehouse_user).get("/api/v1/customers/")
        self.assertEqual(res.status_code, 403)

    def test_cashier_can_view_and_manage(self):
        res = self.client_for(self.cashier).get("/api/v1/customers/")
        self.assertEqual(res.status_code, 200)
        res = self.client_for(self.cashier).post(
            "/api/v1/customers/", {"name": "Test Customer"}, format="json"
        )
        self.assertEqual(res.status_code, 201)


class CreateTests(CustomersApiTestBase):
    def test_create_registered_customer_with_full_fields(self):
        res = self.client_for(self.cashier).post(
            "/api/v1/customers/",
            {
                "name": "Rahul Sharma",
                "phone": "+91-98765-43210",
                "email": "rahul@example.com",
                "address": "12 MG Road, Pune",
                "gstin": "27AAAAA0000A1Z5",
                "notes": "Prefers UPI",
                "type": Customer.Type.REGISTERED,
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["type"], "REGISTERED")
        self.assertEqual(res.data["gstin"], "27AAAAA0000A1Z5")

    def test_walk_in_needs_only_a_name(self):
        res = self.client_for(self.cashier).post(
            "/api/v1/customers/",
            {"name": "Walk-in — Counter", "type": Customer.Type.WALK_IN},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["phone"], "")
        self.assertEqual(res.data["type"], "WALK_IN")

    def test_name_is_required(self):
        res = self.client_for(self.cashier).post("/api/v1/customers/", {}, format="json")
        self.assertEqual(res.status_code, 400)


class ListSearchTests(CustomersApiTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.rahul = Customer.objects.create(
            name="Rahul Sharma", phone="+91-98765-43210", type=Customer.Type.REGISTERED
        )
        cls.priya = Customer.objects.create(
            name="Priya Nair", phone="+91-90000-11111", type=Customer.Type.WALK_IN
        )

    def test_search_by_name(self):
        res = self.client_for(self.cashier).get("/api/v1/customers/", {"search": "Rahul"})
        names = {row["name"] for row in res.data["data"]}
        self.assertEqual(names, {"Rahul Sharma"})

    def test_search_by_phone(self):
        res = self.client_for(self.cashier).get("/api/v1/customers/", {"search": "90000-11111"})
        names = {row["name"] for row in res.data["data"]}
        self.assertEqual(names, {"Priya Nair"})

    def test_filter_by_type(self):
        res = self.client_for(self.cashier).get("/api/v1/customers/", {"type": "WALK_IN"})
        names = {row["name"] for row in res.data["data"]}
        self.assertEqual(names, {"Priya Nair"})


class DeleteGuardTests(CustomersApiTestBase):
    def test_customer_with_no_sales_can_be_deleted(self):
        customer = Customer.objects.create(name="No Sales")
        res = self.client_for(self.cashier).delete(f"/api/v1/customers/{customer.pk}/")
        self.assertEqual(res.status_code, 204)

    def test_customer_with_sales_history_cannot_be_deleted(self):
        customer = Customer.objects.create(name="Has Sales")
        Sale.objects.create(sales_channel=self.offline, customer=customer)
        res = self.client_for(self.cashier).delete(f"/api/v1/customers/{customer.pk}/")
        self.assertEqual(res.status_code, 400)
        self.assertTrue(Customer.objects.filter(pk=customer.pk).exists())
