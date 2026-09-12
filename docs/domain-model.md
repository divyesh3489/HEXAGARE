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

`Location` built in Phase 3 (ADR-007); the stock ledger in Phase 4 (ADR-009).
Full detail — bucket model, services, the `transition`-endpoint gap, transfer
lifecycle, alert rules — in `inventory-ledger.md`.

### Models (`apps/inventory/models.py`)

- **`Location`** — generic stock-holding place. `name` (unique), `code` (unique
  slug), `kind` (`warehouse` / `marketplace` / `retail` / `other` — **reporting
  only, never branched on**), `is_active`, timestamps. Seed rows
  **Warehouse / Amazon / Offline** created idempotently via a `post_migrate` hook
  (`apps/inventory/bootstrap.py`).
- **`InventoryTransaction`** — the append-only stock ledger. One row = one signed
  change to a `(variant, location, status)` bucket: `reference` (UUID grouping
  the −1/+1 pair of a move), `kind`, `variant` (`PROTECT`), `location`
  (`PROTECT`), `status` (a `SerializedUnit.Status` value), `quantity` (∈ ℤ,
  never 0), optional `serialized_unit` (`PROTECT`), `note`, `actor`,
  `created_at`. `save()` refuses post-creation edits; `delete()` always raises.
- **`InventoryBalance`** — rebuildable read cache: `quantity`
  (`PositiveIntegerField`) per `(variant, location, status)`
  (`UniqueConstraint`). Written only by `InventoryService`; reconstructable via
  `rebuild_balances()`.
