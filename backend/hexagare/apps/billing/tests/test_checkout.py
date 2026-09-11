"""``POST /billing/checkout/`` -- payment recording, hold-vs-complete, and the
atomic sell-units + invoice path once payment covers the total
(HEXAGARE_FEATURES.md section 26, rule 7)."""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.rbac import ensure_role_groups
from apps.billing.models import Invoice, Payment
from apps.billing.services.checkout import CompleteSaleService
from apps.inventory.models import InventoryTransaction, Location
from apps.products.models import Category, Product, ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import create_unit
from apps.sales.models import Sale, SalesChannel
from apps.sales.services.units import SaleUnitService

User = get_user_model()


class CheckoutTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        ensure_role_groups()
        cls.cashier = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")
        cls.cashier.groups.add(Group.objects.get(name="Cashier"))
        cls.outsider = User.objects.create_user("outsider@hexagare.test", "pw-Testing-123")

        cls.warehouse = Location.objects.get(code="warehouse")
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

    def make_unit(self):
        return create_unit(
            variant=self.variant, location=self.warehouse, status=SerializedUnit.Status.AVAILABLE
        )

    def make_reserved_sale(self, n=1):
        sale = Sale.objects.create(sales_channel=self.offline)
        units = [self.make_unit() for _ in range(n)]
        for unit in units:
            SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)
        return sale, units


class CompleteSaleServiceTests(CheckoutTestBase):
    def test_full_payment_sells_units_pays_and_invoices_atomically(self):
        sale, units = self.make_reserved_sale(n=2)

        with self.captureOnCommitCallbacks(execute=True):
            sale, invoice = CompleteSaleService.complete(
                sale,
                payments=[{"method": Payment.Method.CASH, "amount": Decimal("2360.00")}],
                actor=self.cashier,
            )

        self.assertIsNotNone(invoice)
        self.assertEqual(sale.status, Sale.Status.COMPLETED)
        for unit in units:
            unit.refresh_from_db()
            self.assertEqual(unit.status, SerializedUnit.Status.SOLD)

        self.assertTrue(
            InventoryTransaction.objects.filter(
                serialized_unit__in=units, kind=InventoryTransaction.Kind.SALE
            ).exists()
        )
        self.assertEqual(Payment.objects.filter(sale=sale).count(), 1)
        self.assertEqual(invoice.grand_total, Decimal("2360.00"))
        self.assertTrue(invoice.invoice_number.startswith("HEX-INV-"))

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.READY)
        self.assertTrue(invoice.pdf_file)

    def test_partial_payment_holds_the_sale_and_keeps_units_reserved(self):
        sale, units = self.make_reserved_sale(n=1)  # grand_total 1180.00

        sale, invoice = CompleteSaleService.complete(
            sale,
            payments=[{"method": Payment.Method.CASH, "amount": Decimal("500.00")}],
            actor=self.cashier,
        )

        self.assertIsNone(invoice)
        self.assertEqual(sale.status, Sale.Status.RESERVED)
        units[0].refresh_from_db()
        self.assertEqual(units[0].status, SerializedUnit.Status.RESERVED)
        self.assertFalse(Invoice.objects.filter(sale=sale).exists())
        self.assertEqual(sale.amount_paid, Decimal("500.00"))
        self.assertEqual(sale.balance_due, Decimal("680.00"))

    def test_zero_payment_holds_the_sale(self):
        sale, units = self.make_reserved_sale(n=1)

        sale, invoice = CompleteSaleService.complete(sale, payments=[], actor=self.cashier)

        self.assertIsNone(invoice)
        self.assertEqual(sale.status, Sale.Status.RESERVED)
        units[0].refresh_from_db()
        self.assertEqual(units[0].status, SerializedUnit.Status.RESERVED)

    def test_credit_payment_for_the_full_amount_completes_the_sale(self):
        """A ``CREDIT`` payment row is just another method -- recording one
        for the full amount completes the sale like any other method."""
        sale, units = self.make_reserved_sale(n=1)

        with self.captureOnCommitCallbacks(execute=True):
            sale, invoice = CompleteSaleService.complete(
                sale,
                payments=[{"method": Payment.Method.CREDIT, "amount": Decimal("1180.00")}],
                actor=self.cashier,
            )

        self.assertIsNotNone(invoice)
        self.assertEqual(sale.status, Sale.Status.COMPLETED)
        units[0].refresh_from_db()
        self.assertEqual(units[0].status, SerializedUnit.Status.SOLD)
        self.assertEqual(invoice.balance_due, Decimal("0.00"))

    def test_resuming_a_held_sale_with_more_payment_completes_it(self):
        sale, units = self.make_reserved_sale(n=1)
        sale, invoice = CompleteSaleService.complete(
            sale,
            payments=[{"method": Payment.Method.CASH, "amount": Decimal("500.00")}],
            actor=self.cashier,
        )
        self.assertIsNone(invoice)
        self.assertEqual(sale.status, Sale.Status.RESERVED)

        with self.captureOnCommitCallbacks(execute=True):
            sale, invoice = CompleteSaleService.complete(
                sale,
                payments=[{"method": Payment.Method.CASH, "amount": Decimal("680.00")}],
                actor=self.cashier,
            )

        self.assertIsNotNone(invoice)
        self.assertEqual(sale.status, Sale.Status.COMPLETED)
        units[0].refresh_from_db()
        self.assertEqual(units[0].status, SerializedUnit.Status.SOLD)
        self.assertEqual(Payment.objects.filter(sale=sale).count(), 2)
        self.assertEqual(invoice.amount_paid, Decimal("1180.00"))

    def test_rejects_already_completed_or_cancelled_sale(self):
        sale, _ = self.make_reserved_sale()
        sale.status = Sale.Status.CANCELLED
        sale.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            CompleteSaleService.complete(sale, payments=[], actor=self.cashier)

    def test_rejects_line_not_fully_unit_backed(self):
        sale = Sale.objects.create(sales_channel=self.offline)
        sale.lines.create(
            variant=self.variant,
            quantity=2,
            unit_price=Decimal("1180.00"),
            tax_rate=Decimal("18.00"),
        )
        with self.assertRaises(ValidationError):
            CompleteSaleService.complete(sale, payments=[], actor=self.cashier)

    def test_invoice_numbers_increment(self):
        sale1, _ = self.make_reserved_sale()
        sale2, _ = self.make_reserved_sale()
        full_payment = [{"method": "CASH", "amount": Decimal("1180.00")}]
        with self.captureOnCommitCallbacks(execute=True):
            _, inv1 = CompleteSaleService.complete(sale1, payments=full_payment, actor=self.cashier)
            _, inv2 = CompleteSaleService.complete(sale2, payments=full_payment, actor=self.cashier)
        self.assertEqual(inv2.sequence, inv1.sequence + 1)


