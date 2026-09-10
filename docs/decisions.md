# Architecture Decision Record (ADR) Log

Newest last. Each entry: context, decision, consequences. Add an ADR whenever a
phase makes a structural or architectural decision.

---

## ADR-001 — Modular monolith over microservices

**Status:** Accepted (Phase 0)

**Context.** Hexagare is a product / inventory / billing system for a small
business, built and operated by a very small team. The domains (catalog,
inventory, sales, billing, integrations, …) are tightly coupled: a sale touches
the inventory ledger, serialized units, invoices and payments in one atomic
transaction.

**Decision.** Build a single Django/DRF backend split into domain apps under
`backend/hexagare/apps/` (`accounts`, `products`, `inventory`, `sales`,
`billing`, `integrations`, `customers`, `purchases`, `suppliers`, `expenses`,
`reports`, `notifications`, `common`). One database, one deployable, one codebase.
Cross-app model references use string FKs to avoid circular imports. Slow or
externally-delivered work runs on Celery, not separate services.

**Consequences.** Atomic cross-domain transactions stay simple (no distributed
transactions, no eventual consistency). One migration history, one test suite,
one deploy. If a domain ever needs independent scaling it can be extracted later,
but nothing in the design should assume that. Module boundaries are enforced by
convention (put code in the app it belongs to), not by process isolation.

---

## ADR-002 — SKU and pricing as columns on `ProductVariant`, not standalone entities

**Status:** Accepted (Phase 0, to be implemented in Phase 2)

**Context.** A full catalog model could give SKU, price lists, tax rules and
cost history their own tables with effective-dated rows. Hexagare currently sells
one product family through two channels and needs current price, MRP, purchase
price and tax rate per sellable variant — nothing more.

**Decision.** `SKU` is a unique `CharField` column on `ProductVariant`.
`mrp`, `selling_price`, `purchase_price` and `tax_rate` are likewise plain
columns on `ProductVariant`. No `Sku`, `Price`, or `PriceList` entities.

**Consequences.** Simple reads and writes, one row per sellable variant, easy
SKU-uniqueness enforcement at the DB level. No historical price tracking beyond
what the audit log captures, and no per-customer or per-channel price lists.
Promoting any of these to a standalone entity requires a new ADR and a
migration; do not do it ad hoc.

---

## ADR-003 — Role → permission-name-set RBAC on Django Groups/Permissions

**Status:** Accepted (Phase 1)

**Context.** Hexagare needs action-level permissions (POS, returns, stock
adjustments, receiving, settings, …) across ~13 domain apps, most not built yet.
Users are assigned a job role, not individual permissions. We want role
definitions in one reviewable place, per-action gating in viewsets, and no
custom permission tables to keep in sync with Django's auth system.

**Decision.** `apps/accounts/rbac.py` is the single source of truth:
`OPERATIONAL_PERMISSIONS` maps every action codename to a label (codenames for
unbuilt features are reserved now so roles stay stable); `ROLE_PERMISSIONS` maps
each of the four seed roles (Admin, Manager, Cashier, Warehouse) to a set of
those codenames. `ensure_role_groups()` materializes each codename as a Django
`Permission` and each role as a `Group` with the matching permission set, and
runs from a `post_migrate` hook so it is reapplied on every `migrate`. The
permissions are anchored to a dedicated unmanaged `OperationalPermission` model's
content type, so they resolve as `accounts.<codename>` and never collide with
the model CRUD permissions Django auto-creates (pruning stale operational
permissions is therefore safe). Enforcement is
`apps/accounts/permissions.py:HasOperationalPermission` (+ a `require(...)`
factory); multi-action viewsets gate per action via `get_permissions()`.

**Consequences.** Roles are one dict to review and diff. RBAC state is standard
`auth.Group` / `auth.Permission` rows — `user.has_perm("accounts.pos")`,
`request.user.get_all_permissions()`, and the admin all work unchanged.
`post_migrate` keeps environments converged with zero manual steps. Superusers
bypass all checks (Django default). Trade-offs: no object-level / row-scoped
permissions (add later if needed), no per-user grants outside a role (supported
by Django but not modelled here), and adding a permission means editing
`rbac.py` and migrating. Assigning users to roles/groups is manual until the
Phase 17 settings UI. (The Phase 7 prompt's passing reference to "ADR-003" for
sales-channel extensibility predates this entry; that decision will take the
next free number when Phase 7 lands.)

