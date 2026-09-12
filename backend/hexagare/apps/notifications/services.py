"""Outbound notification senders (Phase 15).

Two channels, each with one service class:

- :class:`EmailNotificationService` -- Django's ``EmailMessage`` over
  whatever ``EMAIL_BACKEND`` is configured (SMTP/SendGrid in
  staging/production, console/locmem in dev/test -- see
  ``hexagare/settings/base.py``).
- :class:`WhatsAppNotificationService` -- built on :class:`WhatsAppCloudAPI`,
  which isolates the actual Meta Cloud API HTTP call (per the Phase 15 build
  prompt) so the message-building code above it never touches ``requests``
  directly.

Sends plain **text** WhatsApp messages, not a pre-approved template -- this
works immediately against the Cloud API's free test number for its verified
recipients, and for any customer within a 24h session after they've messaged
first. Meta requires an approved template for a business-initiated message
to a customer who has never messaged in ("WhatsApp Setup" section of
HEXAGARE_BUILD_PROMPTS.md) -- swap :meth:`WhatsAppCloudAPI.send_text` for a
``send_template`` call once you've created and had one approved; the
component layout of an approved template is only known once it exists, so
nothing here guesses at one.

Called only from :mod:`apps.notifications.tasks` -- never from a view.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)


class WhatsAppCloudAPI:
    """Thin client for the Meta WhatsApp Cloud API ``/messages`` endpoint.

    Reads ``WHATSAPP_PHONE_NUMBER_ID``/``WHATSAPP_ACCESS_TOKEN`` from
    settings. ``WHATSAPP_BUSINESS_ACCOUNT_ID`` isn't needed for sending a
    message (only for template/account management), but is validated here
    too since all three are configured together per the build prompt.
    """

    def __init__(self) -> None:
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.access_token = settings.WHATSAPP_ACCESS_TOKEN
        self.business_account_id = settings.WHATSAPP_BUSINESS_ACCOUNT_ID
        self.api_version = settings.WHATSAPP_API_VERSION

    @property
    def is_configured(self) -> bool:
        return bool(self.phone_number_id and self.access_token)

    def _post(self, payload: dict) -> dict:
        if not self.is_configured:
            raise RuntimeError(
                "WhatsApp Cloud API is not configured -- set WHATSAPP_PHONE_NUMBER_ID "
                "and WHATSAPP_ACCESS_TOKEN."
            )
        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            json=payload,
            timeout=15,
        )
        if not response.ok:
            raise RuntimeError(
                f"WhatsApp Cloud API error {response.status_code}: {response.text[:500]}"
            )
        return response.json()

    def send_text(self, to: str, body: str) -> dict:
        """``to`` is an E.164-ish phone number (digits, optional leading
        ``+``) -- the Cloud API accepts either, it normalizes internally."""
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body, "preview_url": True},
        }
        return self._post(payload)


class WhatsAppNotificationService:
    def __init__(self, client: WhatsAppCloudAPI | None = None) -> None:
        self.client = client or WhatsAppCloudAPI()

    def send_invoice(self, invoice, recipient: str) -> None:
        link = invoice.pdf_file.url if invoice.pdf_file else ""
        body = (
            f"Your invoice {invoice.invoice_number} from Hexagare is ready.\n"
            f"Amount: Rs {invoice.grand_total}\n"
        )
        if link:
            body += f"Download: {link}"
        self.client.send_text(recipient, body)

    def send_low_stock_digest(self, alerts: list[dict], recipients: list[str]) -> None:
        body = _low_stock_digest_text(alerts)
        for recipient in recipients:
            self.client.send_text(recipient, body)


class EmailNotificationService:
    def send_invoice(self, invoice, recipient: str) -> None:
        link = invoice.pdf_file.url if invoice.pdf_file else ""
        body_lines = [
            f"Your invoice {invoice.invoice_number} from Hexagare is ready.",
            f"Amount: Rs {invoice.grand_total}",
        ]
        if link:
            body_lines.append(f"Download link: {link}")
        message = EmailMessage(
            subject=f"Invoice {invoice.invoice_number} from Hexagare",
            body="\n".join(body_lines),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
        )
        if invoice.pdf_file:
            with invoice.pdf_file.open("rb") as handle:
                message.attach(f"{invoice.invoice_number}.pdf", handle.read(), "application/pdf")
        message.send(fail_silently=False)

    def send_low_stock_digest(self, alerts: list[dict], recipients: list[str]) -> None:
        message = EmailMessage(
            subject=f"Hexagare: {len(alerts)} stock alert(s)",
            body=_low_stock_digest_text(alerts),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )
        message.send(fail_silently=False)


def _low_stock_digest_text(alerts: list[dict]) -> str:
    lines = [f"{len(alerts)} stock alert(s):", ""]
    for alert in alerts[:20]:
        variant = alert["variant"]
        location = alert["location"]["name"] if alert.get("location") else "all locations"
        lines.append(
            f"- [{alert['type']}] {variant['sku']} {variant['product_name']} "
            f"({location}): available {alert['available']}, threshold {alert['threshold']}"
        )
    if len(alerts) > 20:
        lines.append(f"...and {len(alerts) - 20} more.")
    return "\n".join(lines)


__all__ = [
    "EmailNotificationService",
    "WhatsAppCloudAPI",
    "WhatsAppNotificationService",
]
