"""``SerializedInventoryService`` -- the only path allowed to change a serialized
unit's status as part of a business action.

Each method locks the unit row, applies the model's ``ALLOWED_TRANSITIONS`` state
machine via :func:`apps.products.services.serial_numbers.transition_unit` (which
also writes the unit's ``SerializedUnitEvent`` history), and records the matching
:class:`~apps.inventory.models.InventoryTransaction` ledger pair through
:class:`~apps.inventory.services.ledger.InventoryService` -- all in one
``transaction.atomic`` block, so the unit's status and the stock ledger can never
drift apart.

**Intentional gap.** The plain ``POST /products/serialized-units/{id}/transition/``
endpoint from Phase 3 stays available for status-only corrections and does
**not** touch the ledger. Using it for a move that has stock meaning will leave
:class:`InventoryBalance` stale until ``manage.py rebuild_inventory_balances``
runs. This is documented in ``docs/serialized-units.md`` ("Mutation path") and
``docs/inventory-ledger.md``; it matches CLAUDE.md's note that the two paths are
deliberately separate.
"""

from __future__ import annotations

from django.db import transaction

from apps.inventory.models import InventoryTransaction
from apps.inventory.services.ledger import InventoryService

from ..models import SerializedUnit
from .serial_numbers import create_unit, transition_unit

_Kind = InventoryTransaction.Kind
_Status = SerializedUnit.Status


class SerializedInventoryService:
    """Namespace of unit-lifecycle operations. Not instantiated."""

    # -- creation --------------------------------------------------------
    @staticmethod
    @transaction.atomic
    def generate(
        *, variant, location, status=None, purchase_cost=None, actor=None
    ) -> SerializedUnit:
        """Create one unit and its opening ledger row (``create_unit`` writes the
        ``OPENING`` :class:`InventoryTransaction`)."""
        return create_unit(
            variant=variant,
            location=location,
            status=status,
            purchase_cost=purchase_cost,
            actor=actor,
        )

    # -- the shared engine -------------------------------------------------
    @staticmethod
    @transaction.atomic
    def _apply(
        unit, *, to_status, kind, to_location=None, actor=None, note="", reference=None
    ) -> SerializedUnit:
        locked = (
            SerializedUnit.objects.select_for_update(of=("self",))
            .select_related("variant", "location")
            .get(pk=unit.pk)
        )
        from_status = locked.status
        from_location = locked.location

        unit = transition_unit(
            locked,
            to_status=to_status,
            location=to_location,
            actor=actor,
            note=note,
        )
        InventoryService.move_unit(
            unit=unit,
            from_location=from_location,
            from_status=from_status,
            to_location=unit.location,
            to_status=unit.status,
            kind=kind,
            reference=reference,
            note=note,
            actor=actor,
        )

        from apps.accounts.audit import log_activity
        from apps.accounts.models import AuditLogEntry

        changes = {"status": {"old": from_status, "new": unit.status}}
        if from_location_id := getattr(from_location, "pk", None):
            if from_location_id != unit.location_id:
                changes["location"] = {"old": str(from_location), "new": str(unit.location)}
        log_activity(
            actor=actor,
            action=AuditLogEntry.Action.STATUS_CHANGED,
            target=unit,
            changes=changes,
        )
        return unit

    # -- reservation (Phase 7 / 8) -------------------------------------
    @classmethod
    def reserve(cls, unit, *, actor=None, note="", reference=None):
        return cls._apply(unit, to_status=_Status.RESERVED, kind=_Kind.RESERVE,
                          actor=actor, note=note, reference=reference)

    @classmethod
    def release(cls, unit, *, actor=None, note="", reference=None):
        return cls._apply(unit, to_status=_Status.AVAILABLE, kind=_Kind.RELEASE,
                          actor=actor, note=note, reference=reference)

    # -- stock transfer (Phase 4) -----------------------------------
    @classmethod
    def start_transfer(cls, unit, *, actor=None, note="", reference=None):
        """``AVAILABLE -> IN_TRANSIT``; the unit stays recorded at its current
        location until it is received."""
        return cls._apply(unit, to_status=_Status.IN_TRANSIT, kind=_Kind.TRANSFER_OUT,
                          actor=actor, note=note, reference=reference)

    @classmethod
    def complete_transfer(cls, unit, *, to_location, actor=None, note="", reference=None):
        """``IN_TRANSIT -> AVAILABLE`` at ``to_location``."""
        return cls._apply(unit, to_status=_Status.AVAILABLE, to_location=to_location,
                          kind=_Kind.TRANSFER_IN, actor=actor, note=note, reference=reference)

    @classmethod
    def cancel_transfer(cls, unit, *, actor=None, note="", reference=None):
        """``IN_TRANSIT -> AVAILABLE`` at the unit's current (source) location."""
        return cls._apply(unit, to_status=_Status.AVAILABLE, kind=_Kind.TRANSFER_IN,
                          actor=actor, note=note, reference=reference)

    # -- sale / return / write-off ------------------------------
    @classmethod
    def sell(cls, unit, *, actor=None, note="", reference=None):
        return cls._apply(unit, to_status=_Status.SOLD, kind=_Kind.SALE,
                          actor=actor, note=note, reference=reference)

    @classmethod
    def return_unit(cls, unit, *, actor=None, note="", reference=None):
        return cls._apply(unit, to_status=_Status.RETURNED, kind=_Kind.RETURN,
                          actor=actor, note=note, reference=reference)

    @classmethod
    def damage(cls, unit, *, actor=None, note="", reference=None):
        return cls._apply(unit, to_status=_Status.DAMAGED, kind=_Kind.DAMAGE,
                          actor=actor, note=note, reference=reference)

    @classmethod
    def lose(cls, unit, *, actor=None, note="", reference=None):
        return cls._apply(unit, to_status=_Status.LOST, kind=_Kind.LOSS,
                          actor=actor, note=note, reference=reference)

    @classmethod
    def restore(cls, unit, *, actor=None, note="", reference=None):
        """``DAMAGED``/``LOST``/``RETURNED`` -> ``AVAILABLE``."""
        return cls._apply(unit, to_status=_Status.AVAILABLE, kind=_Kind.RESTORE,
                          actor=actor, note=note, reference=reference)

    @classmethod
    def cancel(cls, unit, *, actor=None, note="", reference=None):
        """``GENERATED``/``RESERVED`` -> ``CANCELLED`` (terminal)."""
        return cls._apply(unit, to_status=_Status.CANCELLED, kind=_Kind.CANCEL,
                          actor=actor, note=note, reference=reference)