---

## ADR-004 — Catalog shape: data-driven attributes, advisory SKU suggestion

**Status:** Accepted (Phase 2)

**Context.** The catalog must work for any product category, not just mouse pads.
Variants differ by size / colour / material / "whatever the next category needs",
and SKUs are auto-suggested but must stay hand-editable. Two shape questions:
where do variant properties live, and how strong is the SKU sequence guarantee?

**Decision.**
1. **Variant properties are data, not columns.** `ProductAttribute` defines a
   reusable property (Size, Colour, …); `ProductAttributeValue` is a
   `(variant, attribute) → value` row, unique per pair. No `size` / `colour`
   columns anywhere. Adding a property is a row, not a migration.
2. **Every product has ≥ 1 `ProductVariant`.** Pricing and SKU live only on the
   variant (ADR-002); a "simple" product is just a product with one variant.
   `Product` carries no price fields even though `HEXAGARE_FEATURES.md` §4 lists
   them at product level.
3. **SKU suggestion is advisory.** `apps/products/services/sku.py` builds
   `<prefix>-<category>-<fragment>-<NNN>` and increments past collisions, but
   takes **no advisory lock** (unlike the Phase 3 serial-number service, whose
   sequence must be gapless). The `ProductVariant.sku` unique constraint and the
   serializer's `is_sku_available()` check are the only hard guarantees.
4. **`LabelSize` is catalog reference data**, seeded with two defaults via a
   `post_migrate` hook (`apps/products/bootstrap.py`), matching the
   Locations / SalesChannels seeding pattern. (The Phase 2 prompt only named
   Locations / SalesChannels; this extends the same convention because Phase 5
   needs label geometries to exist.)

**Consequences.** New categories need zero schema work — define attributes, create
products, done. Reads cost a join for attribute values (mitigated by
`prefetch_related`). SKU suggestion can, in theory, race two concurrent
suggestions to the same string; the loser gets a `validation_error` and retries —
acceptable because SKUs are not sequence-critical. Promoting SKU, pricing, or
attribute values to richer entities still requires a new ADR (see ADR-002).
A partial unique constraint on `(product, variant.code)` was prototyped and
dropped: DRF's `UniqueTogetherValidator` forced `code` to be a required field and
could not express the "blank is exempt" condition; variant `code` is now just an
un-constrained SKU-building hint.

