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

---

## ADR-011 — Barcode scanner: ZXing (`@zxing/browser`) headless + `vite-plugin-pwa`, API never precached

**Status:** Accepted (Phase 6)

**Context.** Phase 6 (`HEXAGARE_FEATURES.md` §13) is a mobile, camera-based
scanner that resolves a scanned serial to the unit card. It is explicitly
frontend-only — the resolver already exists
(`GET /api/v1/products/serialized-units/lookup/?code=`, `barcode.scan`, Phase 3).
The build prompt offers **html5-qrcode or `@zxing/browser`** for decoding and
names **`vite-plugin-pwa`** for the installable-PWA requirement. Phase 5 labels
are vector **Code 128** (ADR-010).

**Decision.**
1. **`@zxing/browser` (+ `@zxing/library`), headless.** `BrowserMultiFormatReader`
   with `DecodeHintType.POSSIBLE_FORMATS` pinned to Code 128 first, plus the
   common retail 1D symbologies + QR, and `TRY_HARDER`. html5-qrcode was
   rejected because it injects its own DOM/CSS scanner widget that fights the
   shadcn/Tailwind design system; ZXing is a decoder only, so the viewfinder,
   states and result card are ordinary components. `src/features/scanner/`:
   `use-barcode-scanner.ts` (the camera/decoder hook — start/stop from a user
   gesture so the permission prompt is tied to a tap, device switching, a 15 s
   start-timeout so a browser that hangs `getUserMedia` still falls back to an
   error state + manual entry, a run-id guard so a stale late-resolving stream is
   stopped), `hooks.ts` (`useUnitLookup`, reusing `serializedUnitsApi.lookup`),
   `scan-result-card.tsx`, `scanner-page.tsx`.
2. **The scanner route is lazy-loaded.** `React.lazy` in `routes/router.tsx` —
   ZXing (~465 KB / 121 KB gz) is a separate chunk, off the initial bundle. The
   Phase 1 `barcode/scan` stub is removed.
3. **`vite-plugin-pwa`, `registerType: 'autoUpdate'`, `injectRegister: 'auto'`.**
   No `main.tsx` change. Manifest = `standalone` / `portrait` / `start_url: '/'`,
   icons generated by `frontend/scripts/generate-pwa-icons.py` (Pillow, committed)
   into `frontend/public/`. `index.html` gains `theme-color`, `apple-touch-icon`,
   `favicon`, `viewport-fit=cover`, description.
4. **The service worker never caches API or media.** Workbox precaches the built
   app shell only; a `runtimeCaching` rule and `navigateFallbackDenylist` make
   `pathname.startsWith('/api/')` / `'/media/'` **`NetworkOnly`**. Authed,
   per-user data is never served stale or offline. `devOptions.enabled: false`
   (no SW under `npm run dev`); `dev-dist/` git-ignored.
5. **No route-level permission guard.** Consistent with the rest of
   `router.tsx` (auth-gated only). A `403` from `lookup` (role missing
   `barcode.scan`) renders an explanatory card, a `404` renders "no unit matches".

**Consequences.** The decoder is swappable — a different ZXing build or another
library only touches `use-barcode-scanner.ts`. Camera capture needs a secure
context: fine on `localhost` and HTTPS, but a phone hitting a bare LAN IP over
`http://` gets the "camera unavailable" state and must use manual entry (or a
tunnel / `--https`) — documented, not worked around. First frontend chunk-split
in the app; if more routes need it, factor a shared lazy helper. Adding QR-code
labels later needs no scanner change (the format is already in the hint set).

---

## ADR-012 — Sales Core: data-driven `SalesChannel`, one `Sale`/`SaleLine` shape, unified status enum

**Status:** Accepted (Phase 7)

**Context.** Phase 7 (`HEXAGARE_FEATURES.md` §19, §26–27) stands up `apps.sales`
as a real domain app for the first time: a data-driven sales channel and one
generic order model covering every channel, per CLAUDE.md's "no per-channel
schemas" mandate. This resolves the note under ADR-003 above — the Phase 7
prompt's passing reference to "ADR-003" for sales-channel extensibility was a
placeholder; this is that decision, at the next free number.

