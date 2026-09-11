"""The ``Sale`` totals writer.

``SalesTotalsService`` is the **only** code allowed to write
``Sale.subtotal``/``discount_total``/``tax_total``/``grand_total`` (CLAUDE.md;
ADR-012). ``recalculate`` locks the ``Sale`` row and recomputes every total
from its lines' derived properties (:class:`apps.sales.models.SaleLine`), the
same lock-then-write shape as ``apps.inventory.services.ledger.InventoryService``.

Call it explicitly at the end of any action that creates, updates or removes a
``SaleLine`` -- there is no signal wiring it up automatically (this codebase
has none; call-sites stay explicit and greppable).
"""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction

from ..models import Sale

_ZERO = Decimal("0.00")


class SalesTotalsService:
    """Namespace of totals operations. Not instantiated."""

    @staticmethod
    @transaction.atomic
    def recalculate(sale: Sale) -> Sale:
        """Recompute ``sale``'s derived totals from its current lines.

        Takes a row lock on the ``Sale`` so concurrent line edits on the same
        sale serialise. Returns the refreshed, locked instance.
        """
        sale = Sale.objects.select_for_update().get(pk=sale.pk)

        subtotal = _ZERO
        discount_total = _ZERO
        tax_total = _ZERO
        for line in sale.lines.all():
            subtotal += line.taxable_value
            discount_total += line.discount_amount
            tax_total += line.tax_amount

        sale.subtotal = subtotal
        sale.discount_total = discount_total
        sale.tax_total = tax_total
        sale.grand_total = subtotal + tax_total
        sale.save(update_fields=["subtotal", "discount_total", "tax_total", "grand_total"])
        return sale
