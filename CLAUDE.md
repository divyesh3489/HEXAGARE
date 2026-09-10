# CLAUDE.md

This file provides guidance to Claude Code when working in this repository. Read it fully at the
start of every session — it is the source of truth for architecture, workflow, and where the
project currently stands.

---

## What this is

Hexagare is a product/inventory/billing system, initially for a custom mouse pad business
(sells on Amazon + offline) but built to work for **any product category** — nothing in the
design should be mouse-pad-specific. Backend: Django REST API (`backend/hexagare`). Frontend:
React + Vite + TypeScript (`frontend`). Run together via Docker Compose with PostgreSQL, Redis,
and Celery. This repo starts empty — nothing described below exists yet. It gets built phase by
phase per `HEXAGARE_BUILD_PROMPTS.md`, and this file's **Current Phase** section (bottom) tracks
exactly how far along it is.

---

## Target Architecture

This is the intended design for the whole project. Build toward it phase by phase — don't build
a different shape "for now" without recording why in `docs/decisions.md` as an ADR.

- **Modular monolith**: one Django/DRF backend split into domain apps under
  `backend/hexagare/apps/`: `accounts`, `products`, `inventory`, `sales`, `integrations`,
  `billing`, `customers`, `purchases`, `suppliers`, `expenses`, `reports`, `notifications`,
  `common`. Add functionality to the domain app it belongs to, not a catch-all.
- **Settings** live in `backend/hexagare/hexagare/settings/` — `base.py` holds shared config,
  `development.py`/`staging.py`/`production.py` extend it, selected via the `DJANGO_ENV` env var.
  Environment-specific config never goes in `base.py`.
- **API versioning**: all routes mounted under `/api/v1/` in `hexagare/urls.py`, one `include()`
  per app's `urls.py` (`DefaultRouter` for viewsets, explicit `path()` for non-CRUD actions).
- **Auth & RBAC**: JWT via `rest_framework_simplejwt`, `IsAuthenticated` by default. Roles →
  permission-name sets live in `apps/accounts/rbac.py`, materialized into Django
  `Group`/`Permission` objects via `ensure_role_groups()`, enforced with custom `BasePermission`
  subclasses built on `apps/accounts/permissions.py:HasOperationalPermission`. Grep `rbac.py`
  before inventing a new permission codename — some codenames may already be reserved for
  features not built yet. Multi-action viewsets gate per-action via `get_permissions()`, not one
  fixed `permission_classes`.
- **Response envelopes**: a global DRF `EXCEPTION_HANDLER`
  (`apps.common.exceptions.api_exception_handler`) normalizes errors to
  `{"error": {"code", "message", "fields"?}}`; list endpoints go through
  `apps/common/pagination.py:StandardPagination` → `{"data": [...], "meta": {"count", "next",
  "previous"}}` (`page`, `page_size`, max 100). Never return raw DRF shapes from a new view.
  Binary responses (barcode images, label/invoice PDFs) go through
  `apps/common/renderers.py:BinaryRenderer`.
- **Catalog model** (`apps/products`): `Category` → `Product` → `ProductVariant`, plus
  `ProductAttribute`/`ProductAttributeValue` for data-driven variant properties (size, color,
  material — never product-specific columns), `ProductImage`, `LabelSize`. **SKU is a unique
  column on `ProductVariant`**, not a separate model. Pricing (`mrp`, `selling_price`,
  `purchase_price`, `tax_rate`) are columns on **both** `Product` (optional defaults) and
  `ProductVariant` (nullable overrides — `NULL` inherits the product); read the resolved values
  via the variant's `effective_*` / `base_price` / `gst_amount` / `discount_*` properties.
  `discount` is always derived from MRP and selling price, never stored. This is a deliberate,
  documented simplification (ADR-002 = SKU as a column; ADR-005 = the pricing-inheritance shape)
  — don't "upgrade" pricing/SKU to standalone entities without a new ADR.
- **Serialized units** (`apps/products`): each physical unit gets an immutable, globally unique
  serial number (`<HEXAGARE_SERIAL_PREFIX><variant-code>-<zero-padded sequence>`, e.g.
  `HXMP1123-000001`; prefix/padding from `HEXAGARE_SERIAL_PREFIX`/`HEXAGARE_SERIAL_PADDING`
  settings, distinct from `HEXAGARE_SKU_PREFIX`) allocated under a Postgres advisory lock, and a
  required `location` FK (`apps.inventory.Location`) — no free-text location field.
  `SerializedInventoryService` is the **only** path allowed to transfer/sell/damage/lose/return a
  unit — it locks the unit row, applies the model's own `ALLOWED_TRANSITIONS` state machine, and
  records a matching `InventoryTransaction` in the same atomic block. Never bypass it with a
  direct field edit. Barcodes are Code128 renderings of the serial, generated **on demand**,
  never stored as images.
