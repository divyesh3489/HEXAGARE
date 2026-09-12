"""Celery tasks for the notifications app (Phase 15).

``send_invoice_delivery`` sends one already-created
:class:`~apps.billing.models.InvoiceDelivery` over its channel and updates its
status -- enqueued via ``transaction.on_commit`` right after
``InvoiceViewSet.send`` creates the row (CLAUDE.md's Celery pattern: commit
first, enqueue after).

``send_low_stock_alerts`` is a periodic task (see ``CELERY_BEAT_SCHEDULE`` in
``hexagare/settings/base.py``) that reuses
``apps.inventory.services.alerts.compute_alerts`` (Phase 4) and sends a
digest to whichever recipients are configured -- a no-op, not an error, when
none are.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task
def send_invoice_delivery(delivery_id: int) -> str:
    from apps.billing.models import InvoiceDelivery

    from .services import EmailNotificationService, WhatsAppNotificationService

    try:
        delivery = InvoiceDelivery.objects.select_related("invoice__sale").get(pk=delivery_id)
    except InvoiceDelivery.DoesNotExist:
        return "missing"

    try:
        if delivery.channel == InvoiceDelivery.Channel.EMAIL:
            EmailNotificationService().send_invoice(delivery.invoice, delivery.recipient)
        elif delivery.channel == InvoiceDelivery.Channel.WHATSAPP:
            WhatsAppNotificationService().send_invoice(delivery.invoice, delivery.recipient)
        else:  # pragma: no cover - channel is a validated ChoiceField
            raise ValueError(f"Unknown delivery channel: {delivery.channel}")
    except Exception as exc:  # noqa: BLE001 - record and stop; recoverable
        logger.exception("Invoice delivery %s failed", delivery_id)
        InvoiceDelivery.objects.filter(pk=delivery_id).update(
            status=InvoiceDelivery.Status.FAILED,
            error_message=str(exc)[:2000],
        )
        return "failed"

    InvoiceDelivery.objects.filter(pk=delivery_id).update(
        status=InvoiceDelivery.Status.SENT,
        sent_at=timezone.now(),
        error_message="",
    )
    return "sent"


@shared_task
def send_low_stock_alerts() -> str:
    from apps.inventory.services.alerts import compute_alerts

    from .services import EmailNotificationService, WhatsAppNotificationService

    alerts = [
        a for a in compute_alerts() if a["type"] in ("out_of_stock", "low_stock")
    ]
    if not alerts:
        return "no-alerts"

    email_recipients = settings.LOW_STOCK_ALERT_EMAILS
    whatsapp_recipients = settings.LOW_STOCK_ALERT_WHATSAPP_TO
    if not email_recipients and not whatsapp_recipients:
        return "no-recipients"

    if email_recipients:
        try:
            EmailNotificationService().send_low_stock_digest(alerts, email_recipients)
        except Exception:  # noqa: BLE001 - one channel failing shouldn't skip the other
            logger.exception("Low-stock email digest failed")

    if whatsapp_recipients:
        try:
            WhatsAppNotificationService().send_low_stock_digest(alerts, whatsapp_recipients)
        except Exception:  # noqa: BLE001
            logger.exception("Low-stock WhatsApp digest failed")

    return f"sent ({len(alerts)} alerts)"
