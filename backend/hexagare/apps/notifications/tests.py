"""Notification services + tasks (Phase 15)."""

from __future__ import annotations

from decimal import Decimal
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings

from apps.billing.models import Invoice, InvoiceDelivery
from apps.billing.services.checkout import CompleteSaleService
from apps.inventory.models import Location
from apps.products.models import Category, Product, ProductVariant, SerializedUnit
from apps.products.services.serial_numbers import create_unit
from apps.sales.models import Sale, SalesChannel
from apps.sales.services.units import SaleUnitService

from .services import EmailNotificationService, WhatsAppCloudAPI, WhatsAppNotificationService
from .tasks import send_invoice_delivery, send_low_stock_alerts


class _Response:
    def __init__(self, ok: bool, status_code: int = 200, text: str = "", json_body=None):
        self.ok = ok
        self.status_code = status_code
        self.text = text
        self._json_body = json_body or {}

    def json(self):
        return self._json_body


class WhatsAppCloudAPITests(TestCase):
    @override_settings(
        WHATSAPP_PHONE_NUMBER_ID="123",
        WHATSAPP_ACCESS_TOKEN="token-abc",
        WHATSAPP_BUSINESS_ACCOUNT_ID="waba-1",
        WHATSAPP_API_VERSION="v21.0",
    )
    def test_send_text_posts_expected_payload_and_auth_header(self):
        with mock.patch("apps.notifications.services.requests.post") as post:
            post.return_value = _Response(ok=True, json_body={"messages": [{"id": "wamid.1"}]})
            WhatsAppCloudAPI().send_text("+919999999999", "hello")

        post.assert_called_once()
        url, kwargs = post.call_args
        self.assertEqual(url[0], "https://graph.facebook.com/v21.0/123/messages")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer token-abc")
        self.assertEqual(kwargs["json"]["to"], "+919999999999")
        self.assertEqual(kwargs["json"]["type"], "text")
        self.assertEqual(kwargs["json"]["text"]["body"], "hello")

    @override_settings(WHATSAPP_PHONE_NUMBER_ID="", WHATSAPP_ACCESS_TOKEN="")
    def test_send_text_raises_when_unconfigured(self):
        with self.assertRaises(RuntimeError):
            WhatsAppCloudAPI().send_text("+919999999999", "hello")

    @override_settings(WHATSAPP_PHONE_NUMBER_ID="123", WHATSAPP_ACCESS_TOKEN="token-abc")
    def test_send_text_raises_on_error_response(self):
        with mock.patch("apps.notifications.services.requests.post") as post:
            post.return_value = _Response(ok=False, status_code=401, text="Invalid token")
            with self.assertRaises(RuntimeError) as ctx:
                WhatsAppCloudAPI().send_text("+919999999999", "hello")
        self.assertIn("401", str(ctx.exception))


class InvoiceTestBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        cls.cashier = User.objects.create_user("cashier@hexagare.test", "pw-Testing-123")

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


class EmailNotificationServiceTests(InvoiceTestBase):
    def test_send_invoice_attaches_pdf_and_includes_link(self):
        invoice = self.complete_a_sale()
        invoice.refresh_from_db()  # the render task updated a separate DB row, not this object
        EmailNotificationService().send_invoice(invoice, "buyer@example.com")

        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["buyer@example.com"])
        self.assertIn(invoice.invoice_number, message.subject)
        self.assertEqual(len(message.attachments), 1)
        filename, _content, content_type = message.attachments[0]
        self.assertEqual(filename, f"{invoice.invoice_number}.pdf")
        self.assertEqual(content_type, "application/pdf")

    def test_send_low_stock_digest_lists_alerts(self):
        alerts = [
            {
                "type": "out_of_stock",
                "variant": {"sku": "HEX-MP-A-001", "product_name": "Pad"},
                "location": {"id": 1, "name": "Warehouse"},
                "available": 0,
                "threshold": 0,
            }
        ]
        EmailNotificationService().send_low_stock_digest(alerts, ["ops@hexagare.test"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("HEX-MP-A-001", mail.outbox[0].body)


class SendInvoiceDeliveryTaskTests(InvoiceTestBase):
    def test_email_channel_marks_delivery_sent(self):
        invoice = self.complete_a_sale()
        delivery = InvoiceDelivery.objects.create(
            invoice=invoice, channel=InvoiceDelivery.Channel.EMAIL, recipient="buyer@example.com"
        )
        result = send_invoice_delivery(delivery.id)
        delivery.refresh_from_db()
        self.assertEqual(result, "sent")
        self.assertEqual(delivery.status, InvoiceDelivery.Status.SENT)
        self.assertIsNotNone(delivery.sent_at)

    def test_whatsapp_failure_marks_delivery_failed_with_error(self):
        invoice = self.complete_a_sale()
        delivery = InvoiceDelivery.objects.create(
            invoice=invoice,
            channel=InvoiceDelivery.Channel.WHATSAPP,
            recipient="+919999999999",
        )
        with mock.patch.object(
            WhatsAppNotificationService, "send_invoice", side_effect=RuntimeError("boom")
        ):
            result = send_invoice_delivery(delivery.id)
        delivery.refresh_from_db()
        self.assertEqual(result, "failed")
        self.assertEqual(delivery.status, InvoiceDelivery.Status.FAILED)
        self.assertIn("boom", delivery.error_message)

    def test_missing_delivery_is_a_noop(self):
        self.assertEqual(send_invoice_delivery(999999), "missing")


class SendLowStockAlertsTaskTests(TestCase):
    @override_settings(LOW_STOCK_ALERT_EMAILS=[], LOW_STOCK_ALERT_WHATSAPP_TO=[])
    def test_noop_without_recipients(self):
        with mock.patch(
            "apps.inventory.services.alerts.compute_alerts",
            return_value=[{"type": "low_stock"}],
        ):
            self.assertEqual(send_low_stock_alerts(), "no-recipients")

    @override_settings(LOW_STOCK_ALERT_EMAILS=["ops@hexagare.test"], LOW_STOCK_ALERT_WHATSAPP_TO=[])
    def test_noop_without_alerts(self):
        with mock.patch("apps.inventory.services.alerts.compute_alerts", return_value=[]):
            self.assertEqual(send_low_stock_alerts(), "no-alerts")

    @override_settings(LOW_STOCK_ALERT_EMAILS=["ops@hexagare.test"], LOW_STOCK_ALERT_WHATSAPP_TO=[])
    def test_sends_email_digest_for_low_and_out_of_stock_only(self):
        alerts = [
            {
                "type": "low_stock",
                "variant": {"sku": "A", "product_name": "Pad"},
                "location": None,
                "available": 1,
                "threshold": 5,
            },
            {
                "type": "overstock",
                "variant": {"sku": "B", "product_name": "Mat"},
                "location": None,
                "available": 100,
                "threshold": 50,
            },
        ]
        with mock.patch("apps.inventory.services.alerts.compute_alerts", return_value=alerts):
            result = send_low_stock_alerts()
        self.assertEqual(result, "sent (1 alerts)")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("A", mail.outbox[0].body)
        self.assertNotIn("B", mail.outbox[0].body)
