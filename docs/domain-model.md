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

Built in Phase 2 (`apps/products`). Serialized units, barcodes and bulk generation come in Phases
3 & 5. See ADR-002 (SKU as a column), ADR-004 (data-driven attributes, advisory SKU suggestion)
and ADR-005 (product-level default pricing, nullable variant overrides, derived discount).

### Models (`apps/products/models.py`)

- **`Category`** — self-referential tree (`parent` FK, `on_delete=PROTECT`). `slug` auto-filled
  from `name`; `code` (short token, upper-cased on save, e.g. `MP`) feeds SKU suggestions.
- **`Product`** — `name`, `code`, `description`, `category` (FK, `PROTECT`), `brand` (plain
  `CharField`, not a model), `status` (`active` / `inactive` / `draft` / `discontinued`),
  `hsn_sac`, `weight` (kg), `dimensions` (free text), `tags` (`JSONField` list of strings),
  `notes`, plus **optional default pricing** — `mrp`, `selling_price` (GST-inclusive),
  `purchase_price`, `tax_rate` (all nullable). `discount_amount` / `discount_percent` are
  derived read-only properties.
- **`ProductVariant`** — `product` FK (`CASCADE`), optional `name` / `code`, **`sku`
  (`unique`, indexed)**, optional `barcode`. The four price columns — `mrp`, `selling_price`
  (**GST-inclusive**), `purchase_price`, `tax_rate` (GST %) — are **nullable overrides**:
  `NULL` inherits the product's default (ADR-005). `is_active` doubles as SKU activation.
  Derived **properties** (2 dp, `ROUND_HALF_UP`), all from the *effective* figures
  (variant override → product default → `0`): `effective_mrp` / `effective_selling_price` /
  `effective_purchase_price` / `effective_tax_rate`; `base_price =
  effective_selling_price / (1 + effective_tax_rate/100)`;
  `gst_amount = effective_selling_price − base_price`; `cgst_amount` / `sgst_amount` (even split
  of `gst_amount`); `discount_amount = max(effective_mrp − effective_selling_price, 0)` and
  `discount_percent`. The serializer rejects a variant whose effective `selling_price` or `mrp`
  resolves to `NULL`.
  **Availability (ADR-006):** `is_active` is the per-variant *intent*; `effective_status`
  (a `Product.Status` value) and `is_available` (bool) are derived — a product that is
  `draft` / `inactive` / `discontinued` overrides every variant to that status, and only an
  `active` product defers to `is_active`. `ProductVariant`'s list endpoint takes `?available=1`;
  `ProductListSerializer` exposes `available_variant_count` (`0` unless the product is active).
- **`ProductAttribute`** — reusable variant-property definition (`name`, unique `code`,
  `is_active`). Global list; adding "Finish" is a row, not a migration.
- **`ProductAttributeValue`** — join row: `variant` (`CASCADE`) × `attribute` (`PROTECT`) →
  `value`. Unique per `(variant, attribute)`. This is how size / colour / material are stored —
  never product-specific columns.
- **`ProductImage`** — `product` FK (`CASCADE`), optional `variant` FK, `image`
  (`ImageField`, via `STORAGES["default"]` — S3 in staging/prod, media volume in dev), `alt_text`,
  `is_primary`, `sort_order`. Requires **Pillow**.
- **`LabelSize`** — label / sheet geometry for the Phase 5 label-PDF renderer (`width_mm`,
  `height_mm`, `columns`, `rows`, `margin_mm`, `gutter_mm`, `orientation`, `is_default`). Two
  defaults (`a4-24up`, `thermal-50x25`) seeded idempotently via a `post_migrate` hook
  (`apps/products/bootstrap.py`).

### SKU suggestion (`apps/products/services/sku.py`)

- `suggest_sku(category, product, variant_code, attribute_values)` →
  `<HEXAGARE_SKU_PREFIX>-<CATEGORY CODE>-<VARIANT FRAGMENT>-<NNN>` (e.g. `HEX-MP-11X23-001`).
  Fragment falls back category code → name initials, variant code → attribute values → product
  code / initials. The 3-digit sequence starts past the highest existing value on the same stem
  and increments past collisions.
- `is_sku_available(sku, exclude_variant_id=None)` — case-insensitive.
- **Advisory only** (ADR-004): no advisory lock. The `ProductVariant.sku` unique constraint plus
  the serializer's availability check are the guard; a suggestion race just yields a
  `validation_error` envelope and a retry.

### API (`/api/v1/products/`)

