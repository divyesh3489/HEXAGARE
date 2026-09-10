"""The operational-permission base class every other app builds on.

Usage in a viewset (gate per action via ``get_permissions()``)::

    from apps.accounts.permissions import require

    class ProductViewSet(viewsets.ModelViewSet):
        def get_permissions(self):
            if self.action in {"list", "retrieve"}:
                return [require("products.view")()]
            return [require("products.manage")()]

Or subclass directly::

    class CanScanBarcode(HasOperationalPermission):
        required_permissions = ("barcode.scan",)

Permission codenames are defined in :mod:`apps.accounts.rbac`. They resolve
against Django's permission system as ``accounts.<codename>`` (the rows are
anchored to the ``OperationalPermission`` content type by
``ensure_role_groups()``).
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission

#: App label the operational ``Permission`` rows are anchored to.
PERMISSION_APP_LABEL = "accounts"


def _qualified(codename: str) -> str:
    if codename.startswith(f"{PERMISSION_APP_LABEL}."):
        return codename
    return f"{PERMISSION_APP_LABEL}.{codename}"


class HasOperationalPermission(BasePermission):
    """Grants access when the authenticated user holds *every* required
    operational permission.

    The required set is read from ``view.required_permissions`` if present,
    otherwise from this class's ``required_permissions``. An empty set means
    "authenticated is enough". Active superusers always pass (Django's
    ``has_perm`` short-circuits for them).
    """

    required_permissions: tuple[str, ...] = ()
    message = "You do not have permission to perform this action."

    def get_required_permissions(self, view) -> tuple[str, ...]:
        perms = getattr(view, "required_permissions", None)
        if perms is None:
            perms = self.required_permissions
        if isinstance(perms, str):
            perms = (perms,)
        return tuple(perms)

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated):
            return False
        required = self.get_required_permissions(view)
        if not required:
            return True
        return all(user.has_perm(_qualified(codename)) for codename in required)

    def has_object_permission(self, request, view, obj) -> bool:
        return self.has_permission(request, view)


def require(*codenames: str) -> type[HasOperationalPermission]:
    """Build a ``HasOperationalPermission`` subclass requiring ``codenames``.

    Handy inside ``get_permissions()``: ``return [require("pos")()]``.
    """
    attrs = {"required_permissions": tuple(codenames)}
    if codenames:
        name = "Requires_" + "_".join(c.replace(".", "_") for c in codenames)
    else:
        name = "Requires_none"
    return type(name, (HasOperationalPermission,), attrs)
