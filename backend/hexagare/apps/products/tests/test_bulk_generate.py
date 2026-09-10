"""Phase 5 -- bulk unit generation + label batches.

Covers the atomic all-or-nothing guarantee, serial continuity, RBAC, the async
PDF render (Celery eager), the history list, ``regenerate``, the authenticated
PDF download, and the next-serial preview.
"""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.rbac import ensure_role_groups
from apps.inventory.models import InventoryTransaction, Location
from apps.products.models import (
    Category,
    LabelBatch,
    LabelBatchItem,
    LabelSize,
    Product,
    ProductVariant,
    SerializedUnit,
)
from apps.products.services.serial_numbers import create_unit

User = get_user_model()
BASE = "/api/v1/products/label-batches/"


class BulkGenerateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        # Cashier: serials.view, no serials.manage.
        cls.viewer = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.viewer.groups.add(Group.objects.get(name="Cashier"))
        # Warehouse: serials.view + serials.manage.
        cls.operator = User.objects.create_user("wh@hexagare.test", "pw-Testing-123")
        cls.operator.groups.add(Group.objects.get(name="Warehouse"))

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
        cls.warehouse = Location.objects.get(code="warehouse")
        cls.label_size = LabelSize.objects.get(code="a4-24up")

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def _payload(self, **overrides):
        payload = {
            "variant": self.variant.id,
            "location": self.warehouse.id,
            "quantity": 5,
            "label_size": self.label_size.id,
        }
        payload.update(overrides)
        return payload

    def _generate(self, **overrides):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client_for(self.operator).post(
                BASE, self._payload(**overrides), format="json"
            )

    # -- happy path ------------------------------------------------------
    def test_generate_creates_units_ledger_and_pdf(self):
        res = self._generate(quantity=5)
        self.assertEqual(res.status_code, 201, res.data)

        batch = LabelBatch.objects.get(pk=res.data["id"])
        self.assertEqual(batch.quantity, 5)
        self.assertEqual(SerializedUnit.objects.filter(variant=self.variant).count(), 5)
        self.assertEqual(LabelBatchItem.objects.filter(batch=batch).count(), 5)
        # One OPENING ledger row per unit.
        self.assertEqual(
            InventoryTransaction.objects.filter(
                kind=InventoryTransaction.Kind.OPENING,
                serialized_unit__variant=self.variant,
            ).count(),
            5,
        )
        # Units default to AVAILABLE.
        self.assertEqual(
            set(
                SerializedUnit.objects.filter(variant=self.variant).values_list(
                    "status", flat=True
                )
            ),
            {SerializedUnit.Status.AVAILABLE},
        )
        # PDF rendered by the eager Celery task on commit.
        batch.refresh_from_db()
        self.assertEqual(batch.status, LabelBatch.Status.READY)
        self.assertTrue(batch.pdf_file.name)
        with batch.pdf_file.open("rb") as fh:
            self.assertTrue(fh.read(5).startswith(b"%PDF"))
        self.assertEqual(len(res.data["serials"]), 5)

    def test_initial_status_generated_is_allowed(self):
        res = self._generate(quantity=2, initial_status="GENERATED")
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual(
            set(
                SerializedUnit.objects.filter(variant=self.variant).values_list(
                    "status", flat=True
                )
            ),
            {SerializedUnit.Status.GENERATED},
        )

    def test_initial_status_sold_is_rejected(self):
        res = self.client_for(self.operator).post(
            BASE, self._payload(initial_status="SOLD"), format="json"
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(LabelBatch.objects.count(), 0)

    # -- all-or-nothing ------------------------------------------------
    def test_failure_midway_rolls_back_everything(self):
        from apps.products.services import bulk_generate as bg

        real_generate = bg.SerializedInventoryService.generate
        call_count = {"n": 0}

        def flaky_generate(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 3:
                raise ValidationError("boom")
            return real_generate(*args, **kwargs)

        with mock.patch.object(
            bg.SerializedInventoryService, "generate", side_effect=flaky_generate
        ):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                res = self.client_for(self.operator).post(
                    BASE, self._payload(quantity=5), format="json"
                )

        self.assertEqual(res.status_code, 400)
        self.assertEqual(LabelBatch.objects.count(), 0)
        self.assertEqual(SerializedUnit.objects.filter(variant=self.variant).count(), 0)
        self.assertEqual(InventoryTransaction.objects.count(), 0)
        self.assertEqual(callbacks, [])  # render task never enqueued

    # -- serial continuity -------------------------------------------
    def test_serials_continue_gapless_from_existing_max(self):
        create_unit(variant=self.variant, location=self.warehouse, status="AVAILABLE")
        create_unit(variant=self.variant, location=self.warehouse, status="AVAILABLE")

        res = self._generate(quantity=3)
        self.assertEqual(res.status_code, 201, res.data)

        sequences = sorted(
            SerializedUnit.objects.filter(variant=self.variant).values_list(
                "sequence", flat=True
            )
        )
        self.assertEqual(sequences, [1, 2, 3, 4, 5])

    def test_next_serial_preview_matches_next_allocation(self):
        create_unit(variant=self.variant, location=self.warehouse, status="AVAILABLE")

        preview = self.client_for(self.operator).get(
            f"{BASE}next-serial/", {"variant": self.variant.id}
        )
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data["sequence"], 2)

        res = self._generate(quantity=1)
        first_serial = res.data["serials"][0]
        self.assertEqual(first_serial, preview.data["serial_number"])

    # -- RBAC ---------------------------------------------------------
    def test_viewer_cannot_generate(self):
        res = self.client_for(self.viewer).post(
            BASE, self._payload(), format="json"
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(LabelBatch.objects.count(), 0)

    def test_viewer_can_read_history(self):
        self._generate(quantity=2)
        res = self.client_for(self.viewer).get(BASE)
        self.assertEqual(res.status_code, 200)
        self.assertIn("data", res.data)
        self.assertEqual(res.data["meta"]["count"], 1)
        self.assertEqual(res.data["data"][0]["unit_count"], 2)

    # -- quantity cap ----------------------------------------------
    def test_quantity_over_cap_rejected(self):
        res = self.client_for(self.operator).post(
            BASE,
            self._payload(quantity=LabelBatch.MAX_QUANTITY + 1),
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(LabelBatch.objects.count(), 0)

    # -- regenerate ----------------------------------------------
    def test_regenerate_rerenders_without_new_units(self):
        res = self._generate(quantity=3)
        batch_id = res.data["id"]
        LabelBatch.objects.filter(pk=batch_id).update(
            status=LabelBatch.Status.FAILED, error_message="stale"
        )

        with self.captureOnCommitCallbacks(execute=True):
            again = self.client_for(self.operator).post(f"{BASE}{batch_id}/regenerate/")

        self.assertEqual(again.status_code, 200)
        batch = LabelBatch.objects.get(pk=batch_id)
        self.assertEqual(batch.status, LabelBatch.Status.READY)
        self.assertEqual(batch.error_message, "")
        self.assertEqual(SerializedUnit.objects.filter(variant=self.variant).count(), 3)

    def test_regenerate_needs_manage_permission(self):
        res = self._generate(quantity=2)
        batch_id = res.data["id"]
        denied = self.client_for(self.viewer).post(f"{BASE}{batch_id}/regenerate/")
        self.assertEqual(denied.status_code, 403)

    # -- PDF download --------------------------------------------
    def test_pdf_download_when_ready(self):
        res = self._generate(quantity=2)
        batch_id = res.data["id"]
        pdf = self.client_for(self.viewer).get(f"{BASE}{batch_id}/pdf/")
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF"))

    def test_pdf_download_before_ready_is_rejected(self):
        res = self._generate(quantity=2)
        batch_id = res.data["id"]
        LabelBatch.objects.filter(pk=batch_id).update(status=LabelBatch.Status.PENDING)
        pdf = self.client_for(self.viewer).get(f"{BASE}{batch_id}/pdf/")
        self.assertEqual(pdf.status_code, 400)

    # -- PDF failure keeps the units --------------------------------
    def test_pdf_render_failure_marks_batch_failed_but_keeps_units(self):
        with mock.patch(
            "apps.products.services.labels.build_label_pdf",
            side_effect=RuntimeError("no fonts"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                res = self.client_for(self.operator).post(
                    BASE, self._payload(quantity=4), format="json"
                )

        self.assertEqual(res.status_code, 201)
        batch = LabelBatch.objects.get(pk=res.data["id"])
        self.assertEqual(batch.status, LabelBatch.Status.FAILED)
        self.assertIn("no fonts", batch.error_message)
        self.assertEqual(SerializedUnit.objects.filter(variant=self.variant).count(), 4)
        self.assertFalse(batch.pdf_file.name)
