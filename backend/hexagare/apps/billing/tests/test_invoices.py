"""Invoice list/detail RBAC + PDF render failure recovery (Phase 8),
send-invoice delivery (Phase 15)."""

from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.rbac import ensure_role_groups
from apps.billing.models import Invoice, InvoiceDelivery
from apps.billing.services.checkout import CompleteSaleService
from apps.customers.models import Customer
from apps.inventory.models import Location
from apps.products.models import Category, Product, ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import create_unit
from apps.sales.models import Sale, SalesChannel
from apps.sales.services.units import SaleUnitService

User = get_user_model()


class InvoiceTestBase(TestCase):
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

    def complete_a_sale(self) -> Invoice:
        sale = Sale.objects.create(sales_channel=self.offline)
        unit = create_unit(
            variant=self.variant, location=self.warehouse, status=SerializedUnit.Status.AVAILABLE
        )
        SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)
        with self.captureOnCommitCallbacks(execute=True):
            _, invoice = CompleteSaleService.complete(
                sale, payments=[{"method": "CASH", "amount": "1180.00"}], actor=self.cashier
            )
        return invoice


class InvoiceRbacTests(InvoiceTestBase):
    def test_list_requires_billing_view(self):
        res = self.client_for(self.outsider).get("/api/v1/billing/invoices/")
        self.assertEqual(res.status_code, 403)

    def test_cashier_can_list_and_retrieve(self):
        invoice = self.complete_a_sale()
        client = self.client_for(self.cashier)

        res = client.get("/api/v1/billing/invoices/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["meta"]["count"], 1)

        res = client.get(f"/api/v1/billing/invoices/{invoice.pk}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["invoice_number"], invoice.invoice_number)
        self.assertEqual(len(res.data["sale_detail"]["lines"]), 1)


class InvoicePdfFailureTests(InvoiceTestBase):
    def test_render_failure_marks_invoice_failed_but_keeps_sale_completed(self):
        sale = Sale.objects.create(sales_channel=self.offline)
        unit = create_unit(
            variant=self.variant, location=self.warehouse, status=SerializedUnit.Status.AVAILABLE
        )
        SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)

        with mock.patch(
            "apps.billing.services.invoice_pdf.build_invoice_pdf",
            side_effect=RuntimeError("no fonts"),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                _, invoice = CompleteSaleService.complete(
                    sale,
                    payments=[{"method": "CASH", "amount": "1180.00"}],
                    actor=self.cashier,
                )

        sale.refresh_from_db()
        self.assertEqual(sale.status, Sale.Status.COMPLETED)
        unit.refresh_from_db()
        self.assertEqual(unit.status, SerializedUnit.Status.SOLD)

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, Invoice.Status.FAILED)
        self.assertIn("no fonts", invoice.error_message)

        res = self.client_for(self.cashier).get(f"/api/v1/billing/invoices/{invoice.pk}/pdf/")
        self.assertEqual(res.status_code, 400)


class InvoiceSendTests(InvoiceTestBase):
    def test_send_requires_billing_manage(self):
        invoice = self.complete_a_sale()
        res = self.client_for(self.outsider).post(
            f"/api/v1/billing/invoices/{invoice.pk}/send/", {"channel": "EMAIL"}
        )
        self.assertEqual(res.status_code, 403)

    def test_send_requires_ready_pdf(self):
        with mock.patch(
            "apps.billing.services.invoice_pdf.build_invoice_pdf",
            side_effect=RuntimeError("no fonts"),
        ):
            sale = Sale.objects.create(sales_channel=self.offline)
            unit = create_unit(
                variant=self.variant,
                location=self.warehouse,
                status=SerializedUnit.Status.AVAILABLE,
            )
            SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)
            with self.captureOnCommitCallbacks(execute=True):
                _, invoice = CompleteSaleService.complete(
                    sale, payments=[{"method": "CASH", "amount": "1180.00"}], actor=self.cashier
                )

        res = self.client_for(self.cashier).post(
            f"/api/v1/billing/invoices/{invoice.pk}/send/", {"channel": "EMAIL"}
        )
        self.assertEqual(res.status_code, 400)

    def test_send_without_recipient_or_customer_is_rejected(self):
        invoice = self.complete_a_sale()
        res = self.client_for(self.cashier).post(
            f"/api/v1/billing/invoices/{invoice.pk}/send/", {"channel": "EMAIL"}
        )
        self.assertEqual(res.status_code, 400)
        self.assertFalse(InvoiceDelivery.objects.filter(invoice=invoice).exists())

    def test_send_uses_explicit_recipient_and_enqueues_delivery(self):
        invoice = self.complete_a_sale()
        with mock.patch("apps.billing.views.send_invoice_delivery.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                res = self.client_for(self.cashier).post(
                    f"/api/v1/billing/invoices/{invoice.pk}/send/",
                    {"channel": "EMAIL", "recipient": "buyer@example.com"},
                )
        self.assertEqual(res.status_code, 201)
        delivery = InvoiceDelivery.objects.get(invoice=invoice)
        self.assertEqual(delivery.channel, InvoiceDelivery.Channel.EMAIL)
        self.assertEqual(delivery.recipient, "buyer@example.com")
        self.assertEqual(delivery.status, InvoiceDelivery.Status.PENDING)
        delay.assert_called_once_with(delivery.id)
        self.assertEqual(len(res.data["deliveries"]), 1)

    def test_send_falls_back_to_customer_contact(self):
        customer = Customer.objects.create(
            name="Priya", email="priya@example.com", phone="+919999999999"
        )
        sale = Sale.objects.create(sales_channel=self.offline, customer=customer)
        unit = create_unit(
            variant=self.variant, location=self.warehouse, status=SerializedUnit.Status.AVAILABLE
        )
        SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)
        with self.captureOnCommitCallbacks(execute=True):
            _, invoice = CompleteSaleService.complete(
                sale, payments=[{"method": "CASH", "amount": "1180.00"}], actor=self.cashier
            )

        with mock.patch("apps.billing.views.send_invoice_delivery.delay"):
            with self.captureOnCommitCallbacks(execute=True):
                res = self.client_for(self.cashier).post(
                    f"/api/v1/billing/invoices/{invoice.pk}/send/", {"channel": "WHATSAPP"}
                )
        self.assertEqual(res.status_code, 201)
        delivery = InvoiceDelivery.objects.get(invoice=invoice)
        self.assertEqual(delivery.recipient, "+919999999999")

    def test_send_end_to_end_marks_delivery_sent(self):
        """No mocking of the task itself -- runs the real
        ``send_invoice_delivery`` task (Celery eager in tests) against the
        locmem email backend, exercising ``EmailNotificationService`` too."""
        from django.core import mail

        invoice = self.complete_a_sale()
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client_for(self.cashier).post(
                f"/api/v1/billing/invoices/{invoice.pk}/send/",
                {"channel": "EMAIL", "recipient": "buyer@example.com"},
            )
        self.assertEqual(res.status_code, 201)
        delivery = InvoiceDelivery.objects.get(invoice=invoice)
        self.assertEqual(delivery.status, InvoiceDelivery.Status.SENT)
        self.assertIsNotNone(delivery.sent_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["buyer@example.com"])
        self.assertEqual(len(mail.outbox[0].attachments), 1)


class HeldSaleTests(InvoiceTestBase):
    def test_partially_paid_sale_creates_no_invoice(self):
        sale = Sale.objects.create(sales_channel=self.offline)
        unit = create_unit(
            variant=self.variant, location=self.warehouse, status=SerializedUnit.Status.AVAILABLE
        )
        SaleUnitService.add(sale, code=unit.serial_number, actor=self.cashier)

        sale, invoice = CompleteSaleService.complete(
            sale, payments=[{"method": "CASH", "amount": "500.00"}], actor=self.cashier
        )

        self.assertIsNone(invoice)
        self.assertFalse(Invoice.objects.filter(sale=sale).exists())
        res = self.client_for(self.cashier).get("/api/v1/billing/invoices/")
        self.assertEqual(res.data["meta"]["count"], 0)