- **Inventory ledger** (`apps/inventory`): `Location` (generic stock-holding place, seed rows
  Warehouse/Amazon/Offline via a `post_migrate` bootstrap hook, classified by `kind` for
  reporting only — never branch on name) and `InventoryBalance` (read cache) are never written
  to directly — `apps/inventory/services/ledger.py:InventoryService` is the only writer, and
  every change produces an immutable `InventoryTransaction` row, optionally tagged with a
  `serialized_unit` kwarg.
- **Sales/orders are channel-agnostic** (`apps/sales`): `SalesChannel` (seed rows
  `AMAZON`/`OFFLINE`, extensible with zero code changes — never hardcode a channel name/code in
  logic) and one generic `Sale`/`SaleLine` model for every channel, no per-channel schemas.
  `Sale.subtotal/discount_total/tax_total/grand_total` are derived, read-only —
  `apps/sales/services/totals.py:SalesTotalsService` is the only writer, recalculating from lines
  under a row lock whenever a line changes. `Payment`/`Invoice`/`InvoiceDelivery`, and wiring
  sale completion to the inventory ledger (`SerializedInventoryService.sell()` on payment), get
  built together — don't build one without the other.
- **Amazon order import** (`apps/integrations`): CSV-only to start —
  `apps/integrations/amazon/sources.py:AmazonOrderSource` is the abstraction a future SP-API
  adapter implements; `AmazonOrderImportService` depends only on that interface, never on CSV
  parsing directly. Amazon-specific per-line financials (fees, shipping, advertising, refunds,
  net revenue) live on `AmazonOrderSettlement`, not on `Sale`/`SaleLine` — same pattern for any
  future channel-specific data. Idempotent by design: `Sale` keyed on
  `(sales_channel, external_reference)`, `AmazonOrderSettlement` on `(sale, sku)`. Runs via a
  Celery task, never inline on the upload request.
- **Async work**: Celery + Redis for anything slow or externally delivered (PDFs, email/WhatsApp,
  image processing, Amazon import, exports). Pattern: commit the business transaction in Postgres
  first, enqueue the Celery task after — never hold an HTTP request open for this. Tasks live in
  each app's `tasks.py`, autodiscovered via `hexagare/celery.py`. Test with
  `@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)`.
- **Media/files**: object storage (S3 via `django-storages`), not local container paths in
  staging/production — Postgres stores metadata/object keys only. In development, `MEDIA_ROOT` is
  a local volume-mounted directory.
- API schema auto-generated via `drf-spectacular`, served at `/api/schema/` and `/api/docs/`.
- **Cross-app model references** use string FKs (e.g. `models.ForeignKey("inventory.Location",
  ...)`) to avoid circular imports — an established pattern, not something to "fix."
- **Docs that are authoritative once Phase 0 creates them** — read before structural changes:
  `docs/architecture.md`, `docs/domain-model.md`, `docs/decisions.md` (ADR log),
  `docs/serialized-units.md`, `docs/amazon-order-import.md`. Keep them updated as each phase adds
  or changes a structural decision — a stale doc is worse than no doc.

---

## Commands

All commands run through Docker Compose (a `Makefile` wraps the common ones — created in Phase 0):

```
make up              # docker compose up --build — postgres, redis, backend, celery-worker, celery-beat, frontend
make down
make logs
make migrate         # docker compose run --rm backend python manage.py migrate
make test            # docker compose run --rm backend python manage.py test
make lint            # ruff check on backend, npm run lint on frontend
make seed            # docker compose exec backend python manage.py seed_demo_data
make backend-shell
make frontend-shell
```

Copy `.env.example` to `.env` before first run and set a real `DJANGO_SECRET_KEY`. Seed reference
data (Locations, SalesChannels, RBAC role groups) is created automatically on every `migrate` via
`post_migrate` hooks — not by `make seed`, which only adds demo products/users.

Run a single Django test: `python manage.py test apps.<app>.tests.<module>.<TestCase>.<method>`
(inside the backend container). Backend lint: `ruff check --no-cache .` from `backend/hexagare`.
Frontend (from `frontend/`): `npm run dev`, `npm run build` (`tsc -b && vite build` — the only
type-check), `npm run lint`, `npm run preview`.

---

## Development Workflow — Plan Before Development

For every development task, **do not immediately start writing or modifying code.**

### Phase A — Understand the Request
1. Read the request in full, including which numbered phase of `HEXAGARE_BUILD_PROMPTS.md` it
   corresponds to.
2. Identify expected behavior and acceptance criteria.
3. Identify what's unclear or ambiguous.
4. Inspect the existing codebase for related/similar implementations already present.
5. Identify all affected areas: Frontend, Backend, API, Database, Auth/RBAC, Tests,
   Configuration, Third-party integrations, Deployment/CI.

