"""Sale/SaleLine API -- RBAC, filters, line mutations, and totals wiring."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import OperationalPermission
from apps.accounts.rbac import ensure_role_groups
from apps.customers.models import Customer
from apps.products.models import Category, Product, ProductVariant
from apps.sales.models import Sale, SaleLine, SalesChannel

User = get_user_model()


class SalesApiTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.cashier = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.cashier.groups.add(Group.objects.get(name="Cashier"))

        # No seed role holds sales.view without orders.manage -- grant it directly
        # to exercise the read/write split.
        cls.viewer = User.objects.create_user("viewer@hexagare.test", "pw-Testing-123")
        content_type = ContentType.objects.get_for_model(OperationalPermission)
        cls.viewer.user_permissions.add(
            Permission.objects.get(content_type=content_type, codename="sales.view")
        )

        cls.outsider = User.objects.create_user("outsider@hexagare.test", "pw-Testing-123")

        category = Category.objects.create(name="Mouse Pads", code="MP")
        cls.product = Product.objects.create(
            name="Pad",
            category=category,
            status=Product.Status.ACTIVE,
            mrp=Decimal("1180.00"),
            selling_price=Decimal("1180.00"),
            tax_rate=Decimal("18.00"),
        )
        cls.variant = ProductVariant.objects.create(
            product=cls.product, sku="HEX-MP-A-001", code="A"
        )
        cls.discontinued_product = Product.objects.create(
            name="Old Pad",
            category=category,
            status=Product.Status.DISCONTINUED,
            selling_price=Decimal("500.00"),
            tax_rate=Decimal("18.00"),
        )
        cls.discontinued_variant = ProductVariant.objects.create(
            product=cls.discontinued_product, sku="HEX-MP-B-001", code="B"
        )
        cls.amazon = SalesChannel.objects.get(code="AMAZON")
        cls.offline = SalesChannel.objects.get(code="OFFLINE")

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client


class RbacTests(SalesApiTestBase):
    def test_list_requires_sales_view(self):
        res = self.client_for(self.outsider).get("/api/v1/sales/")
        self.assertEqual(res.status_code, 403)

    def test_view_only_user_can_read_but_not_create(self):
        res = self.client_for(self.viewer).get("/api/v1/sales/")
        self.assertEqual(res.status_code, 200)

        res = self.client_for(self.viewer).post(
            "/api/v1/sales/", {"sales_channel": self.offline.pk}, format="json"
        )
        self.assertEqual(res.status_code, 403)

    def test_cashier_can_create_and_manage(self):
        res = self.client_for(self.cashier).post(
            "/api/v1/sales/", {"sales_channel": self.offline.pk}, format="json"
        )
        self.assertEqual(res.status_code, 201)


class ListFilterTests(SalesApiTestBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.amazon_sale = Sale.objects.create(sales_channel=cls.amazon, status=Sale.Status.PENDING)
        cls.offline_sale = Sale.objects.create(sales_channel=cls.offline, status=Sale.Status.DRAFT)

    def test_uses_pagination_envelope(self):
        res = self.client_for(self.cashier).get("/api/v1/sales/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("data", res.data)
        self.assertIn("meta", res.data)

    def test_filter_by_channel(self):
        res = self.client_for(self.cashier).get("/api/v1/sales/", {"channel": "AMAZON"})
        ids = {row["id"] for row in res.data["data"]}
        self.assertIn(self.amazon_sale.pk, ids)
        self.assertNotIn(self.offline_sale.pk, ids)

    def test_filter_by_status(self):
        res = self.client_for(self.cashier).get("/api/v1/sales/", {"status": "DRAFT"})
        ids = {row["id"] for row in res.data["data"]}
        self.assertIn(self.offline_sale.pk, ids)
        self.assertNotIn(self.amazon_sale.pk, ids)


class CreateWithNestedLinesTests(SalesApiTestBase):
    def test_create_with_lines_snapshots_pricing_and_recalculates_totals(self):
        res = self.client_for(self.cashier).post(
            "/api/v1/sales/",
            {
                "sales_channel": self.offline.pk,
                "lines": [{"variant": self.variant.pk, "quantity": 2}],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(len(res.data["lines"]), 1)
        line = res.data["lines"][0]
        self.assertEqual(Decimal(line["unit_price"]), Decimal("1180.00"))
        self.assertEqual(Decimal(res.data["grand_total"]), Decimal("2360.00"))
        self.assertEqual(Decimal(res.data["tax_total"]), Decimal("360.00"))

    def test_cannot_add_a_non_active_variant(self):
        res = self.client_for(self.cashier).post(
            "/api/v1/sales/",
            {
                "sales_channel": self.offline.pk,
                "lines": [{"variant": self.discontinued_variant.pk, "quantity": 1}],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)


class LineMutationTests(SalesApiTestBase):
    def setUp(self):
        self.sale = Sale.objects.create(sales_channel=self.offline)

    def test_add_line_recalculates_totals(self):
        res = self.client_for(self.cashier).post(
            f"/api/v1/sales/{self.sale.pk}/lines/",
            {"variant": self.variant.pk, "quantity": 1},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(Decimal(res.data["grand_total"]), Decimal("1180.00"))

    def test_update_line_quantity_recalculates_totals(self):
        line = SaleLine.objects.create(
            sale=self.sale, variant=self.variant, quantity=1,
            unit_price=Decimal("1180.00"), tax_rate=Decimal("18.00"),
        )
        res = self.client_for(self.cashier).patch(
            f"/api/v1/sales/{self.sale.pk}/lines/{line.pk}/",
            {"quantity": 3},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(Decimal(res.data["grand_total"]), Decimal("3540.00"))

    def test_remove_line_recalculates_totals(self):
        line = SaleLine.objects.create(
            sale=self.sale, variant=self.variant, quantity=1,
            unit_price=Decimal("1180.00"), tax_rate=Decimal("18.00"),
        )
        res = self.client_for(self.cashier).delete(
            f"/api/v1/sales/{self.sale.pk}/lines/{line.pk}/"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(Decimal(res.data["grand_total"]), Decimal("0.00"))
        self.assertFalse(SaleLine.objects.filter(pk=line.pk).exists())

    def test_lines_cannot_be_edited_once_not_draft(self):
        self.sale.status = Sale.Status.COMPLETED
        self.sale.save(update_fields=["status"])
        res = self.client_for(self.cashier).post(
            f"/api/v1/sales/{self.sale.pk}/lines/",
            {"variant": self.variant.pk, "quantity": 1},
            format="json",
        )
        self.assertEqual(res.status_code, 400)


class CancelTests(SalesApiTestBase):
    def test_cancel_sets_status(self):
        sale = Sale.objects.create(sales_channel=self.offline)
        res = self.client_for(self.cashier).post(f"/api/v1/sales/{sale.pk}/cancel/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "CANCELLED")

    def test_cannot_cancel_an_already_completed_sale(self):
        sale = Sale.objects.create(sales_channel=self.offline, status=Sale.Status.COMPLETED)
        res = self.client_for(self.cashier).post(f"/api/v1/sales/{sale.pk}/cancel/")
        self.assertEqual(res.status_code, 400)


class CustomerAttachTests(SalesApiTestBase):
    def setUp(self):
        self.sale = Sale.objects.create(sales_channel=self.offline)
        self.customer = Customer.objects.create(name="Rahul Sharma", type=Customer.Type.REGISTERED)

    def test_attach_customer(self):
        res = self.client_for(self.cashier).post(
            f"/api/v1/sales/{self.sale.pk}/customer/",
            {"customer": self.customer.pk},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["customer"], self.customer.pk)
        self.assertEqual(res.data["customer_name"], "Rahul Sharma")

    def test_clear_customer(self):
        self.sale.customer = self.customer
        self.sale.save(update_fields=["customer"])
        res = self.client_for(self.cashier).post(
            f"/api/v1/sales/{self.sale.pk}/customer/", {"customer": None}, format="json"
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIsNone(res.data["customer"])
        self.assertIsNone(res.data["customer_name"])

    def test_create_with_customer(self):
        res = self.client_for(self.cashier).post(
            "/api/v1/sales/",
            {"sales_channel": self.offline.pk, "customer": self.customer.pk},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["customer"], self.customer.pk)

    def test_attaching_customer_requires_orders_manage(self):
        res = self.client_for(self.viewer).post(
            f"/api/v1/sales/{self.sale.pk}/customer/",
            {"customer": self.customer.pk},
            format="json",
        )
        self.assertEqual(res.status_code, 403)