`SimpleRouter` viewsets — `` (products), `categories/`, `attributes/`, `variants/`, `images/`,
`label-sizes/` — plus `sku/suggest/` (POST) and `sku/check/` (GET). Every viewset gates per
action via `get_permissions()`: `products.view` for `list` / `retrieve`, `products.manage` for
writes. `ProductViewSet` uses a light list serializer (name, category, brand, status,
`variant_count`, price range, primary image) and a detail serializer with nested read-only
`variants` + `images`; filters: `?category=` / `?status=` / `?brand=` / `?search=`.
`ProductVariantSerializer` accepts nested writable `attribute_values`, auto-fills `sku` when
blank, takes the four price columns as `null`-able overrides (omit or send `null` to inherit the
product default), and exposes the `effective_*` / `base_price` / `gst_amount` / `discount_*`
figures read-only. `ProductDetailSerializer` carries the product's own default pricing +
`discount_amount` / `discount_percent`. Images accept multipart upload; the write field is
`image`, reads return `image_url`. `image_url`
is **storage-relative** — an absolute `https://…` S3 URL in staging/production, a root-relative
`/media/…` path in development (the browser resolves it against its own origin; the Vite dev proxy
forwards `/media` to the backend). The serializer never calls `request.build_absolute_uri()` —
behind the dev proxy that host is the container name. An image may be scoped to a single variant
via its optional `variant` FK (validated to belong to the image's product) or left product-wide
(`variant` null); `?variant=` filters the list, and the product-detail UI groups the image grid
by scope and can re-assign an image between scopes.

## Serialized units

Built in Phase 3 (`apps/products`). Full detail — serial format, advisory-lock
reasoning, state machine, mutation path — in `serialized-units.md`. See ADR-008.

### Models (`apps/products/models.py`)

- **`SerializedUnit`** — one physical unit of a `ProductVariant`. `variant` FK
  (`PROTECT`); **`serial_number`** (`unique`, `editable=False`, immutable, never
  reused) formatted `<HEXAGARE_SERIAL_PREFIX><variant token>-<sequence>`
  (e.g. `HX11X23-000001`); `sequence` (per-variant counter, `editable=False`,
  `UniqueConstraint(variant, sequence)`); `status` (nine-value lifecycle,
  `db_index`); **`location`** FK → `inventory.Location` (`PROTECT`) — independent
  of `status`; optional `purchase_cost`; `created_by`. `ALLOWED_TRANSITIONS` is
  the state machine; `can_transition_to` / `allowed_transitions` / `is_terminal`
  are helpers. Barcodes are **not** stored (see below).
- **`SerializedUnitEvent`** — append-only per-unit history (`unit` `CASCADE`,
  `from_status`, `to_status`, `location`, `note`, `actor`, `created_at`). Written
  on creation and every transition. Distinct from the Phase 4
  `InventoryTransaction` ledger (ADR-008).

### Service (`apps/products/services/serial_numbers.py`)

- `allocate_serial(variant) → (serial, sequence)` — per-variant
  `pg_advisory_xact_lock`, `MAX(sequence)+1`. Must run in a transaction.
- `create_unit(*, variant, location, status=GENERATED, purchase_cost, actor)` —
  atomic: allocate + insert + opening event. `status` must be `GENERATED` or
  `AVAILABLE`. (Bulk generation + label PDFs are Phase 5.)
- `transition_unit(unit, *, to_status, location=None, actor, note)` — row-locked
  status move validated against `ALLOWED_TRANSITIONS`, writes an event. **No
  stock ledger** — Phase 4's `SerializedInventoryService` wraps this + the ledger
  and becomes the only path for transfer/sell/damage/lose/return.
- `resolve_unit(code)` — serial **or** scanned-barcode string → the unit
  (case-insensitive), or `Http404`.

### Barcodes (`apps/products/services/barcodes.py`)

`render_code128_png(data)` — Code128 PNG via python-barcode + Pillow, generated
**on demand**, streamed through `BinaryRenderer`, never stored.

### API (`/api/v1/products/serialized-units/`)

`SerializedUnitViewSet` (no `PUT`/`PATCH`/`DELETE`): `list` + `retrieve`
(`serials.view`), `create` one unit (`serials.manage`),
`POST {id}/transition/` `{status, location?, note?}` (`serials.manage`),
`GET {id}/barcode/` → PNG (`serials.view`),
`GET lookup/?code=` → full chain + pricing + history (`barcode.scan`, §55 rule 4).
List filters: `?status=` `?location=` `?variant=` `?product=` `?search=` (serial).

## Inventory

`Location` built in Phase 3 (ADR-007); the ledger is Phase 4.

### Models (`apps/inventory/models.py`)

- **`Location`** — generic stock-holding place. `name` (unique), `code` (unique
  slug), `kind` (`warehouse` / `marketplace` / `retail` / `other` — **reporting
  only, never branched on**), `is_active`, timestamps. Seed rows
  **Warehouse / Amazon / Offline** created idempotently via a `post_migrate` hook
  (`apps/inventory/bootstrap.py`).

### API (`/api/v1/inventory/`)

`LocationViewSet` — **read-only** for now (`ReadOnlyModelViewSet`, permission
`inventory.view`); filters `?kind=` / `?is_active=` / `?search=`. Write actions
arrive with the Phase 4 ledger.

_Phase 4 adds:_ `InventoryBalance` (read cache), `InventoryTransaction`
(immutable ledger); `InventoryService` the only writer.

## Sales and billing
_Not yet built (Phases 7-8)._ `SalesChannel`, generic `Sale` / `SaleLine`
(derived totals via `SalesTotalsService`), `Payment`, `Invoice`,
`InvoiceDelivery`.

## Integrations (Amazon)
_Not yet built (Phase 9)._ `AmazonOrderSettlement` holds channel-specific
financials, keyed `(sale, sku)`. See `amazon-order-import.md`.

## Customers / Purchases / Suppliers / Expenses / Reports / Notifications
_Not yet built (later phases)._ Scaffold apps only.