**Note.** `apps/products/urls.py` uses DRF's `SimpleRouter`, not `DefaultRouter`
(CLAUDE.md's default phrasing): `ProductViewSet` is registered at the app's root
prefix, so `DefaultRouter`'s API-root view would collide with the product list
route.

---

## ADR-005 — Product-level default pricing, nullable variant overrides, derived discount

**Status:** Accepted (Phase 2, amends ADR-002 / ADR-004)

**Context.** Most products in Hexagare's catalog carry one price across every
variant; typing MRP / selling price / purchase price / GST rate on each variant
is pure friction, and keeping them in sync by hand drifts. Separately, "discount"
had been a stored, hand-entered column that could contradict `mrp - selling_price`.

**Decision.**
1. **`Product` gains optional default pricing** — `mrp`, `selling_price`
   (GST-inclusive), `purchase_price`, `tax_rate`, all `null=True, blank=True`.
2. **`ProductVariant`'s four price columns become nullable overrides.** `NULL`
   means "inherit the product's value"; a value overrides it for that variant.
   `ProductVariant.effective_mrp` / `effective_selling_price` /
   `effective_purchase_price` / `effective_tax_rate` resolve
   *variant value → product default → `0`*. `base_price` / `gst_amount` /
   `cgst_amount` / `sgst_amount` all derive from the **effective** figures.
3. **`discount` is never stored.** Both `Product` and `ProductVariant` expose
   `discount_amount` (`max(mrp − selling_price, 0)`, 2 dp) and `discount_percent`
   (`discount_amount / mrp × 100`, `0` when MRP is missing/zero) as read-only
   properties. The `ProductVariant.discount` column is dropped
   (migration `0002`).
4. **A variant must resolve to a non-null `selling_price` and `mrp`** — the
   serializer rejects a create/update whose effective value for either is `NULL`,
   with a message pointing at "set it on the variant or the product".
5. `selling_price > mrp` is **not** rejected; `discount_amount` simply clamps to
   `0`.

**Consequences.** Price a product once, add variants with no pricing, done; a
per-variant exception is a single field. `discount` can never disagree with the
prices it's computed from. Trade-offs: a variant's effective price now depends on
its product row (loaded via `select_related` / the already-loaded parent in list
serialization — no N+1); changing a product's default price retroactively moves
every inheriting variant (intended); `HEXAGARE_FEATURES.md` §4's product-level
price fields are now honoured literally, and its §5 "Discount (Auto)" is now
actually automatic. **Phase 7's `SalesTotalsService` must read the `effective_*`
figures, not the raw override columns.** This does not reopen ADR-002 — pricing
is still plain columns, not entities; it just lives on both levels now.

---

## ADR-006 — Variant availability is derived from product status

**Status:** Accepted (Phase 2)

**Context.** `ProductVariant.is_active` was shown and treated as absolute, so a
`draft` product's variants read as "Active" — a variant can't sensibly be live
when its product isn't. Product status has four values
(`active` / `inactive` / `draft` / `discontinued`); the per-variant flag should
only matter once the product is actually published.

**Decision.** `is_active` stays as the per-variant *intent*. Two derived,
read-only properties express reality:
- `ProductVariant.effective_status` → a `Product.Status` value:
  product `active` ⇒ `active` if `is_active` else `inactive`;
  product `draft` / `inactive` / `discontinued` ⇒ that status verbatim
  (a discontinued product's variants read `discontinued`, **not** `inactive`).
- `ProductVariant.is_available` → `True` only when the product is `active` **and**
  `is_active` is `True`.

The serializer exposes both; `ProductVariant`'s list endpoint gains an
`?available=1` / `?available=0` filter
(`Q(product__status=active, is_active=True)`); `ProductListSerializer` adds
`available_variant_count` (`0` unless the product is active). The frontend shows
`effective_status`, disables the per-variant Active toggle unless the product is
`active`, and banners draft/inactive/discontinued products. No schema change —
all computed.

**Consequences.** One place decides "is this sellable"; a future POS/storefront
filters `?available=1`. Existing `is_active` values are preserved and
reinterpreted as "intended once live". A discontinued product's variants are not
individually revivable — reactivating the product restores each variant's stored
`is_active`. Nothing enforces hiding draft/inactive variants in the management
UI itself (you must be able to build a product before publishing it).

---

## ADR-007 — `inventory.Location` created in Phase 3 (ahead of the Phase 4 ledger)

**Status:** Accepted (Phase 3)

**Context.** Phase 3's `SerializedUnit` needs a required `location` FK to
`apps.inventory.Location` (§9, §16; and the Target Architecture in `CLAUDE.md`).
The full inventory app — `InventoryBalance`, `InventoryTransaction`,
`InventoryService`, stock transfers — is Phase 4. Building `SerializedUnit`
without a real `Location` to point at (a free-text field, or a stub in
`products`) would contradict "a required `location` FK … no free-text location
field" and force a messy migration later.

**Decision.** Create a **minimal `inventory.Location`** now: `name` (unique),
`code` (unique slug), `kind` (`warehouse` / `marketplace` / `retail` / `other` —
reporting only, never branched on), `is_active`, timestamps. Seed rows
**Warehouse / Amazon / Offline** via a `post_migrate` hook
(`apps/inventory/bootstrap.py`), the same reference-data pattern as
`apps/products/bootstrap.py` (ADR-004). Expose it **read-only** for now
(`LocationViewSet(ReadOnlyModelViewSet)`, permission `inventory.view`) at
`/api/v1/inventory/locations/`.

Phase 4 extends this model and app — it does **not** replace them: it adds
`InventoryBalance` / `InventoryTransaction` / `InventoryService`, the
`post_migrate` seeding stays, and `LocationViewSet` gains write actions in the
ledger's context.

**Consequences.** `SerializedUnit.location` is a real FK from day one. The
`products.0003` migration depends on `inventory.0001`. `inventory.view` (already
reserved in `rbac.py`) starts being enforced in Phase 3. Nothing in Phase 3
writes stock balances — `create_unit` / `transition_unit` only touch the unit and
its event log; wiring unit lifecycle to the ledger is Phase 4's job.

---

## ADR-008 — Per-variant advisory-locked serial sequence; `SerializedUnitEvent` as the unit history log

**Status:** Accepted (Phase 3)

**Context.** Two independent needs:
1. Serial numbers must be **gapless-by-construction and never reused, per
   variant**, even under concurrent bulk generation (Phase 5). SKU suggestion's
   lock-free "retry on collision" approach (ADR-004) is not good enough — a
   serial sequence can't have a losing racer pick "the next one".
2. §55 rule 4 (barcode scan) and §8 ("Serial history", "Serial status") require
   a per-unit history. The Phase 4 `InventoryTransaction` ledger records
   *quantity movements at a location*, not *what happened to unit X*, and does
   not exist yet.

**Decision.**
1. `SerializedUnit.sequence` is a per-variant counter. `allocate_serial(variant)`
   takes `pg_advisory_xact_lock(1001, variant_id)` inside the creating
   transaction, reads `MAX(sequence)` for that variant, returns the next value;
   `create_unit` does allocation + insert + opening event in one
   `transaction.atomic()`. A `UniqueConstraint(variant, sequence)` is the DB
   backstop. Different variants never contend (the lock key includes the variant
   id). No `PUT`/`PATCH`/`DELETE` on units, so rows are not removed and the
   sequence never rewinds.
2. Add `SerializedUnitEvent` — append-only (`unit`, `from_status`, `to_status`,
   `location`, `note`, `actor`, `created_at`), written by `create_unit` and
   `transition_unit`. It is the unit's audit trail and the "History" a scan
   returns. It is **separate from, not a replacement for**, the Phase 4
   `InventoryTransaction`; the two may be cross-linked later but model different
   things.

**Consequences.** Serial allocation is safe for Phase 5 bulk generation with a
single lock per batch. The advisory-lock namespace `1001` is reserved for serial
allocation — pick a different constant for any future advisory lock. History is
available from Phase 3; Phase 4's ledger adds the quantity side without changing
the event log. `transition_unit` is the status-only path and writes an event but
no ledger row — see `serialized-units.md` "Mutation path".

---

## ADR-009 — Stock ledger: append-only `InventoryTransaction`, rebuildable `InventoryBalance` cache, `SerializedInventoryService` as the sole lifecycle writer

**Status:** Accepted (Phase 4)

**Context.** Phase 4 needs "stock by status and location" for serialized
products, low/out/overstock alerts, and a stock-transfer flow — without a stored
counter that can silently drift. `HEXAGARE_FEATURES.md` §17 says serialized
quantities "should be calculated from Product Unit statuses"; CLAUDE.md says
`InventoryBalance` is a read cache never written directly and `InventoryService`
is the only writer, and that the Phase 3 `transition` endpoint stays for
status-only changes but must not touch the ledger.

**Decision.**
1. **`InventoryTransaction` is the append-only ledger.** One row = one signed
   change to a `(variant, location, status)` bucket
   (`quantity` ∈ ℤ, `kind`, optional `serialized_unit`, `reference` UUID,
   `actor`, `note`). `save()` refuses any post-creation edit; `delete()` raises.
   A move between buckets (transfer, reserve, sell, …) is the **−1 / +1 pair**
   sharing one `reference`.
2. **`InventoryBalance` is a disposable cache**, one row per
   `(variant, location, status)` (`PositiveIntegerField`, `UniqueConstraint`).
   `InventoryService.record()` updates it under `select_for_update` in the same
   atomic block as the ledger write and refuses to drive a bucket negative.
   `InventoryService.rebuild_balances()` reconstructs every row from the live
   `SerializedUnit` counts (plus non-serialized `ADJUSTMENT` sums); the
   `rebuild_inventory_balances` management command exposes it.
3. **`InventoryService` (`apps/inventory/services/ledger.py`) is the only writer**
   of both models — `record`, `move_unit`, `opening`, `adjust`,
   `rebuild_balances`.
4. **`SerializedInventoryService` (`apps/products/services/serialized_inventory.py`)
   is the only path that changes a serialized unit's status as a business
   action.** Each verb (`generate`, `reserve`, `release`, `start_transfer`,
   `complete_transfer`, `cancel_transfer`, `sell`, `return_unit`, `damage`,
   `lose`, `restore`, `cancel`) locks the unit row, calls Phase 3's
   `transition_unit` (state machine + `SerializedUnitEvent`), then
   `InventoryService.move_unit` — one `transaction.atomic`, so status and ledger
   never diverge. A rejected transition rolls back both.
5. **`create_unit` now emits an `OPENING` ledger row** in its existing atomic
   block (runtime import of `InventoryService`, so `apps.products` → `apps.inventory`
   at call time only). A unit entering stock is a ledger event from Phase 4 on.
6. **The plain `POST /products/serialized-units/{id}/transition/` endpoint is
   unchanged and still writes no ledger row** — the intentional gap. It is for
   status-only corrections; using it for a move with stock meaning leaves the
   cache stale until `rebuild_inventory_balances` runs. `GET /inventory/overview/`
   is computed **live** from the units and returns `cache_matches`; a
   `balance_mismatch` alert surfaces the same drift.
7. **`StockTransfer` / `StockTransferLine`** model the scan-based transfer and
   its history (§16). Lifecycle `OPEN` → `COMPLETED` / `CANCELLED`; each scan
   dispatches one unit (`AVAILABLE → IN_TRANSIT`), `receive` lands every line at
   `to_location`, `cancel` rolls them back to `from_location`.
8. **`StockLevelPolicy`** (`variant`, optional `location`, `min_quantity`,
   `max_quantity`) drives the alerts, computed on demand in
   `apps/inventory/services/alerts.py` — nothing stored.
9. **RBAC.** `stock_adjustments` (previously reserved) now gates Location writes,
   `StockLevelPolicy` writes and the manual `adjustments/` endpoint;
   `inventory.transfer` gates the transfer flow; `inventory.view` covers all
   reads. No new codename.
10. **`Location` becomes a full `ModelViewSet`** (ADR-007 anticipated this);
    delete is blocked while the location holds units or balances.

**Consequences.** The ledger is the immutable source of truth; the cache is
always rebuildable, so a bug in cache maintenance is recoverable, not corrupting.
Serialized status and stock quantity can only move together through
`SerializedInventoryService`. The `transition` endpoint's gap is real and
documented (`inventory-ledger.md`, `serialized-units.md`) — the price of keeping
a simple status-only correction path. Non-serialized "quantity inventory"
(§17) is only partially covered this phase: the `adjustments/` endpoint + service
support it, but there is no dedicated quantity-stock UI. Phase 8 wires
`SerializedInventoryService.sell()` on payment; Phase 10 uses `return_unit()` /
`damage()`; Phase 5 bulk generation calls `generate()`. Advisory-lock namespace
`1001` is still the only one in use (the ledger uses row locks, not advisory
locks).

---

## ADR-010 — Bulk generation reuses the serial allocator; label PDFs via ReportLab in a Celery task, recorded on a `LabelBatch` history row

**Status:** Accepted (Phase 5)

**Context.** Phase 5 (`HEXAGARE_FEATURES.md` §10–11) is "generate N units of a
variant + a printable label sheet". §10/§11's UI wording includes "set starting
serial number" and "set serial prefix", and the build-prompt library table names
**WeasyPrint** for the PDF. But ADR-008 / `serialized-units.md` make the serial
format allocator-owned (per-variant advisory-locked `MAX(sequence)+1`, immutable,
never caller-chosen), the backend Dockerfile is `python:3.12-slim` with no build
toolchain, and a label sheet is a fixed millimetre grid (`LabelSize` already
models `columns`/`rows`/`margin_mm`/`gutter_mm`/`width_mm`/`height_mm`/
`orientation`), not an HTML page. CLAUDE.md's Celery rule: commit the business
transaction first, enqueue the task after; a PDF failure must not roll back the
units.

**Decision.**
1. **No caller-supplied starting serial or prefix.** `bulk_generate_units`
   (`apps/products/services/bulk_generate.py`) calls
   `SerializedInventoryService.generate()` — i.e. the same `allocate_serial`
   advisory-lock path the single-unit endpoint uses — `quantity` times inside one
   `transaction.atomic`. The wizard shows a **preview** of the next serial via
   `GET /products/label-batches/next-serial/?variant=` (`next_serial_preview`,
   no lock); the real value is assigned under the lock at generation time.
   `HEXAGARE_SERIAL_PREFIX` stays env-config, not a per-batch input.
2. **All-or-nothing.** Batch row + all `quantity` `SerializedUnit` rows +
   their `OPENING` ledger rows commit together or not at all. On any failure the
   whole block rolls back and no render task is enqueued (§11 "Transaction
   Safety": `Created: 0 / Status: Failed`). A `MAX_QUANTITY` cap (5000) bounds
   the transaction.
3. **`LabelBatch` + `LabelBatchItem` are the history table.** `LabelBatch` holds
   the request (variant, location, quantity, `initial_status`, `label_size`,
   `barcode_type`, the optional label-content flags + `custom_text`), the render
   state (`status` PENDING/READY/FAILED, `pdf_file` on `STORAGES["default"]`,
   `pdf_generated_at`, `error_message`), and the units via a `LabelBatchItem`
   M2M-through. Batches and their units are created only through the API and are
   never edited (admin registers them view-only).
4. **The PDF renders in a Celery task, enqueued on commit.**
   `render_label_pdf` (`apps/products/tasks.py`) is dispatched by
   `transaction.on_commit`. Success → `pdf_file` saved, `status=READY`. Any
   exception → `status=FAILED` + `error_message`, task returns (no retry); the
   units are untouched and an operator re-runs via
   `POST /products/label-batches/{id}/regenerate/` (§11 "Reprint labels" /
   "Generation history").
5. **ReportLab, not WeasyPrint.** `apps/products/services/labels.py`
   (`build_label_pdf`) draws the grid straight from the `LabelSize` with
   ReportLab's canvas + its vector Code 128. Pure-Python wheels — the slim image
   needs no Pango/Cairo system packages. `reportlab==4.4.3` added to
   `requirements.txt`; the `celery-worker` / `celery-beat` images (same
   Dockerfile, separate images) must be rebuilt alongside `backend`.
6. **Barcode types: Code 128 only this phase.** §11 also lists EAN-13 / UPC / QR,
   but the serial string is not valid EAN/UPC data and QR needs another
   dependency. `LabelBatch.barcode_type` is stored (default `code128`) so the set
   can grow without a schema change.
7. **RBAC.** Generate / regenerate need `serials.manage`; reading history and the
   `pdf` / `next-serial` endpoints need `serials.view`. No new codename. The
   authenticated PDF download is `GET /products/label-batches/{id}/pdf/`
   (streamed through `BinaryRenderer`, like the Phase 3 barcode); `pdf_url` in
   the serializer is a storage-relative convenience.

**Consequences.** Serial identity stays a single-owner invariant — the wizard
never lets an operator pick or collide a serial. Unit creation and PDF rendering
fail independently, matching the spec. The label renderer is a plain function
over a `LabelBatch`, unit-testable without a browser engine, and the deployment
image is unchanged apart from one pip package. If EAN-13 / UPC / QR or
operator-set start serials are needed later, they are additive (a new
`barcode_type` value; a new allocator mode) — revisit with a follow-up ADR.
Advisory-lock namespace `1001` is unchanged (bulk generation reuses
`allocate_serial`, it does not add a lock).