class CheckoutApiTests(CheckoutTestBase):
    def test_checkout_requires_billing_manage(self):
        sale, _ = self.make_reserved_sale()
        res = self.client_for(self.outsider).post(
            "/api/v1/billing/checkout/", {"sale": sale.pk, "payments": []}, format="json"
        )
        self.assertEqual(res.status_code, 403)

    def test_checkout_happy_path_returns_invoice(self):
        sale, _ = self.make_reserved_sale()
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client_for(self.cashier).post(
                "/api/v1/billing/checkout/",
                {
                    "sale": sale.pk,
                    "payments": [{"method": "CASH", "amount": "1180.00"}],
                },
                format="json",
            )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIsNotNone(res.data["invoice"])
        self.assertEqual(res.data["sale"]["status"], "COMPLETED")

        invoice_id = res.data["invoice"]["id"]
        invoice = Invoice.objects.get(pk=invoice_id)
        self.assertEqual(invoice.status, Invoice.Status.READY)

        pdf_res = self.client_for(self.cashier).get(f"/api/v1/billing/invoices/{invoice_id}/pdf/")
        self.assertEqual(pdf_res.status_code, 200)
        self.assertEqual(pdf_res["Content-Type"], "application/pdf")

    def test_checkout_partial_payment_returns_held_sale_no_invoice(self):
        sale, _ = self.make_reserved_sale()
        res = self.client_for(self.cashier).post(
            "/api/v1/billing/checkout/",
            {"sale": sale.pk, "payments": [{"method": "CASH", "amount": "500.00"}]},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIsNone(res.data["invoice"])
        self.assertEqual(res.data["sale"]["status"], "RESERVED")
        self.assertEqual(res.data["sale"]["balance_due"], "680.00")

    def test_resume_held_sale_via_api(self):
        sale, _ = self.make_reserved_sale()
        client = self.client_for(self.cashier)
        client.post(
            "/api/v1/billing/checkout/",
            {"sale": sale.pk, "payments": [{"method": "CASH", "amount": "500.00"}]},
            format="json",
        )
        with self.captureOnCommitCallbacks(execute=True):
            res = client.post(
                "/api/v1/billing/checkout/",
                {"sale": sale.pk, "payments": [{"method": "CASH", "amount": "680.00"}]},
                format="json",
            )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIsNotNone(res.data["invoice"])
        self.assertEqual(res.data["sale"]["status"], "COMPLETED")

    def test_settle_a_credit_balance_on_an_already_completed_sale(self):
        """A CREDIT row can complete a sale (goods sold, receivable open);
        the same checkout endpoint lets staff record the later repayment."""
        sale, units = self.make_reserved_sale(n=1)  # grand_total 1180.00
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client_for(self.cashier).post(
                "/api/v1/billing/checkout/",
                {"sale": sale.pk, "payments": [{"method": "CREDIT", "amount": "1180.00"}]},
                format="json",
            )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIsNotNone(res.data["invoice"])
        self.assertEqual(res.data["sale"]["status"], "COMPLETED")
        units[0].refresh_from_db()
        self.assertEqual(units[0].status, SerializedUnit.Status.SOLD)

        # Balance is "paid" for completion purposes (CREDIT counts), but the
        # invoice can still take a real repayment against that receivable.
        res = self.client_for(self.cashier).post(
            "/api/v1/billing/checkout/",
            {"sale": sale.pk, "payments": [{"method": "CASH", "amount": "1180.00"}]},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertIsNotNone(res.data["invoice"])
        self.assertEqual(Payment.objects.filter(sale=sale).count(), 2)
        # Units aren't touched again -- still exactly one SOLD event.
        units[0].refresh_from_db()
        self.assertEqual(units[0].status, SerializedUnit.Status.SOLD)

    def test_record_payment_rejects_a_non_completed_sale(self):
        sale, _ = self.make_reserved_sale()  # still DRAFT
        with self.assertRaises(ValidationError):
            CompleteSaleService.record_payment(
                sale,
                payments=[{"method": "CASH", "amount": Decimal("100.00")}],
                actor=self.cashier,
            )

    def test_record_payment_rejects_empty_payments(self):
        sale, _ = self.make_reserved_sale(n=1)
        full_payment = [{"method": "CASH", "amount": Decimal("1180.00")}]
        with self.captureOnCommitCallbacks(execute=True):
            sale, _ = CompleteSaleService.complete(sale, payments=full_payment, actor=self.cashier)
        with self.assertRaises(ValidationError):
            CompleteSaleService.record_payment(sale, payments=[], actor=self.cashier)
