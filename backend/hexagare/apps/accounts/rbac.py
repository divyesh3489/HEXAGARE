"""Role-based access control: the single source of truth for operational
permissions and which role holds which.

`OPERATIONAL_PERMISSIONS` are Hexagare's own action-level permission codenames
(distinct from Django's model CRUD permissions). Some codenames are reserved
here for features not built yet -- grep this file before inventing a new one.

`ensure_role_groups()` materializes these into Django ``Permission`` rows
(anchored to the ``OperationalPermission`` content type, so they resolve as
``accounts.<codename>`` and stay separate from model CRUD permissions) and
syncs one ``Group`` per role. It is idempotent and runs from a ``post_migrate``
hook (see ``apps.accounts.apps``).

Enforcement is via ``apps.accounts.permissions.HasOperationalPermission``.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Operational permissions  (codename -> human-readable name)
# --------------------------------------------------------------------------- #
# Grouped by the permission areas in HEXAGARE_FEATURES.md section 2 and the
# navigation in section 56. Entries marked "reserved" gate a feature that a
# later phase implements; the codename is fixed now so roles are stable.
OPERATIONAL_PERMISSIONS: dict[str, str] = {
    # -- Catalog -----------------------------------------------------------
    "products.view": "View products, variants and SKUs",
    "products.manage": "Create and edit products, variants and SKUs",
    # -- Serialized units / serial numbers / barcodes ---------------------
    "serials.view": "View serialized units and serial-number history",
    "serials.manage": "Generate and edit serialized units",
    "barcode.scan": "Scan barcodes and look up units",
    # -- Inventory -------------------------------------------------------
    "inventory.view": "View inventory balances and the stock ledger",
    "inventory.transfer": "Transfer stock between locations",
    "stock_adjustments": "Adjust stock levels, manage locations and stock-level policies",
    # -- Sales / orders / POS ------------------------------------------
    "sales.view": "View orders and sales",
    "orders.manage": "Edit and cancel orders",
    "pos": "Create bills at the point of sale",  # reserved (Phase 8)
    "returns": "Process sales returns",  # reserved (Phase 10)
    # -- Billing -------------------------------------------------------
    "billing.view": "View invoices and payments",
    "billing.manage": "Create and cancel invoices, record payments",
    # -- Purchases / suppliers --------------------------------------
    "purchases.view": "View purchase orders and suppliers",
    "purchases_receiving": "Receive stock against a purchase order",  # reserved (Phase 12)
    "suppliers.manage": "Create and edit suppliers",
    # -- Finance -----------------------------------------------------
    "finance.view": "View finance and profit summaries",
    "expenses.manage": "Create and edit expenses",
    # -- Customers -------------------------------------------------
    "customers.view": "View customers and their history",
    "customers.manage": "Create and edit customers",
    # -- Integrations --------------------------------------------
    "integrations.amazon": "Import Amazon orders and manage Amazon settings",  # reserved (Phase 9)
    # -- Reports ------------------------------------------------
    "reports.view": "View reports",
    "reports.export": "Export report data",
    # -- Administration ------------------------------------
    "settings.manage": "Change business, tax and system settings",
    "users.manage": "Manage users, roles and permissions",
    "audit.view": "View the activity / audit log",
}

_ALL: set[str] = set(OPERATIONAL_PERMISSIONS)

# --------------------------------------------------------------------------- #
# Roles  (role name -> set of operational permission codenames)
# --------------------------------------------------------------------------- #
ROLE_ADMIN = "Admin"
ROLE_MANAGER = "Manager"
ROLE_CASHIER = "Cashier"
ROLE_WAREHOUSE = "Warehouse"

ROLES: tuple[str, ...] = (ROLE_ADMIN, ROLE_MANAGER, ROLE_CASHIER, ROLE_WAREHOUSE)

ROLE_PERMISSIONS: dict[str, set[str]] = {
    ROLE_ADMIN: set(_ALL),
    ROLE_MANAGER: _ALL - {"users.manage", "settings.manage"},
    ROLE_CASHIER: {
        "products.view",
        "serials.view",
        "barcode.scan",
        "inventory.view",
        "sales.view",
        "orders.manage",
        "pos",
        "returns",
        "billing.view",
        "billing.manage",
        "customers.view",
        "customers.manage",
    },
    ROLE_WAREHOUSE: {
        "products.view",
        "serials.view",
        "serials.manage",
        "barcode.scan",
        "inventory.view",
        "inventory.transfer",
        "stock_adjustments",
        "purchases.view",
        "purchases_receiving",
    },
}

# Fail fast if a role references a codename that does not exist.
for _role, _codenames in ROLE_PERMISSIONS.items():
    _unknown = _codenames - _ALL
    if _unknown:
        raise RuntimeError(f"Role {_role!r} references unknown permissions: {sorted(_unknown)}")


def ensure_role_groups(**kwargs) -> None:
    """Create/update the operational ``Permission`` rows and role ``Group``s.

    Idempotent. Safe to call from a ``post_migrate`` receiver and directly from
    tests. Only touches permissions and groups it owns -- any extra permission
    manually added to a role group is left in place.
    """
    from django.contrib.auth.models import Group, Permission
    from django.contrib.contenttypes.models import ContentType

    from .models import OperationalPermission

    content_type = ContentType.objects.get_for_model(OperationalPermission)

    perms: dict[str, Permission] = {}
    for codename, name in OPERATIONAL_PERMISSIONS.items():
        perm, _ = Permission.objects.update_or_create(
            content_type=content_type,
            codename=codename,
            defaults={"name": name},
        )
        perms[codename] = perm

    # Drop operational Permission rows that are no longer defined.
    Permission.objects.filter(content_type=content_type).exclude(
        codename__in=OPERATIONAL_PERMISSIONS
    ).delete()

    for role, codenames in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=role)
        desired = {perms[c] for c in codenames}
        current = set(
            group.permissions.filter(
                content_type=content_type, codename__in=OPERATIONAL_PERMISSIONS
            )
        )
        if current != desired:
            group.permissions.remove(*(current - desired))
            group.permissions.add(*(desired - current))
