"""Amazon integration API: upload -> async import (Celery eager), history,
RBAC, and SKU-mapping / fee-config / settlement CRUD."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.rbac import ensure_role_groups
from apps.integrations.amazon.models import AmazonFeeConfig, AmazonImportBatch, AmazonSkuMapping
from apps.inventory.models import Location
from apps.products.models import Category, Product, ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import create_unit
from apps.sales.models import Sale, SalesChannel

User = get_user_model()

HEADER = (
    "order_id,order_date,order_status,amazon_sku,quantity,selling_price,gst_amount,"
    "referral_fee,closing_fee,fulfillment_fee,shipping_cost,advertising_cost,other_charges,"
    "refund_amount"
)


class IntegrationsTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.admin = User.objects.create_user(
            "admin@hexagare.test", "pw-Testing-123", is_staff=True
        )
        cls.admin.groups.add(Group.objects.get(name="Admin"))
        cls.cashier = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.cashier.groups.add(Group.objects.get(name="Cashier"))

        cls.channel = SalesChannel.objects.get(code="AMAZON")
        cls.amazon_location = Location.objects.get(code="amazon")
        category = Category.objects.create(name="Mouse Pads", code="MP")
        cls.product = Product.objects.create(
            name="Pad", category=category, status=Product.Status.ACTIVE
        )
        cls.variant = ProductVariant.objects.create(
            product=cls.product, sku="HEX-MP-A-001", code="A"
        )

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def csv_file(self, *rows: str) -> SimpleUploadedFile:
        content = (HEADER + "\n" + "\n".join(rows) + "\n").encode()
        return SimpleUploadedFile("orders.csv", content, content_type="text/csv")

    def row(self, order_id, status, sku=None):
        return (
            f"{order_id},2026-01-10,{status},{sku or self.variant.sku},1,1180.00,180.00,"
            "150.00,20.00,80.00,80.00,50.00,10.00,0.00"
        )


class ImportUploadTests(IntegrationsTestBase):
    BASE = "/api/v1/integrations/amazon/imports/"

    def test_upload_imports_synchronously_under_celery_eager(self):
        create_unit(
            variant=self.variant,
            location=self.amazon_location,
            status=SerializedUnit.Status.AVAILABLE,
        )
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client_for(self.admin).post(
                self.BASE, {"file": self.csv_file(self.row("AMZ-1", "Shipped"))}, format="multipart"
            )
        self.assertEqual(res.status_code, 201, res.data)
        batch = AmazonImportBatch.objects.get(pk=res.data["id"])
        self.assertEqual(batch.status, AmazonImportBatch.Status.READY)
        self.assertEqual(batch.orders_created, 1)
        self.assertTrue(Sale.objects.filter(external_reference="AMZ-1").exists())

    def test_failed_order_is_reported_in_the_error_log(self):
        # No stock at the amazon location -> the only order fails, batch is FAILED
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client_for(self.admin).post(
                self.BASE, {"file": self.csv_file(self.row("AMZ-1", "Shipped"))}, format="multipart"
            )
        self.assertEqual(res.status_code, 201, res.data)
        detail = self.client_for(self.admin).get(f"{self.BASE}{res.data['id']}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["status"], AmazonImportBatch.Status.FAILED)
        self.assertEqual(len(detail.data["error_log"]), 1)

    def test_history_list_is_paginated(self):
        res = self.client_for(self.admin).get(self.BASE)
        self.assertEqual(res.status_code, 200)
        self.assertIn("data", res.data)
        self.assertIn("meta", res.data)

    def test_cashier_is_denied(self):
        res = self.client_for(self.cashier).get(self.BASE)
        self.assertEqual(res.status_code, 403)

        res = self.client_for(self.cashier).post(
            self.BASE, {"file": self.csv_file(self.row("AMZ-1", "Shipped"))}, format="multipart"
        )
        self.assertEqual(res.status_code, 403)


class SkuMappingApiTests(IntegrationsTestBase):
    BASE = "/api/v1/integrations/amazon/sku-mappings/"

    def test_admin_can_crud(self):
        res = self.client_for(self.admin).post(
            self.BASE, {"amazon_sku": "AMZ-SKU-X", "variant": self.variant.pk}
        )
        self.assertEqual(res.status_code, 201, res.data)
        mapping_id = res.data["id"]

        res = self.client_for(self.admin).patch(
            f"{self.BASE}{mapping_id}/", {"is_active": False}
        )
        self.assertEqual(res.status_code, 200)
        self.assertFalse(AmazonSkuMapping.objects.get(pk=mapping_id).is_active)

        res = self.client_for(self.admin).delete(f"{self.BASE}{mapping_id}/")
        self.assertEqual(res.status_code, 204)

    def test_cashier_is_denied(self):
        res = self.client_for(self.cashier).get(self.BASE)
        self.assertEqual(res.status_code, 403)


class FeeConfigApiTests(IntegrationsTestBase):
    BASE = "/api/v1/integrations/amazon/fee-config/"

    def test_admin_can_create_a_fee_rule(self):
        res = self.client_for(self.admin).post(
            self.BASE,
            {
                "fee_name": AmazonFeeConfig.FeeName.REFERRAL,
                "fee_type": AmazonFeeConfig.FeeType.PERCENTAGE,
                "value": "15.00",
                "sales_channel": self.channel.pk,
                "effective_from": "2026-01-01",
            },
        )
        self.assertEqual(res.status_code, 201, res.data)

    def test_product_and_category_together_is_rejected(self):
        res = self.client_for(self.admin).post(
            self.BASE,
            {
                "fee_name": AmazonFeeConfig.FeeName.REFERRAL,
                "fee_type": AmazonFeeConfig.FeeType.FIXED,
                "value": "10.00",
                "sales_channel": self.channel.pk,
                "applicable_category": self.product.category_id,
                "applicable_product": self.product.pk,
                "effective_from": "2026-01-01",
            },
        )
        self.assertEqual(res.status_code, 400)
