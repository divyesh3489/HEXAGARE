"""Catalog API: envelopes, per-action RBAC, nested writes, image upload."""

import io
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.rbac import ensure_role_groups
from apps.products.models import (
    Category,
    Product,
    ProductAttribute,
    ProductVariant,
)

User = get_user_model()


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (1, 1), "white").save(buf, format="PNG")
    return buf.getvalue()


class CatalogApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.viewer = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.viewer.groups.add(Group.objects.get(name="Cashier"))  # products.view only
        cls.manager = User.objects.create_user("manager@hexagare.test", "pw-Testing-123")
        cls.manager.groups.add(Group.objects.get(name="Manager"))  # products.manage
        cls.category = Category.objects.create(name="Mouse Pads", code="MP")
        cls.product = Product.objects.create(
            name="Hexagare Mouse Pad", category=cls.category, code="MP"
        )

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    # -- envelopes ------------------------------------------------------------
    def test_list_uses_pagination_envelope(self):
        res = self.client_for(self.viewer).get("/api/v1/products/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("data", res.data)
        self.assertIn("meta", res.data)
        self.assertEqual(res.data["meta"]["count"], 1)

    def test_duplicate_sku_returns_error_envelope(self):
        ProductVariant.objects.create(
            product=self.product,
            sku="HEX-MP-A-001",
            mrp=Decimal("1000"),
            selling_price=Decimal("1000"),
        )
        res = self.client_for(self.manager).post(
            "/api/v1/products/variants/",
            {
                "product": self.product.pk,
                "sku": "HEX-MP-A-001",
                "mrp": "1000.00",
                "selling_price": "1180.00",
                "tax_rate": "18.00",
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["error"]["code"], "validation_error")
        self.assertIn("sku", res.data["error"]["fields"])

    # -- RBAC ---------------------------------------------------------------
    def test_viewer_can_read_but_not_write(self):
        viewer = self.client_for(self.viewer)
        self.assertEqual(viewer.get("/api/v1/products/categories/").status_code, 200)
        res = viewer.post("/api/v1/products/categories/", {"name": "New"}, format="json")
        self.assertEqual(res.status_code, 403)

    def test_manager_can_create_product(self):
        res = self.client_for(self.manager).post(
            "/api/v1/products/",
            {"name": "Desk Mat", "category": self.category.pk, "status": "active"},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)

    # -- SKU endpoints ----------------------------------------------------
    def test_sku_suggest_endpoint(self):
        res = self.client_for(self.manager).post(
            "/api/v1/products/sku/suggest/",
            {"product": self.product.pk, "variant_code": "11x23"},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["sku"], "HEX-MP-11X23-001")

    def test_sku_check_endpoint(self):
        res = self.client_for(self.viewer).get(
            "/api/v1/products/sku/check/", {"sku": "HEX-MP-FREE-001"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["available"])

    # -- variant with nested attribute values ---------------------------
    def test_variant_create_autofills_sku_and_nested_values(self):
        size = ProductAttribute.objects.create(name="Size", code="size")
        res = self.client_for(self.manager).post(
            "/api/v1/products/variants/",
            {
                "product": self.product.pk,
                "mrp": "1500.00",
                "selling_price": "1180.00",
                "tax_rate": "18.00",
                "attribute_values": [{"attribute": size.pk, "value": "11 x 23 inch"}],
            },
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data["sku"].startswith("HEX-MP-"))
        self.assertEqual(res.data["base_price"], "1000.00")
        self.assertEqual(res.data["gst_amount"], "180.00")
        self.assertEqual(len(res.data["attribute_values"]), 1)

        variant_id = res.data["id"]
        patch = self.client_for(self.manager).patch(
            f"/api/v1/products/variants/{variant_id}/",
            {"attribute_values": [{"attribute": size.pk, "value": "12 x 32 inch"}]},
            format="json",
        )
        self.assertEqual(patch.status_code, 200, patch.data)
        self.assertEqual(patch.data["attribute_values"][0]["value"], "12 x 32 inch")

    # -- pricing inheritance (ADR-005) ---------------------------------
    def test_variant_inherits_product_pricing_when_prices_omitted(self):
        priced = Product.objects.create(
            name="Priced Pad",
            category=self.category,
            mrp="1500.00",
            selling_price="1180.00",
            tax_rate="18.00",
        )
        res = self.client_for(self.manager).post(
            "/api/v1/products/variants/",
            {"product": priced.pk, "sku": "HEX-MP-INH-001"},
            format="json",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertIsNone(res.data["selling_price"])
        self.assertEqual(res.data["effective_selling_price"], "1180.00")
        self.assertEqual(res.data["base_price"], "1000.00")
        self.assertEqual(res.data["gst_amount"], "180.00")
        self.assertEqual(res.data["discount_amount"], "320.00")

    def test_variant_price_override_then_revert_to_inherit(self):
        priced = Product.objects.create(
            name="Priced Pad 2",
            category=self.category,
            mrp="1500.00",
            selling_price="1180.00",
            tax_rate="18.00",
        )
        client = self.client_for(self.manager)
        vid = client.post(
            "/api/v1/products/variants/",
            {"product": priced.pk, "sku": "HEX-MP-OVR-001"},
            format="json",
        ).data["id"]

        overridden = client.patch(
            f"/api/v1/products/variants/{vid}/",
            {"selling_price": "2360.00"},
            format="json",
        )
        self.assertEqual(overridden.data["selling_price"], "2360.00")
        self.assertEqual(overridden.data["effective_selling_price"], "2360.00")
        self.assertEqual(overridden.data["base_price"], "2000.00")

        reverted = client.patch(
            f"/api/v1/products/variants/{vid}/",
            {"selling_price": None},
            format="json",
        )
        self.assertIsNone(reverted.data["selling_price"])
        self.assertEqual(reverted.data["effective_selling_price"], "1180.00")

    def test_variant_without_resolvable_price_is_rejected(self):
        # self.product has no default pricing.
        res = self.client_for(self.manager).post(
            "/api/v1/products/variants/",
            {"product": self.product.pk, "sku": "HEX-MP-NOPRICE-001"},
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        fields = res.data["error"]["fields"]
        self.assertIn("selling_price", fields)
        self.assertIn("mrp", fields)

    # -- availability follows product status (ADR-006) ------------------
    def test_variant_effective_status_follows_product(self):
        active = Product.objects.create(
            name="Live Pad",
            category=self.category,
            status="active",
            mrp="1000.00",
            selling_price="1000.00",
        )
        client = self.client_for(self.manager)
        vid = client.post(
            "/api/v1/products/variants/",
            {"product": active.pk, "sku": "HEX-MP-LIVE-001", "is_active": True},
            format="json",
        ).data["id"]

        row = client.get(f"/api/v1/products/variants/{vid}/").data
        self.assertEqual(row["effective_status"], "active")
        self.assertTrue(row["is_available"])

        # Deactivate the variant -> inactive, not available.
        row = client.patch(
            f"/api/v1/products/variants/{vid}/", {"is_active": False}, format="json"
        ).data
        self.assertEqual(row["effective_status"], "inactive")
        self.assertFalse(row["is_available"])

        # Discontinue the product -> variant reads discontinued regardless.
        client.patch(f"/api/v1/products/{active.pk}/", {"status": "discontinued"}, format="json")
        row = client.get(f"/api/v1/products/variants/{vid}/").data
        self.assertEqual(row["effective_status"], "discontinued")
        self.assertFalse(row["is_available"])

    def test_available_filter_and_count(self):
        active = Product.objects.create(
            name="Sellable", category=self.category, status="active",
            mrp="1000.00", selling_price="1000.00",
        )
        ProductVariant.objects.create(product=active, sku="HEX-S-1", is_active=True)
        ProductVariant.objects.create(product=active, sku="HEX-S-2", is_active=False)
        draft = Product.objects.create(
            name="Draft", category=self.category, status="draft",
            mrp="1000.00", selling_price="1000.00",
        )
        ProductVariant.objects.create(product=draft, sku="HEX-D-1", is_active=True)

        client = self.client_for(self.viewer)
        avail = client.get("/api/v1/products/variants/", {"available": "1"})
        self.assertEqual([v["sku"] for v in avail.data["data"]], ["HEX-S-1"])

        rows = {p["name"]: p for p in client.get("/api/v1/products/").data["data"]}
        self.assertEqual(rows["Sellable"]["available_variant_count"], 1)
        self.assertEqual(rows["Draft"]["available_variant_count"], 0)  # draft -> 0

    # -- image upload -----------------------------------------------------
    def test_image_upload_multipart(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile("pad.png", _png_bytes(), content_type="image/png")
        res = self.client_for(self.manager).post(
            "/api/v1/products/images/",
            {"product": self.product.pk, "image": upload, "is_primary": "true"},
            format="multipart",
        )
        self.assertEqual(res.status_code, 201, res.data)
        # Storage-relative, never an absolute URL carrying the request host
        # (which is the container name behind the dev proxy).
        self.assertTrue(res.data["image_url"].startswith("/media/"))

    def test_variant_scoped_image_round_trips(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        variant = ProductVariant.objects.create(
            product=self.product,
            sku="HEX-MP-IMG-001",
            mrp=Decimal("1000"),
            selling_price=Decimal("1000"),
        )
        client = self.client_for(self.manager)
        res = client.post(
            "/api/v1/products/images/",
            {
                "product": self.product.pk,
                "variant": variant.pk,
                "image": SimpleUploadedFile("v.png", _png_bytes(), content_type="image/png"),
            },
            format="multipart",
        )
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(res.data["variant"], variant.pk)

        by_variant = client.get("/api/v1/products/images/", {"variant": variant.pk})
        self.assertEqual(by_variant.data["meta"]["count"], 1)

    def test_image_variant_must_belong_to_product(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        other_product = Product.objects.create(name="Other", category=self.category)
        foreign_variant = ProductVariant.objects.create(
            product=other_product,
            sku="HEX-MP-OTHER-001",
            mrp=Decimal("1000"),
            selling_price=Decimal("1000"),
        )
        res = self.client_for(self.manager).post(
            "/api/v1/products/images/",
            {
                "product": self.product.pk,
                "variant": foreign_variant.pk,
                "image": SimpleUploadedFile("x.png", _png_bytes(), content_type="image/png"),
            },
            format="multipart",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["error"]["code"], "validation_error")
        self.assertIn("variant", res.data["error"]["fields"])

    # -- filtering ------------------------------------------------------
    def test_product_list_filters(self):
        other = Category.objects.create(name="Cables", code="CB")
        Product.objects.create(name="USB-C Cable", category=other, status="active")
        client = self.client_for(self.viewer)
        by_cat = client.get("/api/v1/products/", {"category": other.pk})
        self.assertEqual(by_cat.data["meta"]["count"], 1)
        by_search = client.get("/api/v1/products/", {"search": "Mouse"})
        self.assertEqual(by_search.data["meta"]["count"], 1)