Do not make code changes during this phase.

### Phase B — Create a Plan
Present: **Goal** (what and why) · **Current Implementation** (how it works today, if anything)
· **Files to Change** (created/modified, and what changes in each) · **Implementation Steps** (in
order — e.g. API validation → business logic → frontend integration → UI → tests → lint/type
checks → verify) · **Risks** (breaking changes, data integrity, security, performance, backward
compatibility) · **Testing Plan** · **Chrome DevTools Verification** (for frontend/UI changes —
skip and note "verified manually" if Chrome DevTools MCP isn't connected).

### Phase C — Stop for Approval
**Stop and wait for approval before modifying code.** Do not create, modify, or delete files, run
migrations, change dependencies, or implement anything until the user approves. Valid approvals:
`approved`, `go ahead`, `start`, or requested changes to the plan (update and ask again).

**Exception:** if the user explicitly says something like *"make the plan and implement it
without waiting for approval,"* proceed after presenting the plan.

### Phase D — Development
Follow the approved plan. Smallest appropriate changes. Follow the Target Architecture above and
existing conventions. Reuse existing services/utilities/components. No unnecessary dependencies,
no unrelated refactoring, no unrelated file changes. If implementation reveals the approved plan
is wrong or incomplete: **stop and explain the required change before continuing.**

### Phase E — Testing
Run the relevant checks (unit/integration/API/frontend tests, type checking, linting, build) using
the commands above. Never claim a test passed unless it actually ran. If a test fails: investigate,
determine if it's caused by this change, fix if appropriate, re-run. Never ignore a failing test.

### Phase F — Chrome DevTools Verification
For frontend/UI/browser changes, use Chrome DevTools MCP when connected and the app can run
locally: page loads, console errors, network errors/status codes, JS runtime errors, UI behavior
(forms, buttons, navigation, loading/error states), responsive layout, the relevant user flow.
Don't declare a frontend task complete without this when the MCP is available.

### Phase G — Final Review + Update This File
Before reporting completion:
1. Review the final git diff for accidental changes, debug statements, secrets/credentials.
2. Confirm tests were added/updated where necessary and the implementation matches the plan.
3. Confirm verification (automated or manual) was done.
4. **Update the "Current Phase" section below** — mark the just-finished phase done, name the
   next phase from `HEXAGARE_BUILD_PROMPTS.md`, and note any deviation from that file's prompt
   (so the next session isn't surprised). Do this as part of finishing the task, not as a
   separate ask.
5. If a structural/architectural decision was made this phase, add an ADR to
   `docs/decisions.md` and update the relevant doc in `docs/`.

### Final Response Format
Report: **What Changed** (brief) · **Files Changed** (with what changed in each) · **Tests** (only
checks actually run, e.g. `✓ Unit tests` / `✓ ESLint` / `✓ TypeScript` / `✓ Production build` —
never list one as passed unless it ran) · **Chrome DevTools** (for frontend changes: `✓ Page
loaded` / `✓ Console checked` / `✓ Network checked` / `✓ Feature manually verified`, or "not
connected — verified manually") · **Notes** (implementation decisions, known limitations,
follow-up work).

---

## Current Phase

**Status:** Phase 2 done — Backend `apps/products` (catalog only): `Category` (self-tree, `PROTECT`, `code`+`slug`), `Product` (`status`/`brand`/`tags`/`hsn_sac`/`weight`/`dimensions`/`notes` + optional default pricing `mrp`/`selling_price`/`purchase_price`/`tax_rate`), `ProductVariant` (unique `sku` column; `mrp`/`selling_price`(GST-incl)/`purchase_price`/`tax_rate` as **nullable overrides** that inherit the product — read `effective_*`; derived `base_price`/`gst_amount`/`cgst_amount`/`sgst_amount`/`discount_amount`/`discount_percent` per §5, ADR-005; no stored `discount`), `ProductAttribute`/`ProductAttributeValue` (data-driven, unique per `(variant,attribute)`), `ProductImage` (`ImageField` via `STORAGES` default — Pillow added; optional per-variant `variant` FK), `LabelSize` (2 defaults seeded via `apps/products/bootstrap.py` `post_migrate`). `services/sku.py:suggest_sku()`/`is_sku_available()` (advisory, DB-constraint-guarded). `SimpleRouter` viewsets + `sku/suggest/` + `sku/check/` under `/api/v1/products/`, per-action RBAC (`products.view`/`products.manage`) via `get_permissions()`. `make seed` → `apps/common` `seed_demo_data` (demo users + catalog, idempotent). Frontend `features/products/`: Categories page (CRUD), Products list/filters + create/edit form (with default-pricing section), product detail with `VariantManager` (attribute rows + editable auto-suggest `SkuField` + inherit-aware pricing + live GST/discount) and `ImageUploader` (multipart, per-variant scope). `make test` (92 tests), `ruff check`, `spectacular --validate` (0 warnings), frontend `eslint` + `tsc -b && vite build`, and a full `docker compose up` with the catalog flow exercised over HTTP all pass.
**Next up:** Phase 3 — Serialized Units + On-Demand Barcode (see `HEXAGARE_BUILD_PROMPTS.md`).
**Completed phases:** Phase 0, Phase 1, Phase 2.
**Notes / deviations from the plan:** (Phase 1 notes 1–12 unchanged; see git history.) Phase 2: (13) **`Pillow==11.1.0` added to `requirements.txt`** for `ProductImage.image` — rebuild the backend image (`docker compose build backend`). (14) [superseded by note 23 / ADR-005] `Product` originally had no pricing columns; it now carries optional default pricing that variants inherit. (15) `apps/products/urls.py` uses **`SimpleRouter`, not `DefaultRouter`** — `ProductViewSet` sits at the app-root prefix and `DefaultRouter`'s API-root would collide with its list route. (16) A partial unique constraint on `(product, variant.code)` was **dropped** — DRF's `UniqueTogetherValidator` forced `code` required and can't express the blank-exempt condition; variant `code` is now an unconstrained SKU hint. (17) `LabelSize` seeding via `post_migrate` (`bootstrap.py`, guarded against a missing table) is beyond the prompt's literal "Locations/SalesChannels" wording — same reference-data pattern, Phase 5 needs it. See ADR-004. (18) SKU suggestion takes **no advisory lock** (contrast Phase 3 serials) — the `sku` unique constraint + `is_sku_available()` are the guard; a race yields a `validation_error` + retry. (19) Chrome DevTools MCP not connected — frontend verified manually (SPA serves, `tsc`/`eslint`/`vite build` clean; catalog CRUD + SKU-suggest + variant nested-attr + GST derivation + image upload exercised via the live API). (20) **Variant-scoped images** wired up (backend `ProductImage.variant` FK already existed): `ImageUploader` has an "Attach to" scope selector, groups the grid by scope, and re-assigns images between scopes; `VariantManager` shows a per-variant thumbnail strip. Backend unchanged; +2 API tests (variant round-trip, cross-product `variant` rejected). (21) **Image URLs are storage-relative** — serializers return `image.url` verbatim (absolute S3 URL in staging/prod, `/media/...` in dev), never `request.build_absolute_uri()` which under the Vite proxy yields the container host (`backend:8000`). `MEDIA_URL` is now `/media/` (leading slash) and the Vite dev proxy forwards `/media` to the backend alongside `/api`. (22) **`seed_demo_data` implemented** (`apps/common/management/commands/`) — the `make seed` command referenced since Phase 0 finally exists: idempotent, adds 4 demo users (`{admin,manager,cashier,warehouse}@hexagare.test` / `demo-Passw0rd!`, password+role realigned every run) and a demo catalog (Peripherals tree, Size/Colour/Switch attrs, 3 products × 2 variants); refuses under `DJANGO_ENV=staging`/`production` without `--force`. Minor known wart: `CategorySerializer.parent_name` is omitted (not `null`) for top-level categories — frontend already treats it as optional. (23) **Pricing moved to a product→variant inheritance model (ADR-005, migration `0002`).** `Product` gained optional `mrp`/`selling_price`/`purchase_price`/`tax_rate`; `ProductVariant`'s same columns are now nullable overrides (`NULL` inherits); read `variant.effective_*` / `base_price` / `gst_amount` / `discount_*`. The `ProductVariant.discount` column was **dropped** — discount is derived (`max(mrp − selling_price, 0)` + percent) on both `Product` and `ProductVariant`. A variant is rejected unless its effective `selling_price` and `mrp` resolve non-null; `selling_price > mrp` just clamps discount to 0. Phase 7 `SalesTotalsService` must use `effective_*`. (24) **Variant availability derives from product status (ADR-006, computed — no migration).** `ProductVariant.is_active` is per-variant intent; `effective_status` (a `Product.Status` value) and `is_available` are derived — `draft`/`inactive`/`discontinued` products override every variant to that status (discontinued reads `discontinued`, not `inactive`), only `active` products defer to `is_active`. `?available=1` filter on the variant list; `ProductListSerializer.available_variant_count` (`0` unless product active). Frontend shows `effective_status`, disables the per-variant Active toggle unless the product is active, and banners non-active products. 92 backend tests.

*(Claude Code: update this section — Status, Next up, Completed phases, Notes — every time a
phase is finished, per Phase G of the workflow above. Keep it to these four lines so it stays
easy to scan at the start of a session.)*