- **`StockLevelPolicy`** — `variant` (`CASCADE`), optional `location` (`CASCADE`;
  blank = the variant's total across all locations), `min_quantity`,
  `max_quantity` (nullable), `is_active`. Partial unique constraints keep one
  global policy and one policy per location per variant. Drives the alerts.
- **`StockTransfer`** — `from_location` / `to_location` (`PROTECT`), `status`
  (`OPEN` / `COMPLETED` / `CANCELLED`), `reference` (UUID), `note`,
  `created_by`, timestamps, `completed_at`. **`StockTransferLine`** — `transfer`
  (`CASCADE`) × `serialized_unit` (`PROTECT`), `received`, unique per pair.

### Services

- **`InventoryService`** (`apps/inventory/services/ledger.py`) — the **only**
  writer of `InventoryTransaction` / `InventoryBalance`: `record`, `move_unit`
  (the −1/+1 pair), `opening`, `adjust`, `rebuild_balances`. Every method is
  atomic and locks the balance row; a move that would go negative is refused.
- **`SerializedInventoryService`** (`apps/products/services/serialized_inventory.py`)
  — the **only** path that changes a serialized unit's status as a business
  action: `generate`, `reserve`, `release`, `start_transfer`,
  `complete_transfer`, `cancel_transfer`, `sell`, `return_unit`, `damage`,
  `lose`, `restore`, `cancel`. Each wraps Phase 3's `transition_unit` **and** the
  ledger in one atomic block. `create_unit` now also emits an `OPENING` ledger
  row.
- **Alerts** (`apps/inventory/services/alerts.py`) — `compute_alerts()` derives
  `out_of_stock` / `low_stock` / `overstock` from `InventoryBalance` vs
  `StockLevelPolicy`, plus `balance_mismatch` when the cache disagrees with the
  live unit counts. Nothing stored.

### The `transition`-endpoint gap (intentional, ADR-009)

`POST /products/serialized-units/{id}/transition/` (Phase 3) still applies a
status-only move and writes **no** ledger row — it is for corrections. A move
with stock meaning made through it leaves `InventoryBalance` stale until
`manage.py rebuild_inventory_balances` runs; `/inventory/overview/` (live) shows
`cache_matches: false` and a `balance_mismatch` alert fires meanwhile.

### API (`/api/v1/inventory/`)

- `LocationViewSet` — full CRUD. Reads `inventory.view`; writes
  `stock_adjustments`. Delete blocked while the location holds units or balances.
  Filters `?kind=` / `?is_active=` / `?search=`.
- `balances/` (GET, `inventory.view`) — the cache. `?variant=` `?location=`
  `?status=` `?product=`.
- `transactions/` (GET, `inventory.view`) — the ledger. `?variant=` `?location=`
  `?status=` `?kind=` `?reference=` `?serialized_unit=` `?search=`.
- `policies/` — CRUD. Reads `inventory.view`; writes `stock_adjustments`.
- `transfers/` + `{id}/scan/` `{id}/receive/` `{id}/cancel/` (`inventory.transfer`)
  — the scan-based transfer flow.
- `overview/` (GET, `inventory.view`) — stock by variant × location × status,
  counted **live** from the units, with `totals_by_status` and `cache_matches`.
- `alerts/` (GET, `inventory.view`) — computed alerts; `?variant=` `?location=`
  `?reconcile=false`.
- `adjustments/` (POST, `stock_adjustments`) — one manual non-serialized quantity
  correction.

RBAC: `inventory.view` (reads), `inventory.transfer` (transfers),
`stock_adjustments` (location / policy / adjustment writes). No new codename this
phase.

## Sales and billing

**`SalesChannel` / `Sale` / `SaleLine` built (Phase 7, ADR-012). Reservation
(`SaleLineUnit`), `Payment`/`Invoice`/`InvoiceDelivery`, and the "Complete
Sale" flow built (Phase 8, ADR-013).**

- **`SalesChannel`** (`apps/sales`) — `code`/`name`/`is_active`, seeded via a
  `post_migrate` hook (`apps/sales/bootstrap.py`, rows `AMAZON`/`OFFLINE`), the
  same shape as `inventory.Location`. A new channel is a new row, never a code
  change.
- **`Sale`** — one generic order for every channel (the "Order" of
  HEXAGARE_FEATURES.md §27). `status` is a single superset `TextChoices`
  spanning both channels' vocabularies (`DRAFT` through `REFUNDED`) — a
  channel-specific status is a *value*, not a schema difference.
  `external_reference` (blank by default, unique with `sales_channel` once
  set) is pulled forward from Phase 9's Amazon-import idempotency key, same
  precedent as `Location` landing ahead of the Phase 4 ledger.
  `subtotal`/`discount_total`/`tax_total`/`grand_total` are a rebuildable
  cache — written only by `apps/sales/services/totals.py:SalesTotalsService`,
  which locks the `Sale` row and resums its lines, the same lock-then-write
  shape as `InventoryService` (ADR-009).
- **`SaleLine`** — `variant`, `quantity`, and a pricing **snapshot**
  (`unit_price`/`tax_rate` copied from the variant's `effective_*` at add-time,
  never re-read live). GST-inclusive, same convention as
  `ProductVariant.base_price`/`gst_amount`: taxable value and tax are derived
  backward from `unit_price` via `taxable_value`/`tax_amount` properties, plus
  `cgst_amount`/`sgst_amount` (an even split — intra-state only, ADR-013).
- **`SaleLineUnit`** (Phase 8, ADR-013) — one row per physical
  `SerializedUnit` bound to a `SaleLine`: `sale_line` FK (`CASCADE`) ×
  `serialized_unit` **`OneToOneField`** (`PROTECT`), so a unit is bound to at
  most one line anywhere. `SaleLine.quantity` is kept in sync with
  `units.count()` by the service layer — a manual `quantity` edit is rejected
  once a line has bound units. Rows created once a sale completes are a
  **permanent record** (never deleted); rows for a still-`DRAFT` line are
  deleted when a unit/line is removed or the sale is cancelled.

### Reservation (`apps/sales/services/units.py:SaleUnitService`)

The **only** path that adds/removes a unit from a sale's cart. `add(sale, *,
code=None, variant=None, actor)`: `code` (a scanned/typed serial or barcode —
the exact-unit flow, HEXAGARE_FEATURES.md §24) resolves via
`apps.products.services.serial_numbers.resolve_unit`; `variant` (a
product-search add) picks the oldest `AVAILABLE` unit for that variant
(FIFO by `sequence`). Either way: find-or-create the sale's line for that
variant, `SerializedInventoryService.reserve()` the unit (`AVAILABLE ->
RESERVED`, ledger updated), create the `SaleLineUnit` row, sync `quantity`,
`SalesTotalsService.recalculate`. `remove(sale, unit_id, actor)` is the
inverse (`release()`, delete the join row, deletes the line once empty).
`release_all(sale, actor)` — used by `SaleViewSet.cancel` — releases every
bound unit on a sale being discarded.

A concurrency race (two cashiers grabbing the same "oldest available" unit) is
resolved safely by `reserve()`'s own row lock: the loser gets a clean
`validation_error` to retry, never a double-reservation.

### API (`/api/v1/sales/`)

- `channels/` (GET, `sales.view`) — read-only list of sales channels.
- `` (list/retrieve, `sales.view`; create, `orders.manage`) — `?channel=<code>`
  `?status=<STATUS>` filters. Create accepts an optional nested `lines` list.
- `{id}/lines/` (POST, `orders.manage`) — add a line to a `DRAFT` sale
  (quantity, no unit binding — a draft/quote line, not yet sellable).
- `{id}/lines/{line_id}/` (PATCH/DELETE, `orders.manage`) — edit
  quantity/discount (rejected once the line has bound units) or remove a line
  (releases its bound units first); same recalculation.
- `{id}/units/` (POST, `orders.manage`, Phase 8) — scan/search-add one exact
  unit: `{"code": "..."}` or `{"variant": <id>}`.
- `{id}/units/{unit_id}/` (DELETE, `orders.manage`, Phase 8) — release/unbind
  one exact unit.
- `{id}/cancel/` (POST, `orders.manage`) — sets `status=CANCELLED` and
  releases every bound unit.

RBAC: `sales.view` (reads), `orders.manage` (create/edit/cancel, including the
new `units/` actions). Both codenames were already reserved in `rbac.py` — no
change this phase.

## Billing (`apps/billing`, Phase 8, ADR-013 + ADR-013 addendum)

- **`Payment`** — `sale` FK (`PROTECT`), `method` (`CASH`/`UPI`/`CARD`/
  `BANK_TRANSFER`/`CREDIT`), `type` (`PAYMENT`/`REFUND` — `REFUND` reused by
  Phase 10 Returns rather than a new model), `amount` (always positive),
  `reference`, `note`. Multiple rows per sale support split-tender payment.
- **`Invoice`** — `sale` `OneToOneField`, `invoice_number` (unique,
  `<HEXAGARE_INVOICE_PREFIX>-<padded sequence>`, e.g. `HEX-INV-001245`,
  allocated by `apps/billing/services/numbering.py:allocate_invoice_number`
  under a Postgres advisory lock — same shape as serial allocation (ADR-008),
  a distinct lock namespace `1002`), a **snapshot** of
  `subtotal`/`discount_total`/`tax_total`/`grand_total` at completion time
  (an invoice is a point-in-time document, same convention as `SaleLine`'s
  pricing snapshot), and `status`/`pdf_file`/`pdf_generated_at`/
  `error_message` mirroring `apps.products.models.LabelBatch`'s `PENDING ->
  READY`/`FAILED` shape. `amount_paid`/`balance_due` delegate to
  `Sale.amount_paid`/`Sale.balance_due` (see below) rather than duplicating
  the computation.
- **`InvoiceDelivery`** — `invoice` FK, `channel` (`EMAIL`/`WHATSAPP`),
  `recipient` (the email/phone actually targeted — an explicit override or
  resolved from the sale's customer, added Phase 15), `status`
  (`PENDING`/`SENT`/`FAILED`), `sent_at`, `error_message`. Rows are created by
  `InvoiceViewSet.send` (`POST /billing/invoices/{id}/send/`, `apps.billing`)
  and updated by `apps.notifications.tasks.send_invoice_delivery` (Phase 15)
  once the actual email/WhatsApp send resolves.
- **`Sale.amount_paid`/`Sale.balance_due`** (`apps.sales.models`, not
  `apps.billing`) — computed properties walking the reverse `sale.payments`
  accessor (a refund-type row subtracts). Deliberately live on `Sale`, not
  `Invoice`: a sale can carry payment before an invoice exists at all, while
  it's `RESERVED` ("on hold" — see below).

### Complete Sale / hold / resume (`apps/billing/services/checkout.py:CompleteSaleService`)

The "Complete Sale" flow (HEXAGARE_FEATURES.md §26, rule 7) **only** sells
units and generates an invoice once payment actually covers the total — a
partial/short payment leaves the sale **on hold**, not completed. This was a
post-launch correction to the original Phase 8 pass (which wrongly treated
any recorded payment as enough to complete); see the ADR-013 addendum.

`CompleteSaleService.complete(sale, *, payments, actor)` — accepts a
`DRAFT` or `RESERVED` sale. One atomic call: locks the `Sale` row, requires
**every line fully unit-backed** (`quantity == units.count()` — a line built
through the generic `POST lines/` endpoint can't be sold until it's
scanned/bound), `SalesTotalsService.recalculate`, records the given
`Payment` row(s), then branches on `sale.amount_paid` (including what was
just recorded) vs `sale.grand_total`:

- **Short** → `Sale.status = RESERVED` ("on hold"); units stay `RESERVED`,
  no `Invoice` is created. The sale can be resumed later — `complete` is
  called again (more `payments`) until it clears.
- **Covered** → `SerializedInventoryService.sell()` for every bound unit
  (`RESERVED`/`IN_TRANSIT -> SOLD`, ledger updated), allocates the invoice
  number, creates the `Invoice` (`PENDING`), sets `Sale.status = COMPLETED`.
  `transaction.on_commit` enqueues `apps.billing.tasks.render_invoice_pdf` —
  commit-first-enqueue-after, per CLAUDE.md's Celery pattern. A PDF render
  failure never unwinds the sale (units are already sold, payment already
  recorded) — it marks the invoice `FAILED`, same recoverable shape as
  `render_label_pdf`.

A `CREDIT`-method `Payment` counts toward `amount_paid` like any other
method — a cashier recording one for the deferred amount completes the sale
(goods considered sold, the credit is the business's own receivable to
collect later), matching HEXAGARE_FEATURES.md §23 listing Credit/Due as an
equal payment method. What must never happen is an *unrecorded* shortfall
being treated as covered.

`CompleteSaleService.record_payment(sale, *, payments, actor)` — the
separate path for a sale that's already `COMPLETED`: adds `Payment` row(s)
only (settling a receivable, e.g. a customer paying back a `CREDIT`
balance). Units and the invoice are untouched.

`apps/billing/services/invoice_pdf.py:build_invoice_pdf` renders the GST
invoice (ReportLab, same rationale as `apps.products.services.labels`,
ADR-010) — header, one row per line with its serial number(s), taxable
value/CGST/SGST/total (HEXAGARE_FEATURES.md §28's own example), payment
summary. **CGST/SGST split only, no IGST** — inter-state detection needs a
customer/business "place of supply", which doesn't exist until
`apps.customers` (Phase 11); documented simplification (ADR-013).

### API (`/api/v1/billing/`)

- `checkout/` (POST, `billing.manage`) — `{"sale": <id>, "payments":
  [{"method", "amount", "reference"?, "note"?}]}` -> `{"sale": ..., "invoice":
  ... | null}`. Dispatches on the sale's current status: `DRAFT`/`RESERVED`
  goes through `complete` (`invoice` is `null` while on hold); `COMPLETED`
  goes through `record_payment` (settling a receivable, `invoice` is the
  existing one with a lower `balance_due`).
- `invoices/` (list/retrieve, `billing.view`) — `?sale=` `?status=` filters.
  Only ever lists sales that actually completed — a held sale has no row
  here yet.
- `invoices/{id}/pdf/` (GET, `billing.view`) — download the rendered PDF
  (only once `status == READY`).
- `payments/` (list/retrieve, `billing.view`) — `?sale=` filter.

RBAC: `billing.view` (reads), `billing.manage` (checkout). Both codenames were
already reserved in `rbac.py` — no change this phase.

## Returns (`apps/billing`, Phase 10, ADR-015)

HEXAGARE_FEATURES.md §31/§59's flow — scan a sold serial, resolve it to its
original sale/line, refund, move the unit to `RETURNED`, then inspect it to
`AVAILABLE` (resellable) or `DAMAGED` — modeled as two new models alongside
`Payment`/`Invoice` in `apps/billing` (ADR-015), not a new domain app.

- **`Return`** — `sale` FK (`PROTECT`), `reason`, `note`, `created_by`,
  `created_at`. `refund_total` is a computed property (sum of its
  `ReturnUnit.refund_amount` rows), not a stored column — `ReturnUnit` rows
  are immutable once created, same reasoning as `SaleLineUnit`.
- **`ReturnUnit`** — `return_record` FK (`CASCADE`, related name `units`;
  named to dodge the `return` keyword), `sale_line_unit` FK (`PROTECT`,
  resolves exactly which sale/line this unit came back from),
  `serialized_unit` FK (**not** `OneToOneField` — contrast `SaleLineUnit` — a
  unit can be sold again after being restored, so it may have more than one
  `ReturnUnit` row across its lifetime), `refund_amount`, `condition`
  (`PENDING` → `RESELLABLE`/`DAMAGED`), `inspected_at`, `inspected_by`.

### `apps/billing/services/returns.py:ReturnService`

- **`resolve(code)`** — read-only preview for one scanned code: the unit,
  its `SaleLineUnit`, the originating `Sale`, and a suggested refund amount
  (`SaleLine.net_amount / quantity`, an even split — `SaleLine` carries no
  per-unit discount breakdown). Raises if the unit isn't `SOLD`.
- **`create(entries, reason, refund_method, note, actor)`** — one atomic
  call. Every `entries[].code` must resolve to a `SOLD` unit on the **same**
  `Sale` (rejects a mix); each unit moves `SOLD -> RETURNED` via
  `SerializedInventoryService.return_unit()` (ledger `RETURN` row, no
  changes needed to that service), a `ReturnUnit` row is created per unit
  (refund amount defaults to the suggestion, overridable per unit), and one
  `Payment` row (`type=REFUND`) is created for the summed total — one
  refund method per `Return`, not split-tender.
- **`inspect(return_unit, condition, actor)`** — resolves a still-`PENDING`
  `ReturnUnit`. `RESELLABLE` calls `SerializedInventoryService.restore()`
  (`RETURNED -> AVAILABLE`); `DAMAGED` calls `.damage()`
  (`RETURNED -> DAMAGED`). Rejects a unit already inspected.

**Channel-agnostic by construction.** Resolution goes through
`SerializedUnit.sale_line_unit`, which every `SOLD` unit has regardless of
whether it was sold through the offline POS checkout (Phase 8) or the
Amazon CSV importer (Phase 9) — no channel branch anywhere in this service.
This is deliberately how Phase 9's gap (a CSV trying to move an
already-finalized order to `RETURNED`/`REFUNDED` is logged as a failed row
rather than reversed — ADR-014 point 3) gets closed: an operator processes
that return here instead, by scanning the serial.

`Sale.status` is **not** written by this flow — a sale can have some units
returned and others still `SOLD`; return state lives at the
`Return`/`ReturnUnit` level (`Return.sale` for the reverse lookup).

### API (`/api/v1/billing/returns/`)

- `resolve/` (GET, `returns`) — `?code=` -> unit/sale/line preview.
- `` (list/retrieve/create, `returns`) — create takes
  `{"entries": [{"code", "refund_amount"?}], "reason", "refund_method",
  "note"?}`.
- `{id}/units/{return_unit_id}/inspect/` (POST, `returns`) —
  `{"condition": "RESELLABLE" | "DAMAGED"}`.

RBAC: the single `returns` codename (reserved since Phase 1, held by
Cashier/Manager/Admin, not Warehouse) gates every action — no `rbac.py`
change.

Frontend: `frontend/src/features/returns/` — `ReturnsPage` (list),
`NewReturnPage` (scan/type-code flow, reusing `features/sales`'s
`CameraScanPanel`), `ReturnDetailPage` (per-unit inspect actions) —
replacing the Phase 0 stub route at `/sales/returns`.

## Integrations (Amazon)

CSV order import (Phase 9, ADR-014) — lives under `apps.integrations` (a
single Django app; the Amazon-specific code is an `amazon` subpackage, e.g.
`apps.integrations.amazon.models`, so a future channel gets its own sibling
subpackage rather than a new app).

- `AmazonSkuMapping` — `amazon_sku` (unique) → `ProductVariant`. Resolves
  every imported row; auto-created on an exact SKU string match, otherwise
  managed via the SKU Mapping page.
- `AmazonFeeConfig` — the configurable fee structure (§22): fee name,
  `PERCENTAGE`/`FIXED`, value, `sales_channel`, optional
  `applicable_category`/`applicable_product` scoping (product wins), an
  effective date range. Consulted only when a CSV row leaves that fee column
  blank — an actual imported figure always wins.
- `AmazonOrderSettlement` — one row per `(sale, sku)`: the Amazon-specific
  per-line financials (`selling_price`, `gst_amount`, `taxable_value`, the
  fee columns, `refund_amount`) kept off the generic `Sale`/`SaleLine`, plus
  computed `settlement_amount`/`net_revenue`/`product_cost`/`net_profit`
  (§21). Idempotent re-import upserts by this key.
- `AmazonImportBatch` — one CSV upload/run: `PENDING` → `PROCESSING` →
  `READY`/`PARTIAL`/`FAILED`, counts (`orders_created`/`updated`/`skipped`/
  `failed`), and `error_log` (one entry per failed row/order) — a CSV import
  is naturally partial-success, unlike `LabelBatch`'s all-or-nothing shape.

`AmazonOrderImportService.run` (`apps/integrations/amazon/services/importer.py`)
groups CSV rows by `order_id` and imports each order in its own
`transaction.atomic()` — one bad order never blocks the rest of the file.
For an order whose status means stock left the business, it sells serialized
units directly via `SerializedInventoryService` (`AVAILABLE → RESERVED →
SOLD`, FIFO at the `amazon` `Location`) and binds them with `SaleLineUnit` —
**deliberately bypassing** `SaleUnitService`/`CompleteSaleService`: an
imported order already happened (not a cart), and Amazon issues its own
invoice, so no `Payment`/`Invoice` is created here. Runs via a Celery task
(`apps/integrations/amazon/tasks.py`), enqueued on commit, never inline.

RBAC: the single `integrations.amazon` codename (reserved since Phase 1)
gates every endpoint here — "Import Amazon orders and manage Amazon
settings" already reads as one combined capability; only Admin/Manager hold
it. See `amazon-order-import.md` for the full CSV format and idempotency
rules.

## Customers (`apps/customers`, Phase 11, ADR-016)

`Customer` — `name` (required), `phone`, `email`, `address`, `gstin`,
`notes` (all optional regardless of `type`), `type`
(`REGISTERED`/`WALK_IN`), `created_at`/`updated_at`. One model for both a
fully registered customer and a lightweight walk-in — "registering" a
walk-in later is just filling in more fields on the same row.

`Sale.customer` is a nullable, `PROTECT` FK to `customers.Customer`. `null`
is the true "no registration required" walk-in (§30) — no `Customer` row at
all; a `Customer` row with `type=WALK_IN` is the separate case of wanting a
name/phone on record without full registration. A customer with any sales
history cannot be deleted (`apps.customers.views.CustomerViewSet.perform_destroy`
blocks it with a friendly `validation_error`, same guard style as
`inventory.Location`).

Attaching/changing/clearing the customer on a sale is its own action,
`POST /sales/{id}/customer/` (`{"customer": <id> | null}`), gated by the
existing `orders.manage` — not tied to `sale.is_editable`, since linking a
customer is metadata, not a cart/total change.

### `apps/customers/services.py` — purchase-history aggregation

Computed on read (not cached columns), walking `apps.sales`/
`apps.billing`/`apps.products` reverse relations at call time — same
one-directional pattern as `Sale.amount_paid` walking `apps.billing`:

- `total_purchases(customer)` — sum of `grand_total` across the customer's
  sales, excluding `DRAFT`/`CANCELLED`.
- `total_refunds(customer)` — sum of `Return.refund_total` across returns
  on those sales.
- `outstanding_amount(customer)` — sum of `balance_due` across those sales
  (only positive balances).
- `serial_number_history(customer)` — every `SerializedUnit` ever sold to
  the customer, via `sale_line_unit__sale_line__sale__customer`.

### API (`/api/v1/customers/`)

Standard CRUD (`customers.view` for list/retrieve, `customers.manage` for
create/update/delete). List/detail search on `name`/`phone`/`email`/`gstin`,
`?type=` filter. `CustomerDetailSerializer` returns the profile, the three
aggregate figures, a light order-history list, and the serial-number
history in one response — matching this project's scale rather than a
separate paginated endpoint per section.

RBAC: `customers.view`/`customers.manage` (reserved since Phase 1, held by
Cashier/Manager/Admin, not Warehouse) — no `rbac.py` change.

Frontend: `frontend/src/features/customers/` — `CustomersPage` (list +
inline create), `CustomerDetailPage` (profile edit, aggregates, order
history, serial history), `CustomerPicker` (search-or-walk-in-quick-add,
reused inside New Bill) — replacing the Phase 0 stub route at `/customers`.

## Suppliers (`apps/suppliers`, Phase 12, ADR-017)

`Supplier` — `name` (required), `company`, `phone`, `email`, `address`,
`gstin`, `payment_terms`, `notes`, `created_at`/`updated_at`. A supplier with
any purchase-order history cannot be deleted (`SupplierViewSet.perform_destroy`
blocks it with a friendly `validation_error`, same guard style as
`inventory.Location`/`customers.Customer`).

### `apps/suppliers/services.py` — purchase-history aggregation

Computed on read (not cached columns), walking `apps.purchases` reverse
relations at call time — same one-directional pattern as
`apps.customers.services`:

- `total_purchase_value(supplier)` — sum of `grand_total` across the
  supplier's purchase orders, excluding `DRAFT`/`CANCELLED`.
- `total_paid(supplier)` — sum of `amount_paid` across those orders.
- `outstanding_amount(supplier)` — sum of `balance_due` across those orders
  (only positive balances).

### API (`/api/v1/suppliers/`)

Standard CRUD. List/retrieve gated `purchases.view` (suppliers are viewed
alongside purchase orders, matching the nav grouping); create/update/delete
gated `suppliers.manage`. Search on `name`/`company`/`phone`/`email`/`gstin`.
`SupplierDetailSerializer` returns the profile, the three aggregate figures,
and every purchase order (regardless of status — the aggregates above are
what excludes `DRAFT`/`CANCELLED`) in one response.

Frontend: `frontend/src/features/suppliers/` — `SuppliersPage` (list +
inline create), `SupplierDetailPage` (profile edit, aggregates, order
history) — replacing the Phase 0 stub route at `/purchases/suppliers`.

## Purchases (`apps/purchases`, Phase 12, ADR-017)

`PurchaseOrder` — `supplier` FK (`PROTECT`), `status`
(`DRAFT -> ORDERED -> PARTIALLY_RECEIVED -> RECEIVED`, `CANCELLED` reachable
from any of the first three), `reference`, `invoice_number`, `note`,
`created_by`. `subtotal`/`discount_total`/`tax_total`/`grand_total` are a
rebuildable cache written only by `PurchaseTotalsService.recalculate` (a
row-locked recompute, the same shape as `SalesTotalsService`).
`amount_paid`/`balance_due` are computed properties summing the order's
`PurchaseOrderPayment` rows. `is_editable` (`DRAFT` only, mirrors
`Sale.is_editable`) gates line mutation; `is_receivable`
(`ORDERED`/`PARTIALLY_RECEIVED`) gates the receive action.

`PurchaseOrderLine` — `variant` FK (`PROTECT`), `quantity_ordered`,
`quantity_received`, `unit_price`, `tax_rate`, `discount_amount`. Unlike
`SaleLine`, `unit_price`/`tax_rate` are always client-supplied at line-entry
time (a purchase price is what the supplier quoted, not snapshotted from the
catalog) — the frontend pre-fills them from the variant's
`effective_purchase_price`/`effective_tax_rate` as a starting suggestion,
editable before submit. `net_amount`/`taxable_value`/`tax_amount` follow the
same tax-inclusive-`unit_price` convention as `SaleLine`.

`PurchaseOrderLineUnit` — `line` FK (`PROTECT`), `serialized_unit`
(`OneToOneField`, `PROTECT`). Links one received physical unit back to the
purchase-order line it came from, for cost-basis traceability — mirrors
`apps.sales.models.SaleLineUnit`. A unit is only ever received once, so this
is a permanent, never-deleted record.

`PurchaseOrderPayment` — `purchase_order` FK (`PROTECT`), `method`
(Cash/UPI/Card/Bank transfer/Credit), `type` (Payment/Refund), `amount`,
`reference`, `note`, `created_by`. A standalone model, **not** a reuse of
`apps.billing.Payment` (that model's `sale` FK is a hard-required `PROTECT`
field tied to `Sale` — see ADR-017).

### `apps/purchases/services.py`

- `PurchaseTotalsService.recalculate(purchase_order)` — row-locked
  recompute of the four derived totals from the order's current lines.
- `ReceiveStockService.receive(purchase_order, *, receipts, actor)` — the
  only path that creates units for a purchase order. One atomic call per
  receiving session; `receipts` is a list of `{line, quantity, location}`.
  Validates every entry's `quantity` against `line.quantity_pending` up
  front (the whole call fails before any unit is generated if one entry is
  bad), then for each unit calls
  `SerializedInventoryService.generate(variant=line.variant,
  location=..., status=AVAILABLE, purchase_cost=line.unit_price, actor=...)`
  — the same allocator every other unit-creation path uses (Phase 3 single
  units, Phase 5 bulk-generate) — landing units directly in `AVAILABLE`
  per HEXAGARE_FEATURES.md §33's flow ("Assign Location -> Mark Units
  Available"), creates the `PurchaseOrderLineUnit` link, and bumps
  `quantity_received`. Updates `PurchaseOrder.status` to `RECEIVED` once
  every line is fully received, else `PARTIALLY_RECEIVED`.

### API (`/api/v1/purchases/`)

- `orders/` — list/retrieve (`purchases.view`); create (`purchases.manage`,
  optionally with a `lines` convenience list, same shape as
  `SaleCreateSerializer`).
- `orders/{id}/lines/` POST, `orders/{id}/lines/{line_id}/` PATCH/DELETE —
  only while `DRAFT` (`purchases.manage`).
- `orders/{id}/place/` POST — `DRAFT -> ORDERED` (`purchases.manage`).
- `orders/{id}/receive/` POST — `{"receipts": [{"line", "quantity",
  "location"}, ...]}` (`purchases_receiving`).
- `orders/{id}/payments/` POST — record a payment/refund (`purchases.manage`).
- `orders/{id}/cancel/` POST — from `DRAFT`/`ORDERED`/`PARTIALLY_RECEIVED`
  only; does not reverse units already received (`purchases.manage`).

RBAC: `purchases.view`/`purchases_receiving` reserved since Phase 1;
`purchases.manage` added this phase (ADR-017) — Admin/Manager hold it
automatically via the existing `_ALL - {...}` role formula, Warehouse keeps
only `purchases.view`/`purchases_receiving`, Cashier holds none of them.

Frontend: `frontend/src/features/purchases/` — `PurchaseOrdersPage` (list),
`NewPurchaseOrderPage` (supplier + build-a-line-list-then-submit form),
`PurchaseOrderDetailPage` (lines, payments, place/receive-link/cancel
actions), `ReceiveStockPage` (pick a receivable order, then a per-line
quantity + shared location form — unlike Phase 5's bulk-generate wizard,
which is sourced from a single manually-chosen variant and quantity, this
is sourced from the order's own pending lines) — replacing the Phase 0 stub
routes at `/purchases/orders` and `/purchases/receive`.

## Expenses / Finance (`apps/expenses`, Phase 13, ADR-018)

`Expense` — `category` (fixed `TextChoices`: Amazon fees, Shipping, Courier, Packaging,
Advertising, Manufacturing, Raw materials, Offline expenses, Other expenses — a closed taxonomy
per HEXAGARE_FEATURES.md §35, not a separate model), `sales_channel` (optional FK, blank = general/
business-wide), `amount`, `expense_date`, `note`, `created_by`.

`FinanceService` (`apps/expenses/services.py`) is a read-only aggregation, same Python-loop style
as `apps.customers.services`/`apps.suppliers.services` — no cached columns:

- `summary(date_from, date_to, channel=None)` — walks qualifying `Sale`s (excludes `DRAFT`/
  `CANCELLED`) in the range, reusing `Sale.subtotal`/`tax_total`/`discount_total`/`grand_total`
  for taxable/gross sales, GST and discounts; sums each sold unit's `SerializedUnit.purchase_cost`
  (falling back to `variant.effective_purchase_price` for units that predate Phase 12 receiving)
  for product cost; folds `AmazonOrderSettlement` fee columns and matching `Expense` categories
  into `packaging`/`shipping`/`advertising`/`amazon_fees`/`other_expenses` buckets (both an
  automatic settlement figure and a manually logged expense can be the source of a given cost);
  reports `Return.refund_total` separately. `gross_profit = taxable_sales − product_cost`;
  `net_profit = gross_profit − packaging − shipping − amazon_fees − advertising −
  other_expenses` — GST/discounts/refunds are informational, not subtracted again (§36).
- `by_channel(date_from, date_to)` — the same summary per active `SalesChannel`.
- `unit_profit(unit)` — §37 per-serial profit: apportions the sale line's `taxable_value` and (for
  an Amazon order) its `AmazonOrderSettlement` fee columns evenly across the line's bound units —
  same even-split reasoning `ReturnService` uses for refund amounts.

API under `/api/v1/expenses/`: `expenses/` CRUD (`expenses.manage` for every action — no separate
`.view` codename was reserved); `finance/summary/`, `finance/by-channel/` and
`finance/units/{unit_id}/profit/` (all `finance.view`, both reserved since Phase 1, held by
Admin/Manager only). Frontend: `frontend/src/features/expenses/` (`ExpensesPage` — list + inline
create/edit, filterable by category/channel/date) and `frontend/src/features/finance/`
(`ProfitSummaryPage` — date-range picker, summary tiles, by-channel table); a "Profit (this
sale)" card was added to `SerializedUnitDetailPage`, shown only for a `SOLD`/`RETURNED` unit and
gated on `finance.view` — replacing the Phase 0 stub routes at `/finance/expenses` and
`/finance/profit`.

## Reports / Exports (`apps/reports`, Phase 14)

`ReportsService` (`apps/reports/services.py`) is a read-only aggregation, same Python-loop style as
`FinanceService`/`apps.customers.services` — no cached columns, one method per report type
(`sales`, `inventory`, `inventory_movement`, `serial_numbers`, `serial_number_history`, `products`,
`financial`), every one returning `(summary: dict, rows: list[dict])`. `rows` is the flat shape used
both for the on-screen table and for CSV/Excel export — nothing is computed twice. Reuses rather
than re-derives: `FinanceService.summary()`/`by_channel()` for the Sales report's profit line and
the whole Financial report, `apps.inventory.services.alerts.compute_alerts()` for the Inventory
report's low/out-of-stock/overstock counts. Two filter vocabularies: `channel` (`SalesChannel`)
scopes Sales/Products/Financial; `location` (`Location`) scopes Inventory/Serial Numbers, since
stock buckets are location-scoped, not channel-scoped.

`ReportExport` tracks a CSV/Excel export job (`report_type`, `export_format`, `filters` JSONField,
`status` PENDING→READY/FAILED, `file`, `error_message`, `requested_by`) — every export, not just
large ones, goes through Celery (`apps.reports.tasks.generate_report_export`), enqueued via
`transaction.on_commit`. `apps.reports.services.run_report(report_type, filters)` is the single
dispatch point both the GET report views and the export task call.

API under `/api/v1/reports/`: `sales/`, `inventory/` (`?view=movement` for the ledger view),
`serial-numbers/`, `serial-number-history/`, `products/`, `financial/` (all `reports.view`), plus
`exports/` (create/list/retrieve + `{id}/download/`, `reports.export`) — both reserved since Phase
1, Admin/Manager only.

Frontend: `frontend/src/features/reports/` — `ReportsPage` with a button-group tab per report type,
date-range/channel/location/category filters, a generic rows table (columns derived from row keys),
and an Export dropdown (CSV/Excel) that polls the export job and triggers a download once READY.

## Dashboard widgets (`apps/reports/dashboard.py`, Phase 16, ADR-019)

`DashboardService` — four independently-callable, param-mostly-free methods behind the Dashboard
page's four widget groups (HEXAGARE_FEATURES.md §3), living in `apps/reports` (the one cross-domain
aggregation app) rather than a new `apps/dashboard` app — see ADR-019 for the full placement/RBAC
reasoning:

- `sales()` — a fixed snapshot, no query params: running totals (`total_sales`, `total_orders`,
  `products_sold`, `units_sold`, per-channel breakdown) plus fixed calendar windows (today/week/
  month/year).
- `inventory()` — `SerializedUnit` status counts (available/reserved/in_transit/sold/returned/
  damaged/lost) plus low/out-of-stock/overstock **counts** from `compute_alerts()`.
- `finance(date_from, date_to)` — delegates straight to `FinanceService.summary()`; optional query
  params, default the current calendar month.
- `analytics()` — a 30-day `sales_graph` (daily totals, split by channel — feeds both the sales
  trend chart and the Amazon-vs-Offline comparison chart from one payload), top-selling
  products/SKUs (`ReportsService.sales(group_by=...)`, top 5 by units sold), a low-stock **list**
  (complements `inventory()`'s count), and recent orders/returns/stock movements (last 10 each).
  §3's "Recent barcode scans"/"Recent notifications" are out of scope — neither has a backing data
  model yet (see ADR-019).

API under `/api/v1/reports/dashboard/`: `sales/` (`sales.view`), `inventory/` (`inventory.view`),
`finance/` (`finance.view`), `analytics/` (`reports.view`) — each widget group gated by the same
view permission that domain already uses elsewhere, not a new `dashboard` codename, so a role's
dashboard shows exactly the groups its existing permissions cover.

Frontend: `frontend/src/features/dashboard/` — one hook + one section component per group, each
with its own independent loading/error state (a role without `finance.view`/`reports.view` sees a
clean "Couldn't load ..." message on just that card) — replacing the Phase 0 stub at `/`. First use
of `recharts` (`sales-trend-chart.tsx`, `channel-comparison-chart.tsx`), kept in the main bundle
since the Dashboard is the landing page every user hits.

## Notifications (`apps/notifications`, Phase 15)

No models of its own. Two isolated sender classes in `services.py` — `EmailNotificationService`
(Django's `EmailMessage`/`EMAIL_BACKEND`) and `WhatsAppCloudAPI` + `WhatsAppNotificationService`
(the Meta Cloud API's `/messages` endpoint via `requests`) — and two Celery tasks:
`send_invoice_delivery(delivery_id)` (dispatches by channel, updates the Phase 8 `InvoiceDelivery`
row `SENT`/`FAILED`) and `send_low_stock_alerts()` (the project's first `CELERY_BEAT_SCHEDULE`
entry, reuses `apps.inventory.services.alerts.compute_alerts()` unchanged, digests to whichever of
`LOW_STOCK_ALERT_EMAILS`/`LOW_STOCK_ALERT_WHATSAPP_TO` are configured). `InvoiceViewSet.send`
(`POST /billing/invoices/{id}/send/`, `billing.manage`) creates the `InvoiceDelivery` row and
enqueues the task via `transaction.on_commit`.

Frontend: `InvoiceDetailPage` gained a "Send invoice" card (channel select + recipient + Send) and
renders `invoice.deliveries` with a status badge per row.

## Administration (`apps/accounts`, Phase 17, ADR-020)

Settings/users/roles/audit-log/backups all live in `apps.accounts`, not a new app — see ADR-020
for why. No new RBAC codenames (`settings.manage`/`users.manage`/`audit.view` were reserved since
Phase 1).

### Models (`apps/accounts/models.py`)

- **`BusinessSettings`** — `pk=1` singleton (`get_solo()`, bootstrapped via `post_migrate` like
  `Location`/`SalesChannel`). Business info (name/address/phone/email/gstin/logo), tax defaults
  (`currency`, `default_tax_rate`), and blank-by-default *override* fields for
  `sku_prefix`/`serial_prefix`/`serial_padding`/`invoice_prefix`/`invoice_padding` — consulted by
  `apps.products.services.{serial_numbers,sku}` and `apps.billing.services.numbering` before
  falling back to the `HEXAGARE_*` env-backed Django settings unchanged.
- **`AuditLogEntry`** — one generic-FK (`content_type`/`object_id`) model covering every
  HEXAGARE_FEATURES.md §53 action family via a fixed `Action` choices field (`product.created`,
  `serial.created`, `stock.changed`, `status.changed`, `location.*`, `invoice.created`,
  `order.created`/`.cancelled`, `return.created`, `purchase.created`/`.cancelled`,
  `payment.recorded`, `expense.*`, `user.*`, `settings.updated`, `backup.triggered`). Carries
  `actor`, `changes` (`{field: {old, new}}` for updates), `ip_address`, `created_at`.
- **`BackupJob`** — `PENDING → RUNNING → SUCCESS/FAILED`, same shape as `ReportExport`/
  `LabelBatch`. `file`/`file_size`/`error_message`/`triggered_by`/`started_at`/`finished_at`.

### Logging (`apps/accounts/audit.py`)

Two hook shapes, not a call per view (per the build prompt): `AuditMixin` (add to a plain CRUD
`ModelViewSet` — `ProductViewSet`, `ProductVariantViewSet`, `LocationViewSet`, `ExpenseViewSet` —
logs create/update/delete automatically with a generic before/after diff on update) and
`log_activity()` (called directly from the one service method that already owns a non-CRUD
mutation: `SerializedInventoryService._apply` for every unit status transition,
`InventoryService.adjust` for manual stock corrections, `CompleteSaleService.complete`/
`record_payment` for payments + invoice creation, `ReturnService.create`, and the
`SaleViewSet`/`PurchaseOrderViewSet` create/cancel/payments actions). Never raises — a logging
failure never breaks the business action it describes.

### Backups (`apps/accounts/tasks.py:run_database_backup`)

`pg_dump -Fc --no-owner --no-privileges` against `settings.DATABASES["default"]`, run via Celery
(never inline on the trigger request), uploaded to the same storage backend as every other
generated file. Requires `postgresql-client-17` in the backend/celery-worker/celery-beat image,
version-matched to the `postgres:17` compose service (see `backend/hexagare/Dockerfile`). Restore
and scheduled/automatic backups are explicitly out of scope this phase.

### API (`/api/v1/auth/`)

`settings/` (GET any authenticated user, PATCH `settings.manage`) · `users/` (full CRUD except hard
delete — `deactivate/`/`reactivate/` toggle `is_active` instead — `users.manage`) · `roles/`
(read-only role → permission matrix, `users.manage`) · `audit-log/` (read-only, filterable by
`action`/`actor`/`object_type`/`date_from`/`date_to`, `audit.view`) · `backups/` (create + list +
retrieve + `{id}/download/`, `settings.manage`).

Frontend: `frontend/src/features/settings/` — `GeneralSettingsPage`, `UsersPage`, `RolesPage`
(read-only matrix), `AuditLogPage`, `BackupsPage` — replacing the three Phase 0 stub routes at
`/settings`, `/settings/users`, `/settings/roles`, plus two new routes/nav entries
(`/settings/activity`, `/settings/backups`).
