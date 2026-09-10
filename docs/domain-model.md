# Domain Model

> Stub created in Phase 0. Each phase adds its section here as the models land.

## Accounts / RBAC

Built in Phase 1. See ADR-003 for the role-permission model rationale.

### Models (`apps/accounts/models.py`)

- **`User`** — `AbstractUser` with **email as the login identifier** (`USERNAME_FIELD = "email"`,
  no `username`), plus an optional `phone`. Custom `UserManager` (`create_user` / `create_superuser`
  take `email`). Set as `AUTH_USER_MODEL`.
- **`OperationalPermission`** — `managed = False`, no table. Exists only to give a dedicated
  `ContentType` for Hexagare's action-level permissions, keeping them separate from the model
  CRUD permissions Django auto-creates. Permission strings still resolve as `accounts.<codename>`.
- **`LoginHistory`** — append-only auth-event log (`login_success` / `login_failed` / `logout`,
  with `email_attempted`, `ip_address`, `user_agent`, `created_at`). Written by the auth views;
  expanded into the full activity/audit log in Phase 17.

### RBAC (`apps/accounts/rbac.py`)

- `OPERATIONAL_PERMISSIONS`: `{codename: label}` — the single source of truth for action-level
  permission codenames. Covers the permission areas in `HEXAGARE_FEATURES.md` §2 and reserves
  codenames for features not built yet (`pos`, `returns`, `stock_adjustments`,
  `purchases_receiving`, `integrations.amazon`, …). **Grep this file before inventing a codename.**
- `ROLE_PERMISSIONS`: `{role: {codename, …}}` for the four seed roles — **Admin** (all),
  **Manager** (all except `users.manage` / `settings.manage`), **Cashier** (POS / billing /
  customers), **Warehouse** (inventory / serials / receiving). Module load fails fast if a role
  references an unknown codename.
- `ensure_role_groups()`: idempotently materializes one `Permission` per codename (anchored to
  `OperationalPermission`'s content type), creates/syncs one `Group` per role, and prunes stale
  operational permissions. Wired to `post_migrate` in `apps/accounts/apps.py`, so `migrate` keeps
  groups current. Extra permissions manually added to a role group are left untouched.

### Enforcement (`apps/accounts/permissions.py`)

- `HasOperationalPermission(BasePermission)` — base class other apps extend. Grants access when
  the authenticated user holds **every** required codename (`required_permissions` on the class or
  the view); active superusers always pass. `require("pos", …)` builds a configured subclass for
  use in a viewset's `get_permissions()` (per-action gating).

### API (`/api/v1/auth/`)

`login/` · `refresh/` · `logout/` (blacklists the refresh token) · `profile/` (GET + PATCH own
profile) · `password/change/` · `password/reset/` + `password/reset/confirm/` (email sent via a
Celery task in `apps/accounts/tasks.py`). JWT via `rest_framework_simplejwt` (access 60 min,
refresh 1 day, rotation + blacklist). Login/refresh keep simplejwt's `{access, refresh}` shape
(login adds `user`); the list/error envelopes do not apply to token or single-resource responses.

## Catalog
_Not yet built (Phase 2)._ `Category` → `Product` → `ProductVariant`
(SKU + pricing are columns on `ProductVariant` — see ADR-002),
`ProductAttribute` / `ProductAttributeValue`, `ProductImage`, `LabelSize`.

## Serialized units
_Not yet built (Phase 3)._ `SerializedUnit` with immutable serial number and a
required `location` FK. See `serialized-units.md`.

## Inventory
_Not yet built (Phase 4)._ `Location`, `InventoryBalance` (read cache),
`InventoryTransaction` (immutable ledger). `InventoryService` is the only writer.

## Sales and billing
_Not yet built (Phases 7-8)._ `SalesChannel`, generic `Sale` / `SaleLine`
(derived totals via `SalesTotalsService`), `Payment`, `Invoice`,
`InvoiceDelivery`.

## Integrations (Amazon)
_Not yet built (Phase 9)._ `AmazonOrderSettlement` holds channel-specific
financials, keyed `(sale, sku)`. See `amazon-order-import.md`.

## Customers / Purchases / Suppliers / Expenses / Reports / Notifications
_Not yet built (later phases)._ Scaffold apps only.
