"""Invoice-number allocation.

Same shape as ``apps.products.services.serial_numbers.allocate_serial``
(ADR-008): a single global counter (``Invoice.sequence``) behind a Postgres
advisory lock, read via a ``Max()`` aggregate so allocation stays O(1) as the
table grows. A different namespace key from the serial allocator's ``1001``
-- see ADR-013.

Format: ``<HEXAGARE_INVOICE_PREFIX>-<zero-padded sequence>`` (e.g.
``HEX-INV-001245``, HEXAGARE_FEATURES.md section 28). Prefix/padding come
from the editable ``apps.accounts.BusinessSettings`` singleton when set,
otherwise the env-backed settings (Phase 17).
"""

from __future__ import annotations

from django.conf import settings
from django.db import connection, models, transaction

#: Namespace key for ``pg_advisory_xact_lock(namespace, 0)`` -- distinct from
#: the serial allocator's ``1001``.
_ADVISORY_LOCK_NAMESPACE = 1002


def format_invoice_number(sequence: int) -> str:
    from apps.accounts.models import BusinessSettings

    try:
        business_settings = BusinessSettings.get_solo()
    except Exception:  # noqa: BLE001 - table not migrated yet
        business_settings = None
    prefix = (business_settings and business_settings.invoice_prefix) or getattr(
        settings, "HEXAGARE_INVOICE_PREFIX", "HEX-INV"
    )
    padding = (business_settings and business_settings.invoice_padding) or getattr(
        settings, "HEXAGARE_INVOICE_PADDING", 6
    )
    return f"{prefix}-{sequence:0{padding}d}"


def allocate_invoice_number() -> tuple[str, int]:
    """Reserve and return ``(invoice_number, sequence)``.

    Must run inside an open transaction -- the lock releases when it ends.
    """
    from ..models import Invoice

    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("allocate_invoice_number() must run inside a transaction.")

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [_ADVISORY_LOCK_NAMESPACE, 0])

    highest = Invoice.objects.aggregate(top=models.Max("sequence"))["top"] or 0
    sequence = highest + 1
    return format_invoice_number(sequence), sequence


__all__ = ["allocate_invoice_number", "format_invoice_number"]