Section 27 lists two *different* status vocabularies per channel (Offline:
Draft/Reserved/Completed/Cancelled/Returned; Amazon: Pending/Confirmed/Shipped/
In Transit/Delivered/Cancelled/Returned/Refunded), which reads at first glance
like a per-channel schema need.

**Decision.**
1. **`SalesChannel`** mirrors `inventory.Location`'s shape exactly: `code`/
   `name`/`is_active`, seeded via a `post_migrate` hook
   (`apps/sales/bootstrap.py`, rows `AMAZON`/`OFFLINE`). A new channel (Shopify,
   Flipkart, …) is a new row — never a code branch.
2. **One `Sale.status` field, a superset `TextChoices`** covering both channel's
   vocabularies (`DRAFT, PENDING, CONFIRMED, RESERVED, SHIPPED, IN_TRANSIT,
   DELIVERED, COMPLETED, CANCELLED, RETURNED, REFUNDED`). "No per-channel
   schema" is read as: don't branch the *shape* by channel — a channel-specific
   vocabulary is just a subset of *values* the same field can hold, the same
   way `Location.kind` classifies without a separate table per kind.
3. **`Sale.external_reference`** (blank-by-default `CharField`, unique with
   `sales_channel` via a partial constraint once set) is added now, pulled
   forward from Phase 9's stated idempotency key
   (`(sales_channel, external_reference)`) — the same precedent as
   `inventory.Location` landing in Phase 3 ahead of the Phase 4 ledger
   (ADR-007). A blank string (not `NULL`) represents "no external order", so
   the field stays an ordinary `CharField` (ruff's `DJ001`); the constraint's
   condition excludes the blank value instead of an `isnull` check.
4. **Reservation and the inventory/serialized-unit link are explicitly out of
   scope.** `SaleLine` has no `serialized_unit` FK — Phase 8's own prompt
   reserves that schema decision for when the `AVAILABLE → RESERVED → SOLD`
   flow is actually built; guessing the shape now (single FK vs. a per-unit
   join row for a multi-quantity line) would likely be wrong. Likewise no
   `customer` FK (`apps.customers` doesn't exist until Phase 11) and no
   `location` FK on `Sale`/`SaleLine`.
5. **Line pricing is a snapshot, not a live read.** `SaleLine.unit_price`/
   `tax_rate` are copied from `variant.effective_selling_price`/
   `effective_tax_rate` when the line is added, following the same
   GST-inclusive convention as `ProductVariant.base_price`/`gst_amount`
   (taxable value derived backward from an inclusive price). A placed order
   must not drift when the catalog price changes later.
6. **`SalesTotalsService.recalculate(sale)`** is the only writer of `Sale`'s
   four derived total columns, taking a `select_for_update` row lock and
   summing every line's derived properties — the same lock-then-write shape as
   `InventoryService` (ADR-009). No Django signals (none exist anywhere in this
   codebase); every line-mutating view action calls it explicitly.

**Consequences.** Adding Shopify/Flipkart later touches no code — one bootstrap
row. Amazon CSV import (Phase 9) can set `external_reference` without a
migration on `Sale`. The line-mutation API (`POST .../lines/`, `PATCH`/`DELETE
.../lines/{id}/`, mirroring `StockTransfer`'s action style) exists ahead of any
consuming UI — Phase 8's POS cart is expected to call it directly, per its own
prompt text. A `Sale` can currently reference more `quantity` than exists in
stock; that's intentional, not an oversight — inventory/reservation wiring is
entirely Phase 8.

---

## ADR-013 — Billing: `SaleLineUnit` join table, advisory-locked invoice numbering, CGST/SGST-only tax

**Status:** Accepted (Phase 8)

**Context.** ADR-012 deliberately deferred the schema for binding a
`SaleLine` to real `SerializedUnit` rows ("a single FK vs. a per-unit join row
for a multi-quantity line") until the `AVAILABLE → RESERVED → SOLD` flow was
actually built. Phase 8 (`HEXAGARE_FEATURES.md` §23–28, rules 5–8) builds that
flow plus `apps.billing` (`Payment`/`Invoice`/`InvoiceDelivery`) net-new.

**Decision.**

1. **`SaleLineUnit`** (`apps.sales`) is a join table, not a single FK on
   `SaleLine` — every physical item is a distinct serialized unit, and a line
   with `quantity > 1` needs to bind more than one. `serialized_unit` is a
   `OneToOneField` (`PROTECT`) so a unit is bound to at most one line anywhere
   at a time; `sale_line` is `CASCADE`. `SaleLine.quantity` stays a stored
   column (unchanged from ADR-012) but is now kept in sync with
   `units.count()` by `apps.sales.services.units.SaleUnitService` — the only
   path that adds/removes a bound unit — rather than becoming a derived
   property, so the existing `gross_amount`/`net_amount`/... properties on
   `SaleLine` needed no change. A manual `quantity` edit
   (`PATCH .../lines/{id}/`) is rejected once a line has bound units.
2. **Two ways into the cart, one service.** `SaleUnitService.add` accepts
   either `code` (a scanned/typed serial or barcode — HEXAGARE_FEATURES.md
   §24's exact-unit flow) or `variant` (a product-search add, no serial
   picked by the cashier) and auto-selects the oldest `AVAILABLE` unit
   (FIFO by `sequence`) in the latter case. Both paths reserve through the
   existing `SerializedInventoryService.reserve()` (Phase 4/7), so the stock
   ledger stays in step automatically — no new ledger-writing code was
   needed, just wiring. A race on "the oldest available unit" is resolved
   safely by `reserve()`'s own row lock (the loser gets a clean
   `validation_error`, never a double-reservation) rather than a second
   pre-lock.
3. **Sale completion requires every line to be fully unit-backed**
   (`quantity == units.count()`). The pre-existing generic
   `POST /sales/{id}/lines/` endpoint (ADR-012, quantity + variant, no units)
   is left completely unchanged — it still builds a draft/quote line — but
   `CompleteSaleService.complete()` refuses to sell a sale containing one,
   naming the offending line(s). This is the enforcement point, not
   line-mutation time, so ADR-012's existing line-mutation API needed no
   behavior change.
4. **`SaleLineUnit` rows are a permanent record once a sale completes** —
   never deleted. Phase 10 (Returns) needs to resolve "which sale/line did
   this serial sell on"; deleting the join row after sale would destroy that.
   Rows for a still-`DRAFT` line *are* deleted on unit-remove, line-delete, or
   sale-cancel (`SaleUnitService.remove`/`release_all`), each of which also
   releases the unit back to `AVAILABLE` first — a discarded cart keeps no
   unit history, but a completed sale's is permanent.
5. **Invoice numbering mirrors serial allocation (ADR-008)**: a global
   counter (`Invoice.sequence`, a plain integer column so allocation reads a
   `Max()` aggregate rather than re-parsing the formatted `invoice_number`
   string) behind a Postgres advisory lock, a distinct namespace key (`1002`,
   vs. the serial allocator's `1001`). Format
   `<HEXAGARE_INVOICE_PREFIX>-<padded sequence>` (new
   `HEXAGARE_INVOICE_PREFIX`/`HEXAGARE_INVOICE_PADDING` settings, same
   env-backed pattern as the SKU/serial prefixes).
6. **`Invoice` mirrors `LabelBatch`'s async-PDF shape exactly** (ADR-010):
   `status` `PENDING → READY`/`FAILED`, `pdf_file`, `pdf_generated_at`,
   `error_message`; `apps.billing.tasks.render_invoice_pdf` is enqueued via
   `transaction.on_commit` right after `CompleteSaleService` commits — the
   units are already sold and payment already recorded by the time it runs,
   so a render failure is fully recoverable (marks `FAILED`, never unwinds
   the sale) and never blocks checkout on PDF generation.
7. **CGST/SGST split only, no IGST.** `SaleLine.cgst_amount`/`sgst_amount`
   (an even split of `tax_amount`, same convention as
   `ProductVariant.cgst_amount`/`sgst_amount`) are the only GST breakdown the
   invoice PDF prints. Inter-state detection needs a customer/business "place
   of supply", which doesn't exist until `apps.customers` (Phase 11) — a
   documented simplification, not an oversight. Revisit when customer/
   business state data lands.
8. **`Payment.type` (`PAYMENT`/`REFUND`) is modeled now**, even though only
   `PAYMENT` is used this phase — Phase 10's own prompt says returns "refund
   via Payment," so this avoids a second payment-like model later.
   `amount` is always positive; a refund is a `REFUND`-typed row, not a
   negative amount.

**Consequences.** Phase 10 (Returns) can resolve a sold serial back to its
`Sale`/`SaleLine` via `SaleLineUnit` without a schema change, and record its
refund as a `Payment` row without a new model. Phase 9 (Amazon import) is
unaffected — imported historical orders don't need to go through
`SaleUnitService`/`CompleteSaleService` at all if they arrive already
"sold" (that decision is Phase 9's own, not made here). Adding IGST later
needs a `place_of_supply` concept plus a branch in `SaleLine`'s tax
properties and the invoice PDF — not a `SaleLineUnit`/`Invoice` schema
change.

---

## ADR-013 addendum — Payment must cover the total to complete a sale; hold/resume; post-completion settlement

**Status:** Accepted (Phase 8, post-launch correction)

**Context.** ADR-013's original point 1 read: "completion does **not**
require `sum(amount) == Sale.grand_total` — partial/credit sales are
allowed." In practice this meant `CompleteSaleService.complete()` sold every
bound unit and generated an invoice as soon as *any* payment was recorded,
regardless of amount — a ₹500 cash payment on a ₹5,499 sale marked the unit
`SOLD` and produced a `READY` invoice showing a `balance_due`. Manual testing
against the live app surfaced this immediately as wrong: an underpaid sale
must not be treated as sold inventory.

**Decision.**
1. **`CompleteSaleService.complete()` only sells units and creates the
   invoice once `sale.amount_paid >= sale.grand_total`** (after recording
   whatever `payments` were just submitted). Short of that, `Sale.status`
   becomes `RESERVED` — the existing "on hold" value from ADR-012's Offline
   status vocabulary — and nothing else changes: units stay `RESERVED`, no
   `Invoice` row is created. `Sale.amount_paid`/`Sale.balance_due` (new
   properties, walking the reverse `payments` accessor) let every screen
   show the running total without an `Invoice` existing yet.
2. **`complete()` now accepts a `RESERVED` sale, not just `DRAFT`** — calling
   it again with more `payments` is how a held sale is resumed. A `CREDIT`
   payment still counts toward `amount_paid` like any other method (an
   explicit business decision to extend credit completes the sale and sells
   the goods; an *unrecorded* shortfall does not).
3. **`CompleteSaleService.record_payment()`** is a second, narrower entry
   point for a sale that's already `COMPLETED` — settling more of a
   receivable (e.g. a `CREDIT` balance being paid back) without re-selling
   units or touching the existing invoice. `CheckoutView` dispatches between
   `complete`/`record_payment` based on the sale's current status, so the
   frontend always calls the same `POST /billing/checkout/` regardless of
   which case applies.
4. **Frontend: New Bill supports "resume."** `/sales/new?sale=<id>` loads an
   existing `DRAFT` (full cart edit, exactly as before) or `RESERVED` sale
   (cart locked — items can't be added/removed, only more payment recorded).
   The Orders list links to this for any `DRAFT`/`RESERVED` row ("Resume" /
   "Collect payment"). The Invoice detail page gained a small settle-balance
   form (visible only when `balance_due > 0`) that posts to the same
   checkout endpoint, landing on `record_payment`.
5. **Frontend: a real camera scanner in New Bill**, not just a text input —
   `frontend/src/features/sales/camera-scan-panel.tsx`, lazy-loaded behind a
   toggle button (same ADR-011 code-split reasoning as the standalone
   `/barcode/scan` route: ZXing stays out of New Bill's main chunk).

**Consequences.** `docs/domain-model.md`'s Billing section describes the
corrected flow directly (not as a diff) since this was caught and fixed
within the same phase, before merge. The original ADR-013 point 1 is
superseded by this addendum. No schema change beyond the two new `Sale`
properties — `Payment`/`Invoice`/`SaleLineUnit` are unchanged.

---

## ADR-014 — Amazon order import: bypasses cart/checkout, order-level
atomicity, configured fees are a fallback

**Status:** Accepted (Phase 9)

**Context.** ADR-013 flagged but deferred this decision: "imported
historical orders don't need to go through `SaleUnitService`/
`CompleteSaleService` at all if they arrive already 'sold' (that decision is
Phase 9's own, not made here)." Phase 9 adds CSV import of Amazon orders
(`apps/integrations/amazon`), and several shapes needed deciding: how an
already-happened, already-invoiced-by-Amazon order should touch the local
sales/inventory model; how a CSV spanning many orders should fail (or not)
as a unit; and how "Amazon fees must be configurable" (§22) interacts with a
CSV that may or may not already contain actual fee figures.

**Decision.**

1. **Import bypasses `SaleUnitService` and `CompleteSaleService` entirely.**
   `AmazonOrderImportService` creates `SaleLine`s directly and, for an order
   whose status means stock left the business, calls
   `SerializedInventoryService.reserve()` then `.sell()` directly per unit
   (both calls still required — the state machine has no direct
   `AVAILABLE → SOLD` edge) and writes `SaleLineUnit` rows itself. **No
   `Payment`/`Invoice` is created** — Amazon invoices the customer directly;
   Hexagare only needs the sale record and the settlement financials.
2. **Order-level atomicity, not batch-level.** Rows are grouped by
   `order_id`; each order commits (or rolls back) in its own
   `transaction.atomic()`. One bad order (unknown SKU, insufficient stock,
   conflicting statuses across its rows) is recorded in the batch's
   `error_log` and skipped — it never fails the rest of the file. Within one
   order it's all-or-nothing; there is no partially-imported order.
3. **Idempotent re-import, with a finalization rule.** `Sale` is keyed
   `(sales_channel, external_reference)`, `AmazonOrderSettlement` on `(sale,
   sku)`. An order that hasn't sold units yet is fully rebuilt on every
   re-import. Once it has (any bound `SaleLineUnit`), it is **finalized**:
   re-import only ever advances `Sale.status` forward along the
   pre-cancellation lifecycle; a CSV trying to move a finalized order to
   `CANCELLED`/`RETURNED`/`REFUNDED` is **not applied** (logged as a failed
   order instead) rather than silently mismatching units the importer has no
   way to reverse. Reversing sold stock is Phase 10 Returns' job.
4. **`SaleLine` pricing snapshots the CSV's actual values**
   (`selling_price`/derived `tax_rate`), not `variant.effective_*` — for a
   historical import, "what was actually charged" is the correct snapshot,
   which can differ from today's catalog price. This is a deliberate
   divergence from how a locally-created `Sale` snapshots pricing at
   add-time (ADR-012); the meaning ("price actually charged, frozen at time
   of sale") is preserved, only the source differs.
5. **Fee columns: CSV value wins; blank falls back to `AmazonFeeConfig`.**
   This is what makes "fees must be configurable because rates change"
   (§22) load-bearing rather than decorative: if the CSV already has actual
   fees (a real settlement report), they're used as-is; if a column is
   blank (a simpler order export), the importer computes it from the active
   config matching product → category → channel-wide, narrowed to the
   order's date. Nothing configured ever overrides real data.
6. **`AmazonFeeConfig` includes an `applicable_channel` (`sales_channel`)
   FK**, even though only the `AMAZON` channel exists today — matching
   §22's field list literally, so a second marketplace integration (a
   Flipkart/Meesho adapter reusing the same fee-config shape) needs no
   migration, just new rows.
7. **Amazon-specific per-line financials live on `AmazonOrderSettlement`,
   never on `Sale`/`SaleLine`** — the same channel-specific-data pattern
   `docs/architecture.md` already establishes, applied for real for the
   first time. `settlement_amount`/`net_revenue`/`product_cost`/`net_profit`
   are computed properties matching HEXAGARE_FEATURES.md §21's worked
   example, not stored columns.

**Consequences.** `apps.integrations` stays a single Django app with an
`amazon` subpackage (`apps/integrations/amazon/{models,sources,services,
tasks,serializers,views,urls,admin}.py`) rather than becoming its own app —
thin re-export shims at `apps/integrations/{models,admin,tasks}.py` exist
only so Django's app registry / `admin.autodiscover()` /
`celery.autodiscover_tasks()` (which all look for `<app>.<module>`, not a
nested subpackage) find them; migrations stay at the conventional
`apps/integrations/migrations/`. A future channel gets a sibling subpackage
(`apps/integrations/flipkart/`, ...), not a new Django app. See
`docs/amazon-order-import.md` for the full CSV format and idempotency rules.

---

## ADR-015 — Returns: modeled in `apps.billing`, channel-agnostic by
construction, refund-amount snapshot is an even split

**Status:** Accepted (Phase 10)

**Context.** HEXAGARE_FEATURES.md §31/§59: scan a sold serial, resolve it
back to its original `Sale`/`SaleLine`, refund, move the unit
`SOLD → RETURNED`, then a separate inspection step resolves it to
`AVAILABLE` (resellable) or `DAMAGED`. No domain app named "returns" exists
in the fixed app list (CLAUDE.md); the flow is fundamentally a refund/
money-flow action layered on an already-placed sale, the same shape as
`apps.billing.services.checkout.CompleteSaleService` (which also spans
`apps.sales` and `apps.products` without becoming a `sales`/`products`
change).

**Decision.**
1. **New models `Return`/`ReturnUnit` live in `apps.billing`**, not
   `apps.sales` or a new app — same reasoning ADR-013 already established
   for `Payment`/`Invoice`/`CompleteSaleService`. `ReturnUnit.serialized_unit`
   is a plain `ForeignKey`, not `OneToOneField` (contrast `SaleLineUnit`) —
   a unit can be sold again after being restored to `AVAILABLE`, so it can
   legitimately have more than one `ReturnUnit` row over its lifetime.
2. **Resolution is channel-agnostic by construction, closing Phase 9's
   gap.** `ReturnService.resolve`/`.create` go through
   `SerializedUnit.sale_line_unit` (Phase 8's `SaleLineUnit`), which every
   `SOLD` unit has whether it was sold through the offline POS checkout or
   the Amazon CSV importer (Phase 9 notes 82/89) — no channel branch
   anywhere. This is deliberately how "a CSV reporting an already-finalized
   Amazon order as `RETURNED`/`REFUNDED` is logged as a failed row rather
   than reversed" (ADR-014 point 3) gets closed: an operator now processes
   that return manually here, by scanning the serial, regardless of which
   channel sold it.
3. **One `Return` = one refund transaction against one `Sale`.**
   `ReturnService.create` rejects a call whose scanned serials resolve to
   more than one `Sale` — a return does not span sales. Multiple units from
   the *same* sale are fine and share one refund `Payment` row
   (`type=REFUND`, reusing the model exactly as ADR-013 point 8 already
   reserved it for this phase).
4. **`ReturnUnit.refund_amount` snapshots an even split of the original
   line's net amount across its bound units**
   (`SaleLine.net_amount / SaleLine.quantity`, quantized) — `SaleLine`
   carries no per-unit discount breakdown, so this is the best available
   default. The cashier may override the suggested amount per unit before
   submitting (HEXAGARE_FEATURES.md §31 lists "Refund amount" as its own
   field, implying it's adjustable, not strictly derived).
5. **`Sale.status` is deliberately left untouched by a partial unit
   return.** `Sale.Status.RETURNED`/`REFUNDED` (added in Phase 7 for
   channel-status vocabulary) are not written by this flow — a `Sale` can
   have some units returned and others still `SOLD`, so collapsing that
   into one `Sale.status` value would lose information. Return state lives
   at the `Return`/`ReturnUnit` level, queryable via `Return.sale`.
6. **One refund method per `Return`, not split-tender.** Unlike
   `CompleteSaleService.complete`'s `payments: list[...]`, a return records
   exactly one `Payment` row for the summed refund — split-tender refunds
   weren't asked for and would add a second "list of entries" shape for a
   flow that already has one (the scanned units themselves).
7. **Inspection is a separate step/model state, not folded into `create`.**
   `ReturnUnit.condition` starts `PENDING` (the unit is `RETURNED` but not
   yet inspected) and is set exactly once by `ReturnService.inspect`, which
   calls the existing `SerializedInventoryService.restore()` (→
   `AVAILABLE`) or `.damage()` (→ `DAMAGED`) — both already existed and
   needed no changes; `ALLOWED_TRANSITIONS` already had `SOLD → RETURNED`
   and `RETURNED → {AVAILABLE, DAMAGED}` before this phase.

**Consequences.** No RBAC change — the single `returns` codename (reserved
since Phase 1) gates every action (`resolve`/list/retrieve/create/inspect),
already held by Cashier/Manager/Admin, not Warehouse. No new
`InventoryTransaction.Kind` — `RETURN`, `DAMAGE`, `RESTORE` already existed.
Frontend: `frontend/src/features/returns/` (list, scan-based "New Return",
detail-with-inspect-actions), replacing the Phase 0 stub route.

## ADR-016 — Customers: one model for registered + walk-in, `Sale.customer`
nullable and `PROTECT`, purchase history computed on read

**Status:** Accepted (Phase 11)

**Context.** HEXAGARE_FEATURES.md §29/§30: customers need a profile (name,
phone, email, address, GSTIN, notes), a purchase/refund/outstanding summary,
and a serial-number history; walk-in sales must work with "no registration
required" at all, while the POS should also support a lightweight walk-in
record (name/phone) added inline without leaving the New Bill screen.

**Decision.**
1. **One `Customer` model for both registered and walk-in**, distinguished
   only by a `type` field (`REGISTERED`/`WALK_IN`). Every field besides
   `name` is optional regardless of type — a walk-in quick-added from POS
   with just a name/phone can be "upgraded" to a full registered profile
   later by editing the same row, never a migration to a different model.
2. **`Sale.customer` is a nullable, `PROTECT` string FK to
   `customers.Customer`.** `null` is the true "no registration required"
   walk-in (§30) — no `Customer` row is created at all. This is distinct
   from a `Customer` row with `type=WALK_IN`, which is a deliberate choice
   to keep a name/phone on record (for support/returns) without full
   registration. `PROTECT` mirrors the guard already used for
   `inventory.Location` (Phase 4 note 40) and `sales.SalesChannel` — a
   customer with sales history cannot be deleted, surfaced as a friendly
   `validation_error`, not a 500; the `apps.customers` API blocks deletion
   the same way before the FK constraint would ever fire.
3. **Attaching/changing/clearing the customer on a sale is its own action**
   (`POST /sales/{id}/customer/`), not a field on the generic `Sale` update
   path — `SaleViewSet` deliberately has no `UpdateModelMixin` (ADR-012)
   and every other sale mutation already goes through a dedicated action
   (`lines/`, `units/`, `cancel/`). Unlike cart edits, this action is not
   gated on `sale.is_editable` — linking a customer is metadata, not a
   line/total change, so it works on a `RESERVED` (on-hold) or even
   `COMPLETED` sale too.
4. **Purchase-history aggregates (`total_purchases`, `total_refunds`,
   `outstanding_amount`, `serial_numbers`) are computed on read in
   `apps.customers.services`, not cached columns** — same reasoning as
   `Sale.amount_paid` / `Return.refund_total`. `apps.customers` reads
   `apps.sales`/`apps.billing`/`apps.products` models directly (one
   directional: neither of those apps imports `apps.customers` back, only
   the string FK on `Sale.customer` points at it), matching this project's
   scale (dozens/hundreds of orders per customer, not thousands) rather
   than adding a separate paginated per-section endpoint.
5. **`Sale.Status.DRAFT`/`CANCELLED` sales don't count toward a customer's
   `total_purchases`** — a draft never reached checkout and a cancelled
   sale never completed; every other status (including `RESERVED`
   "on hold") counts, since real money/stock may already be committed.

**Consequences.** No RBAC change — `customers.view`/`customers.manage`
(reserved since Phase 1) already gate every `apps.customers` endpoint,
held by Cashier/Manager/Admin, not Warehouse. Amazon-imported and any
pre-Phase-11 offline sales keep `customer=None` — no backfill migration,
since the column is nullable and the importer (Phase 9) still has no
customer-identity data to attach. Frontend: `frontend/src/features/customers/`
(list with inline create, detail with aggregates/order-history/serial-
history and inline edit, and a `CustomerPicker` reused inside New Bill for
both searching an existing customer and the walk-in quick-add flow),
replacing the Phase 0 stub route at `/customers`.
