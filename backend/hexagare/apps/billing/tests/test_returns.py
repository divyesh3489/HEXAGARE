"""Returns (Phase 10): resolve/create/inspect, RBAC, and the channel-agnostic
resolution that closes Phase 9's "can't reverse a finalized Amazon order"
gap (HEXAGARE_FEATURES.md section 31, 59)."""

import io
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.rbac import ensure_role_groups
from apps.billing.models import Payment, Return, ReturnUnit
from apps.billing.services.checkout import CompleteSaleService
from apps.billing.services.returns import ReturnService
from apps.integrations.amazon.models import AmazonImportBatch
from apps.integrations.amazon.services.importer import AmazonOrderImportService
from apps.integrations.amazon.sources import CSVAmazonOrderSource
from apps.inventory.models import InventoryTransaction, Location
from apps.products.models import Category, Product, ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import create_unit
from apps.sales.models import Sale, SalesChannel
from apps.sales.services.units import SaleUnitService

User = get_user_model()

AMAZON_CSV_HEADER = (
    "order_id,order_date,order_status,amazon_sku,quantity,selling_price,gst_amount,"
    "referral_fee,closing_fee,fulfillment_fee,shipping_cost,advertising_cost,other_charges,"
    "refund_amount"
)


class ReturnsTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.cashier = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.cashier.groups.add(Group.objects.get(name="Cashier"))
        cls.warehouse_user = User.objects.create_user("wh@hexagare.test", "pw-Testing-123")
        cls.warehouse_user.groups.add(Group.objects.get(name="Warehouse"))

        cls.warehouse = Location.objects.get(code="warehouse")
        cls.amazon_location = Location.objects.get(code="amazon")
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
        cls.offline = SalesChannel.objects.get(code="OFFLINE")

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def make_unit(self, location=None):
        return create_unit(
            variant=self.variant,
            location=location or self.warehouse,
            status=SerializedUnit.Status.AVAILABLE,
        )

    def make_completed_sale(self, n=1):
        """A COMPLETED offline sale with ``n`` SOLD units, via the real
        checkout flow (not a shortcut) so ``SaleLineUnit`` rows exist."""
        sale = Sale.objects.create(sales_channel=self.offline)
        units = [self.make_unit() for _ in range(n)]
        for unit in units:
            SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)
        sale.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            sale, _invoice = CompleteSaleService.complete(
                sale,
                payments=[{"method": Payment.Method.CASH, "amount": sale.grand_total}],
                actor=self.cashier,
            )
        return sale, units


class ReturnServiceTests(ReturnsTestBase):
    def test_resolve_returns_sale_and_line_context(self):
        sale, units = self.make_completed_sale(n=1)

        result = ReturnService.resolve(units[0].serial_number)

        self.assertEqual(result["sale"].pk, sale.pk)
        self.assertEqual(result["suggested_refund_amount"], Decimal("1180.00"))

    def test_resolve_rejects_a_unit_that_is_not_sold(self):
        unit = self.make_unit()
        with self.assertRaises(ValidationError):
            ReturnService.resolve(unit.serial_number)

    def test_create_moves_unit_to_returned_and_records_refund_payment(self):
        sale, units = self.make_completed_sale(n=1)

        return_obj = ReturnService.create(
            entries=[{"code": units[0].serial_number, "refund_amount": None}],
            reason="Customer changed mind",
            refund_method=Payment.Method.CASH,
            actor=self.cashier,
        )

        units[0].refresh_from_db()
        self.assertEqual(units[0].status, SerializedUnit.Status.RETURNED)
        self.assertEqual(return_obj.sale_id, sale.pk)
        self.assertEqual(return_obj.refund_total, Decimal("1180.00"))
        self.assertEqual(return_obj.units.count(), 1)
        self.assertEqual(return_obj.units.first().condition, ReturnUnit.Condition.PENDING)

        refund = Payment.objects.get(sale=sale, type=Payment.Type.REFUND)
        self.assertEqual(refund.amount, Decimal("1180.00"))
        self.assertEqual(refund.method, Payment.Method.CASH)

        self.assertTrue(
            InventoryTransaction.objects.filter(
                serialized_unit=units[0], kind=InventoryTransaction.Kind.RETURN
            ).exists()
        )

    def test_create_rejects_units_from_different_sales(self):
        _sale1, units1 = self.make_completed_sale(n=1)
        _sale2, units2 = self.make_completed_sale(n=1)

        with self.assertRaises(ValidationError):
            ReturnService.create(
                entries=[
                    {"code": units1[0].serial_number, "refund_amount": None},
                    {"code": units2[0].serial_number, "refund_amount": None},
                ],
                reason="Mixed",
                refund_method=Payment.Method.CASH,
                actor=self.cashier,
            )
        self.assertFalse(Return.objects.exists())

    def test_create_rejects_a_unit_that_is_not_sold(self):
        unit = self.make_unit()
        with self.assertRaises(ValidationError):
            ReturnService.create(
                entries=[{"code": unit.serial_number, "refund_amount": None}],
                reason="Bad",
                refund_method=Payment.Method.CASH,
                actor=self.cashier,
            )

    def test_inspect_resellable_restores_unit_to_available(self):
        _sale, units = self.make_completed_sale(n=1)
        return_obj = ReturnService.create(
            entries=[{"code": units[0].serial_number, "refund_amount": None}],
            reason="Wrong size",
            refund_method=Payment.Method.CASH,
            actor=self.cashier,
        )
        return_unit = return_obj.units.first()

        ReturnService.inspect(
            return_unit=return_unit, condition=ReturnUnit.Condition.RESELLABLE, actor=self.cashier
        )

        units[0].refresh_from_db()
        return_unit.refresh_from_db()
        self.assertEqual(units[0].status, SerializedUnit.Status.AVAILABLE)
        self.assertEqual(return_unit.condition, ReturnUnit.Condition.RESELLABLE)
        self.assertIsNotNone(return_unit.inspected_at)
        self.assertTrue(
            InventoryTransaction.objects.filter(
                serialized_unit=units[0], kind=InventoryTransaction.Kind.RESTORE
            ).exists()
        )

    def test_inspect_damaged_moves_unit_to_damaged(self):
        _sale, units = self.make_completed_sale(n=1)
        return_obj = ReturnService.create(
            entries=[{"code": units[0].serial_number, "refund_amount": None}],
            reason="Cracked",
            refund_method=Payment.Method.UPI,
            actor=self.cashier,
        )
        return_unit = return_obj.units.first()

        ReturnService.inspect(
            return_unit=return_unit, condition=ReturnUnit.Condition.DAMAGED, actor=self.cashier
        )

        units[0].refresh_from_db()
        self.assertEqual(units[0].status, SerializedUnit.Status.DAMAGED)

    def test_inspect_twice_is_rejected(self):
        _sale, units = self.make_completed_sale(n=1)
        return_obj = ReturnService.create(
            entries=[{"code": units[0].serial_number, "refund_amount": None}],
            reason="Wrong size",
            refund_method=Payment.Method.CASH,
            actor=self.cashier,
        )
        return_unit = return_obj.units.first()
        ReturnService.inspect(
            return_unit=return_unit, condition=ReturnUnit.Condition.RESELLABLE, actor=self.cashier
        )

        with self.assertRaises(ValidationError):
            ReturnService.inspect(
                return_unit=return_unit,
                condition=ReturnUnit.Condition.DAMAGED,
                actor=self.cashier,
            )


