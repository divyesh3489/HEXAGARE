"""Serial-number allocation and the serialized-unit lifecycle.

The one hard guarantee here is that a serial number is **never handed out
twice**. Each ``ProductVariant`` has its own gap-tolerant counter
(``SerializedUnit.sequence``); the next value is read and the row inserted
inside a single transaction while holding a *per-variant* Postgres advisory
lock, so two concurrent generators for the same variant serialise while
generators for different variants run in parallel. ``(variant, sequence)`` is
also unique at the database level as a backstop.

Contrast ``apps.products.services.sku`` -- SKU suggestion takes no lock because
a losing race there just means the caller retries with the next candidate. A
serial sequence has to be gapless-by-construction, so it does.

Format: ``<HEXAGARE_SERIAL_PREFIX><variant token>-<zero-padded sequence>``
(e.g. ``HXMP1123-000001``). Prefix and padding come from the
``HEXAGARE_SERIAL_PREFIX`` / ``HEXAGARE_SERIAL_PADDING`` settings. The variant
token is ``ProductVariant.code`` when set, otherwise a token derived from the
SKU. See ``docs/serialized-units.md``.
"""

from __future__ import annotations

import re

from django.conf import settings
from django.db import connection, models, transaction
from django.http import Http404
from rest_framework.exceptions import ValidationError

#: Namespace key for ``pg_advisory_xact_lock(namespace, variant_id)`` -- keeps
#: serial allocation from colliding with any other advisory lock the app takes.
_ADVISORY_LOCK_NAMESPACE = 1001

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")


def _variant_token(variant) -> str:
    """A short ``A-Z0-9`` token identifying the variant inside a serial.

    ``ProductVariant.code`` if it carries one, otherwise the SKU with the
    configured SKU prefix and separators stripped. Capped at 16 characters;
    ``"V"`` if nothing usable is left.
    """
    raw = (getattr(variant, "code", "") or "").strip()
    if not raw:
        raw = (getattr(variant, "sku", "") or "").strip()
        sku_prefix = getattr(settings, "HEXAGARE_SKU_PREFIX", "HEX")
        if sku_prefix and raw.upper().startswith(sku_prefix.upper()):
            raw = raw[len(sku_prefix):]
    token = _NON_ALNUM.sub("", raw.upper())[:16]
    return token or "V"


def format_serial(variant, sequence: int) -> str:
    prefix = getattr(settings, "HEXAGARE_SERIAL_PREFIX", "HX")
    padding = getattr(settings, "HEXAGARE_SERIAL_PADDING", 6)
    return f"{prefix}{_variant_token(variant)}-{sequence:0{padding}d}"


def allocate_serial(variant) -> tuple[str, int]:
    """Reserve and return ``(serial_number, sequence)`` for ``variant``.

    Must be called inside an open transaction (``create_unit`` handles this) --
    the advisory lock is released when that transaction ends.
    """
    from apps.products.models import SerializedUnit

    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("allocate_serial() must run inside a transaction.")

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s, %s)",
            [_ADVISORY_LOCK_NAMESPACE, variant.pk],
        )

    highest = SerializedUnit.objects.filter(variant=variant).aggregate(
        top=models.Max("sequence")
    )["top"] or 0
    sequence = highest + 1
    return format_serial(variant, sequence), sequence


@transaction.atomic
def create_unit(
    *,
    variant,
    location,
    status: str | None = None,
    purchase_cost=None,
    actor=None,
):
    """Allocate a serial and create one :class:`SerializedUnit`.

    Writes the opening :class:`SerializedUnitEvent` and the opening
    :class:`~apps.inventory.models.InventoryTransaction` (stock ledger) in the
    same atomic block -- from Phase 4 a unit entering stock is a ledger event
    (ADR-009).  Bulk generation + label PDFs are Phase 5; this is the
    single-unit path.
    """
    from apps.inventory.services.ledger import InventoryService
    from apps.products.models import SerializedUnit, SerializedUnitEvent

    status = status or SerializedUnit.Status.GENERATED
    if status not in SerializedUnit.INITIAL_STATUSES:
        raise ValidationError(
            {"status": f"A new unit must start as one of "
                       f"{sorted(SerializedUnit.INITIAL_STATUSES)}."}
        )

    serial_number, sequence = allocate_serial(variant)
    unit = SerializedUnit.objects.create(
        variant=variant,
        location=location,
        serial_number=serial_number,
        sequence=sequence,
        status=status,
        purchase_cost=purchase_cost,
        created_by=actor if getattr(actor, "is_authenticated", False) else None,
    )
    SerializedUnitEvent.objects.create(
        unit=unit,
        from_status="",
        to_status=status,
        location=location,
        note="created",
        actor=actor if getattr(actor, "is_authenticated", False) else None,
    )
    InventoryService.opening(unit=unit, actor=actor)
    return unit


@transaction.atomic
def transition_unit(
    unit,
    *,
    to_status: str,
    location=None,
    actor=None,
    note: str = "",
):
    """Apply a single status move along ``ALLOWED_TRANSITIONS``.

    Locks the unit row for the duration. This is the Phase 3 status-only path:
    it does **not** touch the (not-yet-built) stock ledger. From Phase 4, moves
    tied to a business action go through ``SerializedInventoryService`` instead.
    """
    from apps.products.models import SerializedUnit, SerializedUnitEvent

    unit = SerializedUnit.objects.select_for_update().get(pk=unit.pk)
    from_status = unit.status

    if to_status == from_status:
        raise ValidationError({"status": "The unit is already in that status."})
    if not unit.can_transition_to(to_status):
        allowed = ", ".join(unit.allowed_transitions) or "none (terminal status)"
        raise ValidationError(
            {"status": f"Cannot move a unit from {from_status} to {to_status}. "
                       f"Allowed from {from_status}: {allowed}."}
        )

    unit.status = to_status
    update_fields = ["status", "updated_at"]
    if location is not None and location.pk != unit.location_id:
        unit.location = location
        update_fields.append("location")
    unit.save(update_fields=update_fields)

    SerializedUnitEvent.objects.create(
        unit=unit,
        from_status=from_status,
        to_status=to_status,
        location=unit.location,
        note=note,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
    )
    return unit


def resolve_unit(code: str):
    """Look a unit up by serial number (or a scanned barcode, which is the same
    string). Raises :class:`~django.http.Http404` when nothing matches."""
    from apps.products.models import SerializedUnit

    code = (code or "").strip()
    if not code:
        raise ValidationError({"code": "A serial number or barcode is required."})
    try:
        return (
            SerializedUnit.objects.select_related(
                "variant__product__category", "location"
            )
            .prefetch_related("events__location", "events__actor")
            .get(serial_number__iexact=code)
        )
    except SerializedUnit.DoesNotExist:
        raise Http404(f"No serialized unit matches {code!r}.")
