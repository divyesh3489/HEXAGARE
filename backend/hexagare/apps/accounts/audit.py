"""Activity/audit logging (Phase 17, HEXAGARE_FEATURES.md section 53).

Hexagare's architecture already funnels almost every mutation through one
canonical place -- a ``ModelViewSet``'s ``perform_create``/``perform_update``/
``perform_destroy`` for plain CRUD resources, or a single named ``*Service``
method for anything with real business logic (``SerializedInventoryService``,
``InventoryService``, ``CompleteSaleService``, ``ReturnService``, ...). So
rather than adding a bespoke ``AuditLogEntry.objects.create(...)`` call inside
every view/action, there are exactly two hook shapes:

1. :class:`AuditMixin` -- add it to a simple CRUD viewset's base classes and
   create/update/delete are logged automatically, with a generic before/after
   diff for updates.
2. :func:`log_activity` -- call it directly, once, from inside the one
   service method that already owns a non-CRUD mutation (a sale completing,
   a unit changing status, a return being processed, ...).
"""

from __future__ import annotations

from typing import Any

from django.contrib.contenttypes.models import ContentType

#: Never diffed/stored, even if a viewset audits the model that has them.
_SENSITIVE_FIELDS = {"password"}


def _model_fields(instance) -> dict[str, Any]:
    """A shallow ``{field_name: value}`` snapshot of an instance's concrete,
    non-relation-reverse fields -- enough for a human-readable diff."""
    snapshot = {}
    for field in instance._meta.concrete_fields:
        if field.name in _SENSITIVE_FIELDS:
            continue
        try:
            snapshot[field.name] = field.value_from_object(instance)
        except Exception:  # noqa: BLE001 - never let a diff crash the request
            continue
    return snapshot


def diff_fields(before: dict[str, Any], after: dict[str, Any]) -> dict[str, dict[str, Any]]:
    changes = {}
    for key, new_value in after.items():
        old_value = before.get(key)
        if old_value != new_value:
            changes[key] = {"old": old_value, "new": new_value}
    return changes


def log_activity(
    *,
    actor=None,
    action: str,
    target=None,
    changes: dict | None = None,
    ip_address: str | None = None,
    model=None,
    object_id: int | str | None = None,
    object_repr: str | None = None,
) -> "AuditLogEntry | None":  # noqa: F821, UP037 - forward ref, avoids a module cycle
    """Write one :class:`AuditLogEntry`. Never raises -- a logging failure
    must never break the business action it's describing.

    Pass ``target`` (a live model instance) for create/update. For a delete --
    where the instance's pk is already cleared by the time Django's
    ``Model.delete()`` returns -- pass ``model``/``object_id``/``object_repr``
    captured *before* the delete instead.
    """
    from .models import AuditLogEntry

    try:
        entry = AuditLogEntry(
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            action=action,
            changes=changes or {},
            ip_address=ip_address,
        )
        if target is not None:
            entry.content_type = ContentType.objects.get_for_model(target)
            entry.object_id = str(target.pk)
            entry.object_repr = str(target)[:255]
        elif model is not None:
            entry.content_type = ContentType.objects.get_for_model(model)
            entry.object_id = str(object_id) if object_id is not None else ""
            entry.object_repr = (object_repr or "")[:255]
        entry.save()
        return entry
    except Exception:  # noqa: BLE001 - audit logging is best-effort
        import logging

        logging.getLogger(__name__).exception("Failed to write audit log entry (%s)", action)
        return None


class AuditMixin:
    """Mix into a ``ModelViewSet`` (before it in the MRO) to log create/update/
    delete automatically, with a generic field diff on update.

    ``audit_created_action`` / ``audit_updated_action`` / ``audit_deleted_action``
    (``AuditLogEntry.Action`` values) select which action code each maps to;
    a viewset that only wants a subset can leave the others unset (``None``
    skips logging that verb entirely).
    """

    audit_created_action: str | None = None
    audit_updated_action: str | None = None
    audit_deleted_action: str | None = None

    def _actor(self):
        user = getattr(self.request, "user", None)
        return user if getattr(user, "is_authenticated", False) else None

    def _ip(self) -> str | None:
        from apps.common.utils import get_client_ip

        return get_client_ip(self.request)

    def perform_create(self, serializer):
        super().perform_create(serializer)
        if self.audit_created_action:
            log_activity(
                actor=self._actor(),
                action=self.audit_created_action,
                target=serializer.instance,
                ip_address=self._ip(),
            )

    def perform_update(self, serializer):
        before = _model_fields(serializer.instance)
        super().perform_update(serializer)
        if self.audit_updated_action:
            after = _model_fields(serializer.instance)
            changes = diff_fields(before, after)
            if changes:
                log_activity(
                    actor=self._actor(),
                    action=self.audit_updated_action,
                    target=serializer.instance,
                    changes=changes,
                    ip_address=self._ip(),
                )

    def perform_destroy(self, instance):
        action = self.audit_deleted_action
        model = type(instance)
        object_id = instance.pk
        object_repr = str(instance)
        super().perform_destroy(instance)
        if action:
            log_activity(
                actor=self._actor(),
                action=action,
                model=model,
                object_id=object_id,
                object_repr=object_repr,
                ip_address=self._ip(),
            )