class AmazonOriginReturnTests(ReturnsTestBase):
    """Phase 9 deliberately rejects a CSV trying to reverse an already-sold
    Amazon order; this is the manual path that closes that gap -- returns
    work off the serial, regardless of which channel sold it."""

    def test_a_unit_sold_via_amazon_import_can_be_returned(self):
        unit = self.make_unit(location=self.amazon_location)
        batch = AmazonImportBatch.objects.create()
        csv_text = AMAZON_CSV_HEADER + "\n" + ",".join(
            str(v)
            for v in [
                "AMZ-1",
                "2026-01-10",
                "Shipped",
                self.variant.sku,
                1,
                "1180.00",
                "180.00",
                "150.00",
                "20.00",
                "80.00",
                "80.00",
                "50.00",
                "10.00",
                "0.00",
            ]
        ) + "\n"
        AmazonOrderImportService.run(batch, CSVAmazonOrderSource(io.StringIO(csv_text)))
        unit.refresh_from_db()
        self.assertEqual(unit.status, SerializedUnit.Status.SOLD)

        return_obj = ReturnService.create(
            entries=[{"code": unit.serial_number, "refund_amount": None}],
            reason="Amazon return",
            refund_method=Payment.Method.BANK_TRANSFER,
            actor=self.cashier,
        )

        unit.refresh_from_db()
        self.assertEqual(unit.status, SerializedUnit.Status.RETURNED)
        self.assertEqual(return_obj.sale.sales_channel.code, "AMAZON")


class ReturnApiTests(ReturnsTestBase):
    def test_full_flow_via_api(self):
        _sale, units = self.make_completed_sale(n=1)
        client = self.client_for(self.cashier)

        resolve_resp = client.get(
            "/api/v1/billing/returns/resolve/", {"code": units[0].serial_number}
        )
        self.assertEqual(resolve_resp.status_code, 200)
        self.assertEqual(resolve_resp.data["sku"], self.variant.sku)

        create_resp = client.post(
            "/api/v1/billing/returns/",
            {
                "entries": [{"code": units[0].serial_number}],
                "reason": "Customer changed mind",
                "refund_method": "CASH",
            },
            format="json",
        )
        self.assertEqual(create_resp.status_code, 201, create_resp.data)
        return_id = create_resp.data["id"]
        return_unit_id = create_resp.data["units"][0]["id"]

        inspect_resp = client.post(
            f"/api/v1/billing/returns/{return_id}/units/{return_unit_id}/inspect/",
            {"condition": "RESELLABLE"},
            format="json",
        )
        self.assertEqual(inspect_resp.status_code, 200, inspect_resp.data)
        self.assertEqual(inspect_resp.data["units"][0]["condition"], "RESELLABLE")

        units[0].refresh_from_db()
        self.assertEqual(units[0].status, SerializedUnit.Status.AVAILABLE)

    def test_warehouse_role_is_forbidden(self):
        _sale, units = self.make_completed_sale(n=1)
        client = self.client_for(self.warehouse_user)

        resp = client.get(
            "/api/v1/billing/returns/resolve/", {"code": units[0].serial_number}
        )
        self.assertEqual(resp.status_code, 403)

        resp = client.post(
            "/api/v1/billing/returns/",
            {
                "entries": [{"code": units[0].serial_number}],
                "reason": "x",
                "refund_method": "CASH",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 403)
