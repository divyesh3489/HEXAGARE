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

**User-reported bugs:** the user does their own manual/live testing of the app. When they report
something is broken, reproduce and debug it live in the browser via the Claude-in-Chrome MCP
(navigate, click through the flow, read console/network) rather than asking them to describe
steps or paste logs first — go find it yourself.

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

**Status:** Phase 17 done — Settings + Security/Audit Polish (`HEXAGARE_FEATURES.md` §49-54,
ADR-020 — the whole Administration surface lives in `apps.accounts`, not a new app, since every
permission it needs was already reserved there since Phase 1). New models on `apps.accounts`
(migration `0002_backupjob_businesssettings_auditlogentry`): **`BusinessSettings`** (`pk=1`
singleton, `get_solo()`, bootstrapped via `post_migrate` like `Location`/`SalesChannel`) carries
business info, tax defaults, and blank-by-default *override* fields for
`sku_prefix`/`serial_prefix`/`serial_padding`/`invoice_prefix`/`invoice_padding` —
`apps.products.services.{serial_numbers,sku}` and `apps.billing.services.numbering` now call
`BusinessSettings.get_solo()` first and fall back to the existing `HEXAGARE_*` env-backed settings
unchanged when a field is blank, so every `@override_settings(HEXAGARE_SKU_PREFIX=...)`-style test
keeps passing untouched. **`AuditLogEntry`** (one generic-FK model, not a table per domain) covers
every HEXAGARE_FEATURES.md §53 action family via a fixed `Action` choices field; written through
exactly two hook shapes (`apps/accounts/audit.py`), per the build prompt's own instruction to "hook
into the exception handler / service layer rather than scattering log calls per view":
`AuditMixin` (added to `ProductViewSet`/`ProductVariantViewSet`/`LocationViewSet`/`ExpenseViewSet`
— logs create/update/delete automatically with a generic before/after field diff on update) and
`log_activity()` called directly from the one service method that already owns a non-CRUD
mutation — `SerializedInventoryService._apply` (the single shared engine behind every unit status
transition: reserve/release/transfer/sell/return/damage/lose/restore/cancel, one call site covers
all of them), `InventoryService.adjust` (manual stock corrections), `CompleteSaleService.complete`/
`record_payment` (payments + invoice creation), `ReturnService.create`, and the
`SaleViewSet`/`PurchaseOrderViewSet` create/cancel/payments actions. **`BackupJob`**
(PENDING→RUNNING→SUCCESS/FAILED, same shape as `ReportExport`/`LabelBatch`) is written by
`apps.accounts.tasks.run_database_backup`, a `pg_dump -Fc --no-owner --no-privileges` wrapper run
via Celery (never inline on the trigger request) — this needed **`postgresql-client-17` added to
the backend/celery-worker/celery-beat image** (`backend/hexagare/Dockerfile`; the base
`python:3.12-slim` image is Debian trixie, which already carries a matching `postgresql-client-17`
package natively, no PGDG repo needed), version-matched to the `postgres:17` compose service since
an older `pg_dump` isn't guaranteed to cleanly dump a newer server. Restore and scheduled/automatic
backups are explicitly out of scope this phase. API under `/api/v1/auth/`: `settings/` (GET any
authenticated user, PATCH `settings.manage`), `users/` (full CRUD except hard delete —
`deactivate/`/`reactivate/` toggle `is_active` instead — `users.manage`), `roles/` (read-only
role→permission matrix, `users.manage`), `audit-log/` (read-only, filterable by
`action`/`actor`/`object_type`/`date_from`/`date_to`, `audit.view`), `backups/` (create + list +
retrieve + `{id}/download/`, `settings.manage`) — **no new RBAC codenames**
(`settings.manage`/`users.manage`/`audit.view` were all reserved since Phase 1). Frontend: new
`frontend/src/features/settings/` — `GeneralSettingsPage` (read-only view + gated edit form),
`UsersPage` (list + inline create + inline role reassignment + deactivate/reactivate),
`RolesPage` (read-only role×permission matrix), `AuditLogPage` (filterable activity table),
`BackupsPage` (trigger + history + download, polls while a job is PENDING/RUNNING) — replacing the
three Phase 0 stub routes at `/settings`, `/settings/users`, `/settings/roles`, plus two new
routes/nav entries (`/settings/activity`, `/settings/backups`) under the existing Settings nav
group. Verified: `ruff check` clean; full `manage.py test` (429 tests, 28 new —
`apps/accounts/tests/test_administration.py`, covering the Administration surface itself
end-to-end — settings GET/PATCH/RBAC/singleton/audit-diff, user create/update/deactivate/
reactivate/RBAC/filtering, the roles matrix, audit-log list/filter/read-only, backup
trigger/history/download/failure-path — plus cross-app spot-checks confirming the log_activity
hooks actually fire: Location create/update/delete, a manual stock adjustment, order created/
cancelled, checkout payment+invoice creation, a return, a full purchase-order lifecycle
(create/payment/cancel), and expense create/update/delete) clean; `python manage.py spectacular
--fail-on-warn` surfaced only the same pre-existing 5 path-param warnings from earlier phases
(Phase 8 note 69's class), nothing new. `eslint` and `tsc -b && vite build` both clean. **Two real
bugs caught and fixed during this phase's own test-writing and live verification, not pre-existing:**
(1) `UserAdminCreateSerializer.role` wasn't `write_only` — creating a user crashed with
`AttributeError: 'User' object has no attribute 'role'` because DRF tried to read `.role` back off
the saved `User` for the 201 response (a `ChoiceField` with no `source=`/`write_only` and
`required=True` doesn't silently skip on a missing attribute the way a `required=False` field
does); fixed by marking `role` `write_only=True` and adding a read-only `id` field to the same
serializer so the create response is actually useful. (2) `BusinessSettingsView.perform_update`'s
audit diff included `updated_at`/`updated_by` on *every* save (they always differ), so every
"Settings updated" log entry carried a meaningless timestamp/actor diff alongside the real one —
excluded both from the diff. **Verified live** via the Claude-in-Chrome MCP against the running
dev stack (after rebuilding + `--force-recreate`-ing `backend`/`celery-worker`/`celery-beat` for the
new `postgresql-client-17` layer): edited Business Settings twice as Admin and confirmed the
Activity Log rendered a clean field-level diff each time (catching bug (2) above live); inline-
edited a user's role in the Users list; confirmed the Roles & Permissions matrix matches
`rbac.py` exactly; triggered two real manual backups (real `pg_dump` against the live dev
Postgres, not mocked) and downloaded one successfully; confirmed a Cashier login sees read-only
Business Settings (no Edit button) and a clean "Couldn't load ..." message on Users/Roles/Activity
Log/Backups, matching every prior phase's degraded-access pattern (the Phase 13-noted nav-filtering
gap means Cashier still *sees* these sidebar entries, unchanged, out of scope here too) — no
console errors beyond the pre-existing React Router future-flag warning. **One environment
observation, not a code bug:** `BackupsPage`'s poll-while-pending (`useBackups`'s `refetchInterval`,
the same pattern already relied on by `useReportExportStatus`/label-batches) never visibly re-fired
inside the automated Chrome tab even though the triggered Celery task completed in well under a
second server-side and a fresh page reload immediately rendered the correct final SUCCESS status —
this tab also produced repeated CDP "renderer may be frozen or unresponsive" screenshot timeouts
throughout the session, consistent with Chrome's background/inactive-tab timer throttling rather
than a regression in the polling code itself.

Previously: Phase 16 done — Dashboard (`HEXAGARE_FEATURES.md` §3, ADR-019 — placement in
`apps/reports` rather than a new `apps/dashboard` app, and per-group RBAC reusing each domain's
existing view permission rather than a new `dashboard` codename). New `apps/reports/dashboard.py`
(`DashboardService`, four static methods, no persistence of its own) behind a new `DashboardViewSet`
mounted at `/api/v1/reports/dashboard/{sales,inventory,finance,analytics}/` — `sales()` is a fixed,
param-free snapshot (running totals + today/week/month/year + per-channel breakdown, kept
param-free so its cache key is stable); `inventory()` is `SerializedUnit` status counts plus
low/out-of-stock/overstock counts from `compute_alerts()`; `finance(date_from, date_to)` (default:
current calendar month) delegates straight to `FinanceService.summary()`; `analytics()` is a 30-day
`sales_graph` (daily totals split by channel, feeding both the sales-trend and Amazon-vs-Offline
charts from one payload), top-selling products/SKUs via `ReportsService.sales(group_by=...)`, a
low-stock list, and recent orders/returns/stock-movements (last 10 each) — every widget reuses an
existing service rather than re-deriving aggregation logic. Each group is gated in
`get_permissions()` by its own domain's existing view permission (`sales.view`/`inventory.view`/
`finance.view`/`reports.view` for Analytics), not a new codename — see ADR-019 for why. §3's
"Recent barcode scans"/"Recent notifications" are out of scope — neither has a backing data model
yet (no scan-log model; `apps.notifications` has no models of its own per the Phase 15 note below);
both are left for Phase 17's activity/audit log. Frontend: `frontend/src/features/dashboard/`
replaces the Phase 0 stub at `/` — one hook + one section component per widget group, each with its
own independent loading/error state so a role without `finance.view`/`reports.view` sees a clean
"Couldn't load ..." message on just that card rather than the whole page breaking; two `recharts`
charts (first use of that dependency — added to `frontend/package.json`, kept in the main bundle
rather than code-split like the ADR-011 candidates, since the Dashboard is the landing page every
user hits). Verified: `ruff check` clean; full `manage.py test` (401 tests, 9 new,
`apps/reports/tests/test_dashboard.py` — RBAC per widget group across Admin/Manager/Cashier/
Warehouse plus one content-correctness test per group) clean; `python manage.py spectacular
--fail-on-warn` surfaced only the same 5 pre-existing path-param warnings from earlier phases
(Phase 8 note 69's class), nothing new from the dashboard endpoints. `eslint` and `tsc -b && vite
build` both clean. **Verified live** via the Claude-in-Chrome MCP against the running dev stack
(after a `docker compose up -d --force-recreate --renew-anon-volumes frontend` — the anonymous
`node_modules` volume needed a fresh recreate, not just `--build`, to actually mount the image's
`recharts` install; a plain `--build` alone silently kept serving the stale volume, same class of
gotcha as the Phase 6/9/15 container-recreate notes, just one step further this time): Admin login
shows all four widget groups populated from seed/demo data plus both charts rendering correctly;
Cashier login shows Sales+Inventory tiles with clean "Couldn't load finance figures."/"Couldn't
load analytics." messages on the two gated cards, confirming the degraded-access pattern; no
console errors beyond the pre-existing React Router future-flag warning on either login.

Previously: Phase 15 done — Notifications (Email + WhatsApp) (`HEXAGARE_FEATURES.md` §47,
narrowed to exactly the Phase 15 build prompt — invoice send + low-stock digest, not the
broader in-app "Dashboard Notifications" bell/center from §47, which is future/Phase-16-adjacent
territory — no ADR, since nothing here departs from established patterns). **`apps/notifications`**
(real implementation replacing the scaffold) — no models of its own; two isolated sender classes
in `services.py` (`EmailNotificationService` on Django's `EmailMessage`/`EMAIL_BACKEND`, already
configured since Phase 1 for password-reset; `WhatsAppCloudAPI` + `WhatsAppNotificationService`
wrapping the Meta Cloud API's `/messages` endpoint via `requests`, the project's first use of
that dependency) and two Celery tasks in `tasks.py`: **`send_invoice_delivery(delivery_id)`**
(dispatches by channel, updates the `InvoiceDelivery` row `SENT`/`FAILED` — same recoverable-
failure shape as `render_invoice_pdf`) and **`send_low_stock_alerts()`**, the project's first
`CELERY_BEAT_SCHEDULE` entry (interval via `LOW_STOCK_ALERT_INTERVAL_HOURS`, default 6h), which
reuses `apps.inventory.services.alerts.compute_alerts()` (Phase 4) unchanged, filters to
`out_of_stock`/`low_stock` only, and digests to whichever of `LOW_STOCK_ALERT_EMAILS`/
`LOW_STOCK_ALERT_WHATSAPP_TO` are configured (a flat operator-configured recipient list — no
per-user notification preferences exist, so this isn't tied to a role/user). WhatsApp messages
are sent as plain **text**, not a pre-approved template — Meta requires a template only for a
business-initiated first contact, and guessing at an approved template's component layout isn't
possible from code; a comment in `services.py` flags swapping to `send_template` once one exists.
**`InvoiceDelivery`** (`apps.billing`, Phase 8 schema) gains a `recipient` field (small additive
migration) recording the actual email/phone targeted. **`InvoiceViewSet.send`** (new action,
`POST /billing/invoices/{id}/send/`, `billing.manage` — same codename Cashier/Manager/Admin
already hold for invoice actions, no RBAC change) creates the `InvoiceDelivery` row and enqueues
the task via `transaction.on_commit`; `recipient` is optional in the request, defaulting to the
sale's linked customer's email/phone when omitted, rejected with 400 when neither resolves.
Frontend: `InvoiceDetailPage` gains a "Send invoice" card (channel select + recipient input +
Send button, plain-Tailwind `<select>` — no Dialog primitive exists in this project, same
inline-form style as the existing "settle balance" card) and renders `invoice.deliveries` with a
status badge and inline error message per row; `useInvoice`'s existing PDF-pending poll now also
polls while any delivery is `PENDING` (the actual send happens in the Celery worker, out of band
from the `send/` response). Verified: `ruff check` clean; full `manage.py test` (392 tests, ~20
new, all passing — run via `docker compose run --rm -e DJANGO_ENV=test backend ...`, i.e. `make
test`'s actual invocation; running `manage.py test` without `DJANGO_ENV=test` silently uses
*development* settings, where `CELERY_TASK_ALWAYS_EAGER=False` — Celery tasks enqueue against
the real Redis broker but nothing consumes them inside the test process, so any test asserting a
task's result fails with the task's target still `PENDING`/un-updated. This is almost certainly
the actual root cause behind the "10 pre-existing failures" flagged in the Phase 14 note below as
an `on_commit`/`captureOnCommitCallbacks` gap — with `DJANGO_ENV=test` set correctly, all 392
tests pass, that note's 10 tests included; left the Phase 14 entry itself unedited since it's a
historical record, but flagging here so a future session doesn't re-diagnose it as a
`captureOnCommitCallbacks` bug). `eslint` and `tsc -b && vite build` both clean. **Verified live**
via the Claude-in-Chrome MCP against the running dev stack: sent an existing READY invoice over
both Email (real SMTP attempt to the configured host, no credentials set in this dev `.env` →
correctly recorded `FAILED` with the real `535/530` auth error surfaced in the UI) and WhatsApp
(no Cloud API credentials configured → correctly recorded `FAILED` with a clear "not configured"
error) — confirms the send/enqueue/update/render round-trip end to end without needing real
credentials. **Two container-image gotchas hit and resolved live, worth remembering**: (1)
`celery-worker`/`celery-beat` only pick up brand-new task modules (`apps.notifications.tasks`
didn't exist when they were last started) on a real container **recreate**, not `docker compose
restart` (restart reuses the already-created container/image reference) — a stale worker
silently discarded the first `send_invoice_delivery` message with "Received unregistered task"
rather than erroring loudly; (2) similarly, the `frontend` Vite dev server's file-watcher on this
Windows/Docker Desktop bind mount did not pick up source edits via HMR without a container
restart. Neither is a code defect, both are noted here so the next session isn't surprised by an
API/UI change silently not taking effect against the already-running dev stack.

Previously: Phase 14 done — Reports + Exports (`HEXAGARE_FEATURES.md` §38-44, narrowed per the
build prompt to the six named report types and CSV/Excel only — no ADR, since nothing here departs
from established patterns). New **`apps/reports`** (real implementation replacing the scaffold).
**`ReportsService`** (`apps/reports/services.py`) is a read-only, no-cached-columns aggregation
namespace (same Python-loop style as `FinanceService`) with one method per report — `sales`,
`inventory`, `inventory_movement`, `serial_numbers`, `serial_number_history`, `products`,
`financial` — every one returning `(summary: dict, rows: list[dict])`; `rows` is the flat shape
used **both** for the on-screen table and for CSV/Excel export, so nothing is computed twice.
Reuses rather than re-derives: `FinanceService.summary()`/`by_channel()` for the Sales report's
profit line and the whole Financial report, `apps.inventory.services.alerts.compute_alerts()` for
the Inventory report's low/out-of-stock/overstock counts, and the existing
`apps.products.models.SerializedUnitEvent` log verbatim for Serial Number History (that model
still only carries `from_status`/`to_status`/the *new* location/a free-text note — no previous
location or related order/invoice/purchase/transfer links; this phase surfaces what's recorded, it
doesn't extend that Phase 3 model). Two filter vocabularies matching the domain: `channel`
(`SalesChannel`) scopes Sales/Products/Financial; `location` (`Location`) scopes
Inventory/Serial Numbers, since stock buckets are location-scoped, not channel-scoped. Grouped
Sales rows (by product/variant/category/serial) carry **gross** profit only (taxable sales minus
product cost) — full fee-apportioned net profit stays a Financial-report-level figure, to avoid
re-deriving Amazon-settlement attribution per row. **`ReportExport`** (new model) tracks a
CSV/Excel export job — `report_type`, `export_format`, `filters` (JSONField, exactly the query
params the job was requested with), `status` PENDING → READY/FAILED, `file`, `error_message`,
`requested_by` — same shape as `Invoice`/`LabelBatch`. **Every** export (not just large ones) goes
through Celery — `apps.reports.tasks.generate_report_export`, enqueued via `transaction.on_commit`
after `apps.reports.services.create_export()` commits the row — one code path rather than
branching sync/async by size. `apps/reports/exporters.py` (`rows_to_csv`/`rows_to_xlsx`, the
latter via the new `openpyxl` dependency) is shared by every report type. `apps.reports.services.
run_report(report_type, filters)` is the single dispatch point both the GET report views and the
export task call — a report is queried identically whether it's rendered on screen or exported.
API under **`/api/v1/reports/`**: `sales/`, `inventory/` (`?view=movement` switches to the ledger
view), `serial-numbers/`, `serial-number-history/` (`?serial_number=`), `products/`, `financial/`
(all `reports.view`, reserved since Phase 1, Admin/Manager only — no `rbac.py` change), plus
`exports/` (create/list/retrieve + `{id}/download/`, all `reports.export`, same restriction).
Frontend: new `frontend/src/features/reports/` — a `ReportsPage` with a button-group tab per
report type (no new Tabs primitive — matches the plain-Tailwind select/button style already used
elsewhere), date-range/channel/location/category filters per tab, a generic rows table (columns
derived from the row keys, since shape varies by report/grouping), and an "Export" dropdown
(CSV/Excel) that creates an export job, polls it (`useReportExportStatus`, same
`refetchInterval`-while-PENDING idiom as `useLabelBatch`), and triggers a browser download once
READY — replacing the Phase 0 stub route at `/reports` (nav entry already existed, gated
`reports.view`, unchanged). Verified: `ruff check` clean; full `manage.py test` (375 tests, 26 new,
all passing) — **10 pre-existing failures unrelated to this phase** were found in the same run
(Invoice/LabelBatch/Amazon-import PDF-and-status tests all asserting a `on_commit`-enqueued task's
result without wrapping the assertion in `captureOnCommitCallbacks`); confirmed via `git stash` that
these 10 fail identically on the pre-Phase-14 tree (349 baseline tests), so they're a pre-existing
gap in those tests' own setup, not a regression from this phase — left alone as out of scope,
flagged here for whoever picks it up. `eslint` and `tsc -b && vite build` both clean. **Not
verified live in the browser this phase** — the user is doing their own manual/live testing per
CLAUDE.md's "User-reported bugs" section; the local Docker stack (backend + rebuilt
celery-worker/celery-beat, now carrying `openpyxl`) is left running for that.

Previously: Phase 13 — Expenses + Profit/Finance (ADR-018, `HEXAGARE_FEATURES.md` §35-37).
New **`Expense`** model in `apps/expenses` (real implementation replacing the scaffold) —
`category` (fixed `TextChoices`: Amazon fees/Shipping/Courier/Packaging/Advertising/
Manufacturing/Raw materials/Offline expenses/Other expenses — a closed taxonomy, not a separate
model), `sales_channel` (optional FK, blank = general/business-wide), `amount`, `expense_date`,
`note`, `created_by`. **`FinanceService`** (`apps/expenses/services.py`) is a read-only
aggregation — same Python-loop style as `apps.customers.services`/`apps.suppliers.services`, no
cached columns: `summary(date_from, date_to, channel=None)` walks qualifying `Sale`s (excludes
`DRAFT`/`CANCELLED`) in the range, reuses `Sale.subtotal`/`tax_total`/`discount_total`/
`grand_total` for taxable/gross sales, GST and discounts; sums each sold unit's
`SerializedUnit.purchase_cost` (Phase 12, falling back to `variant.effective_purchase_price` for a
unit that predates per-unit cost tracking) for product cost; folds `AmazonOrderSettlement` (Phase
9) fee columns *and* matching `Expense` categories into `packaging`/`shipping`/`advertising`/
`amazon_fees`/`other_expenses` buckets (either can be the source of a given cost — an automatic
per-order Amazon figure, or a manually logged lump-sum expense); reports `Return.refund_total`
separately. `gross_profit = taxable_sales − product_cost`; `net_profit = gross_profit −
packaging − shipping − amazon_fees − advertising − other_expenses` — GST/discounts/refunds are
informational, not subtracted again in the waterfall (§36's diagram already starts from
post-discount revenue). `by_channel(date_from, date_to)` is the same summary per active
`SalesChannel`. `unit_profit(unit)` (§37) apportions a sale line's `taxable_value` — and, for an
Amazon order, its settlement's fee columns — evenly across the line's bound units, same even-split
reasoning `ReturnService` uses for refund amounts. API: **`/api/v1/expenses/`** (standard CRUD,
every action gated `expenses.manage` — no separate `.view` codename exists for this resource) and
**`/api/v1/expenses/finance/`** — `summary/?date_from=&date_to=&channel=`, `by-channel/`, and
`units/{unit_id}/profit/` (all `finance.view`; both codenames reserved since Phase 1, held by
Admin/Manager only). Frontend: new `frontend/src/features/expenses/` (`ExpensesPage` — list +
inline create/edit, filterable by category/channel/date range) and `frontend/src/features/
finance/` (`ProfitSummaryPage` — date-range picker, summary tiles for every §36 report line, a
by-channel breakdown table); a "Profit (this sale)" card was added to
`SerializedUnitDetailPage`, shown only for a `SOLD`/`RETURNED` unit and gated on `finance.view` —
replacing the Phase 0 stub routes at `/finance/expenses` and `/finance/profit` (nav entries already
existed, gated on `expenses.manage`/`finance.view` respectively, unchanged). `seed_demo_data`
gains four demo `Expense` rows spanning categories/channels/dates. Verified: `ruff check` + full
`manage.py test` (349 tests, 24 new) clean; `eslint` + `tsc -b && vite build` clean; a full Chrome
pass via the Claude-in-Chrome MCP on the live dev server — created and deleted an expense from the
Expenses page, confirmed the Profit summary page's tiles and by-channel table match a by-hand
recomputation from the seeded data across two date ranges, confirmed the "Profit (this sale)" card
renders correct figures on a sold unit's detail page, and confirmed a Cashier login (no
`finance.view`/`expenses.manage`) gets a clean "Couldn't load expenses" error on direct navigation
and no Profit card on the unit page — same degraded-access pattern as every prior phase, matching
the automated RBAC tests. No console errors beyond the pre-existing React Router future-flag
warning.

**Bug caught and fixed live (this phase):** `ProfitSummaryPage`'s default date range used
`new Date(...).toISOString().slice(0, 10)` to compute "first of this month" / "today" — `
toISOString()` converts through UTC first, which silently rolled the "first of month" default back
one calendar day in any timezone ahead of UTC (observed live: "From" showed `08/31/2026` instead
of `09/01/2026`). Fixed with a `localDateString()` helper that reads `getFullYear()`/`getMonth()`/
`getDate()` directly, no UTC round-trip; the same latent bug in `ExpensesPage`'s "New expense"
default date (this phase's own new code) was fixed the same way. Two other pre-existing call sites
with the identical pattern (`fee-settings-page.tsx`'s default `effective_from`, Phase 9) were left
alone — untouched by this phase, out of scope to fix incidentally.

**Bug found but not fixed (pre-existing, out of scope — nav permission filtering):** while
verifying RBAC live, a Cashier login still showed the Integrations nav group (Amazon
Import/Import History/Fee Settings/SKU Mapping — all gated `integrations.amazon`, which Cashier
lacks) in the sidebar. `frontend/src/components/layout/nav.ts` declares a `permission` field on
every entry, but `sidebar.tsx` (unchanged since Phase 1, confirmed via `git log`) never reads it —
nothing has ever actually filtered the sidebar by permission, across every phase. This is cosmetic,
not a security gap: every page still enforces its own permission via the API (403) and/or
`useHasPermission()`, exactly as verified for this phase's own Expenses/Profit pages. Left for a
future session (Phase 17 Settings/Security polish is the natural place) rather than expanding this
phase's scope into the shared layout component.

Previously: Phase 12 — Purchases + Suppliers (ADR-017, `HEXAGARE_FEATURES.md` §32, §33). New
**`Supplier`** model in `apps/suppliers` (real implementation replacing the scaffold) — `name`
(required), `company`/`phone`/`email`/`address`/`gstin`/`payment_terms`/`notes` all optional. New
**`apps/purchases`**: `PurchaseOrder` (`supplier` FK `PROTECT`, `status`
`DRAFT→ORDERED→PARTIALLY_RECEIVED→RECEIVED`, `CANCELLED` reachable from the first three,
`reference`/`invoice_number`/`note`, `subtotal`/`discount_total`/`tax_total`/`grand_total` derived
— written only by **`PurchaseTotalsService.recalculate`**, same shape as `SalesTotalsService`;
`amount_paid`/`balance_due` computed from `PurchaseOrderPayment` rows), `PurchaseOrderLine`
(`variant` FK `PROTECT`, `quantity_ordered`/`quantity_received`, `unit_price`/`tax_rate` always
client-supplied — not snapshotted from the catalog, since a purchase price is what the supplier
quoted — `discount_amount`), `PurchaseOrderLineUnit` (`line` FK `PROTECT` + `serialized_unit`
`OneToOne` `PROTECT`, links a received unit back to its PO line for cost-basis traceability,
mirrors `SaleLineUnit`), `PurchaseOrderPayment` (a standalone model, **not** a reuse of
`billing.Payment` — that model's `sale` FK is hard-required; reuses the same method/type
vocabulary). **`ReceiveStockService.receive`** (`apps/purchases/services.py`) is the only path
that creates units for a PO — one atomic call per receiving session (`{line, quantity, location}`
entries, validated against `quantity_pending` up front, all-or-nothing), each unit created via the
same `SerializedInventoryService.generate` allocator every other unit-creation path uses, landing
directly `AVAILABLE` with `purchase_cost` set from the line's `unit_price` (§33: "Assign Location →
Mark Units Available"), updating `PurchaseOrder.status` to `PARTIALLY_RECEIVED`/`RECEIVED`. New
RBAC codename **`purchases.manage`** added (ADR-017 — the three codenames reserved since Phase 1
covered view/receive/supplier-manage but nothing covered creating or editing a PO itself; falls out
to Admin/Manager automatically via the existing `_ALL - {...}` role formula, Warehouse keeps only
`purchases.view`/`purchases_receiving`, Cashier holds none of the purchases codenames). API:
**`/api/v1/suppliers/`** (standard CRUD, reads `purchases.view`, writes `suppliers.manage`, delete
blocked while the supplier has purchase-order history) and **`/api/v1/purchases/orders/`**
(list/retrieve `purchases.view`; create with a nested `lines` convenience list `purchases.manage`;
`lines/`/`lines/{id}/` add/edit/remove only while `DRAFT`; `place/` `DRAFT→ORDERED`; `receive/`
`purchases_receiving`; `payments/` record a payment/refund; `cancel/` from
`DRAFT`/`ORDERED`/`PARTIALLY_RECEIVED`, does not reverse already-received units — all
`purchases.manage` except `receive/`). Frontend: new `frontend/src/features/suppliers/`
(`SuppliersPage` list + inline create, `SupplierDetailPage` profile/aggregates/order-history —
structurally identical to Phase 11 Customers) and `frontend/src/features/purchases/`
(`PurchaseOrdersPage` list, `NewPurchaseOrderPage` build-a-line-list-then-submit form with unit
price/tax rate pre-filled from the variant's `effective_purchase_price`/`effective_tax_rate`,
`PurchaseOrderDetailPage` with place/receive-link/cancel/record-payment actions, `ReceiveStockPage`
— sourced from a purchase order's own pending lines, unlike Phase 5's bulk-generate wizard which
is sourced from one manually-chosen variant and quantity) — replacing the three Phase 0 stub
routes at `/purchases/suppliers`, `/purchases/orders`, `/purchases/receive` (nav entries already
existed, gated on `purchases.view`/`purchases_receiving`, unchanged). `seed_demo_data` gains one
demo `Supplier` + one partially-received `PurchaseOrder` (20 ordered, 15 received). Verified:
`ruff check` + full `manage.py test` (325 tests, 22 new) clean; `eslint` + `tsc -b && vite build`
clean; a full Chrome pass via the Claude-in-Chrome MCP on the live dev server — created a supplier,
created a PO with a line (unit price/tax rate auto-filled), placed it, recorded a partial payment
(balance due updated correctly), hit a real bug attempting to receive stock (below), then completed
a full create→place→receive→verify cycle on a clean variant: units created `AVAILABLE` at the
chosen location with `purchase_cost` set from the line's `unit_price`, `PurchaseOrderLineUnit`
links confirmed via the Django shell, status auto-flipped to `RECEIVED`, and the supplier detail
aggregates plus the orders list both reflected the change correctly. No console errors.

**Bug caught live (not fixed — pre-existing, outside this phase's scope):** receiving stock
against `HEX-MP-12X32-001` (variant id 14, `code='12X32'`) failed with a 500 —
`IntegrityError: duplicate key value violates unique constraint
"products_serializedunit_serial_number_key"` — because a *different* variant
(`HEX-DM-BLACK-001`, id 15, `code` now `'BLACK'`) already owned a unit serialed
`HX12X32-000003`, evidently generated back when that variant's `code` was still `'12X32'`
(`code` was edited afterward in earlier interactive testing; serial numbers are immutable once
issued per `docs/serialized-units.md`, so the old serial persists). `allocate_serial`'s uniqueness
guarantee (`apps/products/services/serial_numbers.py`) is a per-variant sequence counter, not a
globally-unique formatted string — two variants whose token collides (via a `code` edit after
serials were already issued under the old value) can produce the same `serial_number`, and
`create_unit` doesn't catch/retry on the resulting `IntegrityError`, so it surfaces as a 500
instead of a clean validation error. This is a Phase 3 design gap plus historical dev-data drift,
not something Phase 12 introduced or a defect in `ReceiveStockService` — every attempt rolled back
atomically and left the order/lines/payments fully consistent (confirmed via the Django shell
across several retries), so no data corruption resulted. Left for a future session: either make
the token derivation collision-proof (e.g. include the variant id) or have `create_unit`
retry-on-`IntegrityError` with the next sequence.

Previously: Phase 11 — Customers (ADR-016, `HEXAGARE_FEATURES.md` §29, §30). New
**`Customer`** model in `apps/customers` (real implementation replacing the scaffold) — `name`
(required), `phone`/`email`/`address`/`gstin`/`notes` (all optional regardless of type), `type`
(`REGISTERED`/`WALK_IN`, default `REGISTERED`) — one model for both a registered customer and a
lightweight walk-in; "registering" a walk-in later is just filling in more fields on the same row.
**`Sale.customer`** (new, `apps/sales`) is a nullable, `PROTECT` string FK to `customers.Customer`
— `null` is the true "no registration required" walk-in (§30, no `Customer` row at all), distinct
from a `Customer` row with `type=WALK_IN` (a name/phone kept on record without full registration).
Attaching/changing/clearing the customer on a sale is its own action, **`POST
/sales/{id}/customer/`** (`{"customer": <id>|null}`, gated by the existing `orders.manage`,
not tied to `sale.is_editable` since it's metadata not a cart/total change) — `SaleCreateSerializer`
also accepts `customer` at creation. **`apps/customers/services.py`** computes purchase-history
aggregates on read (not cached columns, same pattern as `Sale.amount_paid`): `total_purchases`
(sum of `grand_total` across the customer's sales, excluding `DRAFT`/`CANCELLED`), `total_refunds`
(sum of `Return.refund_total` on those sales), `outstanding_amount` (sum of positive `balance_due`),
`serial_number_history` (every `SerializedUnit` ever sold to the customer, via
`sale_line_unit__sale_line__sale__customer`). API under `/api/v1/customers/`: standard CRUD
(`customers.view`/`customers.manage`, both reserved since Phase 1, held by Cashier/Manager/Admin,
not Warehouse — no `rbac.py` change), search on name/phone/email/gstin, `?type=` filter,
`CustomerDetailSerializer` returns profile + the three aggregates + light order history + serial
history in one response (no separate paginated endpoint per section, matching this project's
scale). Deletion is blocked while the customer has any sales history (`ValidationError`, same
guard style as `inventory.Location`), not a raw FK `ProtectedError`. Frontend: new
`frontend/src/features/customers/` — `CustomersPage` (list + inline create), `CustomerDetailPage`
(profile view/edit, the three stat tiles, order history table, purchased-serial-numbers table),
`CustomerPicker` (search-existing-or-add-walk-in, reused inside New Bill) — replacing the Phase 0
stub route at `/customers` (nav entry already existed, gated on `customers.view`, unchanged). New
Bill (`frontend/src/features/sales/new-bill-page.tsx`) gained a "Customer" card using
`CustomerPicker`; Orders list gained a Customer column. Verified: `ruff check` + full `manage.py
test` (303 tests, 19 new) clean; `eslint` + `tsc -b && vite build` clean; a full Chrome pass via
the Claude-in-Chrome MCP on the live dev server — created a registered customer via the full form,
searched by phone, walk-in-quick-added "Priya Verma" from inside New Bill, added a product,
completed the sale (₹1,180 cash), then confirmed on her Customer detail page: Total purchases
₹1,180, order history showing the COMPLETED order with ₹0 balance due, and the purchased serial
number listed with status SOLD and a working link to its unit detail page; Orders list showed the
new Customer column correctly (populated for the new sale, "—" for older unlinked sales). No
console errors beyond a pre-existing, unrelated React Router future-flag warning.

Previously: Phase 10 — Returns (ADR-015, `HEXAGARE_FEATURES.md` §31, §59). New **`Return`**/
**`ReturnUnit`** models added to `apps/billing` (not a new app — same reasoning as `Payment`/
`Invoice`; no domain app named "returns" exists in the fixed list). `Return` — `sale` FK, `reason`,
`note`, `created_by`; `refund_total` is a computed property (sum of `ReturnUnit.refund_amount`),
not stored. `ReturnUnit` — `return_record` FK (named to dodge the `return` keyword),
`sale_line_unit` FK (resolves the original line), `serialized_unit` FK (**plain**, not
`OneToOneField` — contrast `SaleLineUnit` — a unit can be sold and returned more than once over its
lifetime), `refund_amount`, `condition` (`PENDING`→`RESELLABLE`/`DAMAGED`), `inspected_at`,
`inspected_by`. **`apps/billing/services/returns.py:ReturnService`**: `resolve(code)` (read-only
preview — unit + originating `Sale`/`SaleLine` + a suggested refund amount, an even split of
`SaleLine.net_amount` across its units since there's no per-unit discount breakdown); `create(entries,
reason, refund_method, note, actor)` (one atomic call — every scanned code must resolve to a `SOLD`
unit on the **same** `Sale`; each unit moves `SOLD→RETURNED` via the existing
`SerializedInventoryService.return_unit()`, one `Payment` row `type=REFUND` is created for the
summed total — one refund method per return, not split-tender); `inspect(return_unit, condition,
actor)` (resolves a `PENDING` unit to `RESELLABLE` — `SerializedInventoryService.restore()` → back
to `AVAILABLE` — or `DAMAGED` — `.damage()`; both methods already existed, no changes needed, and
`ALLOWED_TRANSITIONS` already allowed both edges). **Channel-agnostic by construction** — resolution
goes through `SerializedUnit.sale_line_unit`, which every `SOLD` unit has whether it was sold
through the offline POS checkout or the Amazon CSV importer (Phase 9); this is deliberately how
Phase 9's gap (a CSV trying to reverse an already-finalized order is logged as a failed row rather
than reversed) gets closed — an operator now processes it here by scanning the serial, regardless
of channel. `Sale.status` is **not** written by this flow (a sale can have some units returned and
others still `SOLD`). API under `/api/v1/billing/returns/`: `resolve/` GET preview, list/retrieve/
create, `{id}/units/{unit_id}/inspect/` POST — all gated by the single existing `returns` codename
(reserved since Phase 1, held by Cashier/Manager/Admin, not Warehouse; no `rbac.py` change).
Frontend: new `frontend/src/features/returns/` — `ReturnsPage` (list), `NewReturnPage`
(scan/type-code flow building a list of units before submitting, reusing `features/sales`'s
`CameraScanPanel`), `ReturnDetailPage` (per-unit "Mark resellable"/"Mark damaged" actions) —
replacing the Phase 0 stub route at `/sales/returns` (nav entry already existed, gated on
`returns`, unchanged). Verified: `ruff check` + full `manage.py test` (284 tests, 11 new) clean;
`eslint` + `tsc -b && vite build` clean; New Bill / Returns pages exercised live via the
Claude-in-Chrome MCP (start bill → add unit → totals correct; Returns list empty state renders) —
Chrome automation was paused by the user mid-verification before the return/inspect round-trip
itself was driven through the browser, so that last leg rests on the passing backend test suite
(`apps/billing/tests/test_returns.py`, including the Amazon-origin case) rather than a live click-
through.

Previously: Phase 9 — Amazon Integration: CSV Import (ADR-014, `HEXAGARE_FEATURES.md`
§20–22). New **`apps.integrations`** app gets an `amazon` subpackage
(`apps/integrations/amazon/{models,sources,services,tasks,serializers,views,urls,admin}.py`; thin
re-export shims at `apps/integrations/{models,admin,tasks}.py` since Django's app registry /
`admin.autodiscover()` / Celery's `autodiscover_tasks()` all look for `<app>.<module>`, not a
nested subpackage — migrations stay at the conventional `apps/integrations/migrations/`).
**`AmazonOrderSource`** (`sources.py`) is the abstraction; `CSVAmazonOrderSource` is the only
implementation, one row per order line (`order_id`/`order_date`/`order_status`/`amazon_sku`/
`quantity`/`selling_price` required, `gst_amount`/`refund_amount`/six fee columns optional).
**`AmazonOrderImportService.run`** (`services/importer.py`) groups rows by `order_id` and imports
each order in its own `transaction.atomic()` — one bad order (unknown SKU, insufficient stock,
conflicting statuses) never blocks the rest of the file. For an order whose `order_status` means
stock left the business (Shipped/In transit/Delivered/Completed), it draws `quantity` `AVAILABLE`
units FIFO from the `amazon` `Location` and moves each through `SerializedInventoryService`
(`AVAILABLE → RESERVED → SOLD`, both calls — no direct edge) binding a `SaleLineUnit` itself —
**deliberately bypassing `SaleUnitService`/`CompleteSaleService`** (ADR-014 point 1): an imported
order already happened, Amazon issues its own invoice, so no `Payment`/`Invoice` is created.
Idempotent: `Sale` keyed `(sales_channel, external_reference)`, `AmazonOrderSettlement` on `(sale,
sku)`; an order that hasn't sold units is fully rebuilt on re-import, one that has is
**finalized** — re-import only advances `Sale.status` forward along the happy path, a CSV trying
to move it to CANCELLED/RETURNED/REFUNDED is logged as a failed order rather than silently
mismatching unreversed units (Phase 10's job). New models: **`AmazonSkuMapping`** (amazon_sku
unique → variant, auto-created on an exact SKU match), **`AmazonFeeConfig`** (fee name/type/value/
channel/optional category-or-product scope/effective date range — section 22's configurable fee
structure, consulted only when a CSV fee column is blank; CSV value always wins),
**`AmazonOrderSettlement`** (per `(sale, sku)` — selling_price/gst_amount/taxable_value + the six
fee columns + refund_amount, computed `amazon_fees_total`/`settlement_amount`/`net_revenue`/
`product_cost`/`net_profit` matching section 21's worked example), **`AmazonImportBatch`**
(PENDING→PROCESSING→READY/PARTIAL/FAILED, counts, `error_log` JSON). API under
`/api/v1/integrations/amazon/`: `imports/` POST (multipart upload, enqueues
`tasks.py:import_amazon_orders` via `transaction.on_commit`) + GET history/detail; `sku-mappings/`
+ `fee-config/` full CRUD; `settlements/` read-only (`?sale=`) — all gated by the single existing
`integrations.amazon` codename (reserved since Phase 1, held by Admin/Manager only, no `rbac.py`
change). Frontend: new `frontend/src/features/integrations/` — `AmazonImportPage` (upload + live
poll of the just-created batch), `AmazonImportHistoryPage` (list with expand-to-see-`error_log`
rows), `AmazonFeeSettingsPage`, `AmazonSkuMappingPage` (variant picker reuses Phase 8's
`variantsApi.search()`) — all four lazy-loaded as one chunk (ADR-011 code-split, most users never
touch this) behind a new "Integrations" nav group in `nav.ts`. `seed_demo_data` gains one
`AmazonSkuMapping` + one channel-wide `AmazonFeeConfig` (15% referral). `docs/amazon-order-import.md`
fully written (CSV format, status mapping, idempotency/finalization rules, fee fallback);
`docs/domain-model.md` Integrations section filled in. Verified: `ruff check` + full `manage.py
test` (273 tests, 29 new) clean; `eslint` + `tsc -b && vite build` clean (new lazy chunk confirmed
separate from the main bundle); a full Chrome pass via the Claude-in-Chrome MCP on the live dev
server — uploaded a 2-row demo CSV (one importable, one bad-SKU row), watched it go
PENDING→PARTIAL with the bad row surfaced in `error_log`; created/activated/deleted a SKU mapping;
created a category-scoped fixed-amount fee rule and confirmed it listed correctly.

**Next up:** Phase 18 — AWS Deployment (see `HEXAGARE_BUILD_PROMPTS.md`).
**Completed phases:** Phase 0, Phase 1, Phase 2, Phase 3, Phase 4, Phase 5, Phase 6, Phase 7, Phase 8, Phase 9, Phase 10, Phase 11, Phase 12, Phase 13, Phase 14, Phase 15, Phase 16, Phase 17.
**Notes / deviations from the plan:** Phase 17: (125) **No new RBAC codenames** — unlike every
prior phase introducing a new resource, `settings.manage`/`users.manage`/`audit.view` were all
three already reserved since Phase 1, confirmed by grepping `rbac.py` before writing any code.
(126) **`BusinessSettings` fields are *overrides*, not the settings themselves** — a blank
`sku_prefix`/`serial_prefix`/`serial_padding`/`invoice_prefix`/`invoice_padding` means "keep using
the env-backed `HEXAGARE_*` Django setting," never a hardcoded fallback string baked into the
service layer; this was a deliberate design choice (not spelled out in HEXAGARE_FEATURES.md §49-52)
so the existing `@override_settings(HEXAGARE_SKU_PREFIX=...)`-style tests across `apps.products`/
`apps.billing` keep working against a fresh, all-blank `BusinessSettings` row without any test
changes. (127) **A single `AuditLogEntry.Action` value sometimes covers several §53 list items** —
e.g. "Variant modification"/"SKU modification"/"Price changes" all collapse onto `product.updated`
since they're the same underlying model's field diff, distinguished by *which* field changed in
`changes`, not by a separate action code per phrase in the feature list; see ADR-020 point 2 for
the full reasoning. (128) **"Invoice modification"/"Invoice cancellation" (also listed in §53) are
not wired up** — no such feature exists anywhere in the app (an `Invoice` is an immutable
point-in-time snapshot once created, per its own Phase 8 docstring, and a `COMPLETED` sale — the
only kind with an invoice — can't be cancelled); this is a pre-existing gap in the domain model, not
something this phase should invent a mutation path for just to have something to log. (129) **The
backend image needed a real dependency add** (`postgresql-client-17`, `backend/hexagare/Dockerfile`)
for the manual-backup feature to actually function — caught by testing `pg_dump --version` inside
the container before writing the Celery task, not after; the base `python:3.12-slim` image turned
out to already be Debian trixie (not bookworm), which ships a version-matched `postgresql-client-17`
natively, so no PGDG apt repo was needed (an earlier attempt to add one failed on a
trixie-vs-bookworm package-dependency conflict, reverted in favor of the simpler one-line fix).
(130) 401→429 backend tests (28 new, `apps/accounts/tests/test_administration.py` — see the Status
section above for the full breakdown). `ruff check` clean; `python manage.py spectacular
--fail-on-warn` surfaced no new warnings, only the same 5 pre-existing path-param ones (Phase 8 note
69's class). (131) **Two real bugs were caught and fixed this phase** (not pre-existing) — see the
Status section above for both: `UserAdminCreateSerializer.role` needed `write_only=True` (a
required, non-`write_only` `ChoiceField` with no matching model attribute crashes DRF's response
serialization rather than silently skipping, unlike a `required=False` field), and
`BusinessSettingsView.perform_update`'s audit diff needed `updated_at`/`updated_by` excluded (both
always differ on every save, so every settings-update log entry carried a meaningless diff line
alongside the real one). (132) **Chrome DevTools MCP not connected** — verified live via the
Claude-in-Chrome MCP instead: two full edit→save→diff round trips on Business Settings (the second
confirming bug (131)'s fix), an inline user role change, the Roles & Permissions matrix compared
directly against `rbac.py`, two real (unmocked) `pg_dump` backups triggered and one downloaded
successfully, and a full Cashier-login degraded-access pass across all five new pages. (133) **One
environment-only observation, not a regression:** `BackupsPage`'s pending-job poll
(`useBackups`'s `refetchInterval`) never visibly re-fired inside the automated browser tab despite
the underlying task finishing in under a second server-side (confirmed via the Celery worker log
and a fresh page reload showing the correct final status immediately) — the same tab produced
repeated CDP screenshot-timeout warnings throughout the session, pointing at Chrome's
background-tab timer throttling in this specific automation environment rather than a bug in the
polling code, which is the same `refetchInterval` pattern already relied on (and previously
verified working) by `useReportExportStatus`/the label-batches list.
**Doc-hygiene note (Phase 16, retained for history):** these two lines had been left
stale at "Next up: Phase 14 / Completed: ...Phase 13" since before Phase 14 started — Phase 14 and
15 both finished (see their **Status**/**Previously** write-ups above) without updating them. Fixed
here; `docs/domain-model.md`'s "Reports / Notifications" section had the same staleness (still read
"Not yet built (later phases). Scaffold apps only." after both shipped) and was filled in for real
in the same pass — see the new "Reports / Exports", "Dashboard widgets" and "Notifications"
sections there.
Phase 13: (118) **No new RBAC codename was added** — unlike
every prior phase that introduced a new resource, `expenses.manage`/`finance.view` were already
both reserved since Phase 1, and (per ADR-018) `expenses.manage` alone gates the whole `Expense`
resource including reads, matching how `nav.ts` had already gated the Expenses link before this
phase touched it. (119) **`FinanceService` sums a manually logged `Expense` and the matching
`AmazonOrderSettlement` column into the same bucket** rather than treating them as mutually
exclusive — a deliberate simplification (ADR-018 point 3): double-entry is possible if an operator
logs an expense for a cost Amazon's settlement already captured, and this phase doesn't add a
flag to prevent that. (120) **GST/discounts/refunds are reported but never subtracted in the
profit waterfall** — `Sale.subtotal` is already the post-discount, GST-exclusive "Sales Revenue"
§36's diagram starts from, so subtracting `discounts` again would double-count it; confirmed via
`test_refunds_are_reported_but_not_subtracted_from_net_profit`. (121) **Per-serial profit only
apportions Amazon settlement fee columns for an Amazon-channel sale** — an offline-sold unit's
"Profit" card shows ₹0.00 for Amazon fees/courier/advertising/other charges (there is no per-unit
attribution for those on an offline sale; only aggregate `Expense` rows capture them at the
summary level). (122) 325→349 backend tests (24 new:
`apps/expenses/tests/{test_api,test_services}.py`, the latter built on a real
`CompleteSaleService` checkout *and* a real `AmazonOrderImportService.run` import — same
"exercise the actual service, don't hand-build totals" convention as `apps.customers.tests.
test_services` — covering the purchase-cost-vs-fallback branch, expense-bucket mapping, date-range
exclusion, channel filtering, draft/cancelled exclusion, Amazon settlement fee flow-through, both
online and offline per-serial profit, the never-sold-unit rejection, and the refund-is-reported-
not-subtracted case). `ruff check` clean; `python manage.py spectacular --fail-on-warn` needed no
new `ENUM_NAME_OVERRIDES` entry (`Expense.category` didn't collide with anything) but did need a
class-level `serializer_class` default plus `@extend_schema(responses=...)` on `FinanceViewSet`'s
three actions — it has no `queryset` (every action computes its response from `FinanceService`,
not a model), which spectacular treated as a hard error, not just a warning, until fixed; the
resulting `unit_id` path-param warning is left unannotated, same pre-existing class as
`SaleViewSet`'s `line_id`/`unit_id` (Phase 8 note 69). (123) `seed_demo_data` gains a new
`_seed_expenses` step — four demo `Expense` rows keyed on `(category, note)` for idempotency (no
natural business key exists otherwise), pushing `Expense.objects.count()` to 4;
`apps/common/tests/test_seed_demo_data.py`'s `test_is_idempotent` gained a matching assertion,
same as every phase that adds to the seed data. (124) Two bugs caught live via the
Claude-in-Chrome MCP — one fixed (a timezone-conversion off-by-one in this phase's own new default
-date logic, `toISOString()` vs. the viewer's local calendar), one left for a future session (nav
permission filtering has never actually been wired up, across every phase, since `sidebar.tsx` was
written in Phase 1) — see the Status section above for the full writeup of both.
Phase 12: (107) **New RBAC codename `purchases.manage`**
added (ADR-017) — the three codenames reserved since Phase 1 (`purchases.view`,
`purchases_receiving`, `suppliers.manage`) left a gap: nothing gated creating or editing a
purchase order itself, unlike every other domain's `.view`/`.manage` pair. User-confirmed decision
before implementation (see the Phase 12 planning exchange); falls out to Admin/Manager
automatically via the existing `_ALL - {"users.manage", "settings.manage"}` formula, no other
role-table edit needed. (108) **`PurchaseOrder` has a `DRAFT` status mirroring `Sale.is_editable`
exactly** (also a user-confirmed decision) — lines are freely editable only while `DRAFT`; a
`place/` action (`DRAFT→ORDERED`) locks them, matching `SaleLine`'s ADR-012 shape rather than the
simpler "starts at ORDERED" alternative considered in planning. (109) **`PurchaseOrderPayment` is
a standalone model in `apps.purchases`, not a reuse of `apps.billing.Payment`** (also user-
confirmed) — `billing.Payment.sale` is a hard-required `PROTECT` FK to `Sale`; extending it to
also cover purchase orders would touch a tested, unrelated app's core model for no shared benefit,
and `apps.purchases` has no reason to depend on `apps.billing`. Reuses the same method/type
vocabulary (Cash/UPI/Card/Bank transfer/Credit; Payment/Refund) as an independently-owned model.
(110) **`PurchaseOrderLineUnit` lives in `apps.purchases`, not as a FK on `SerializedUnit`** —
mirrors `apps.sales.models.SaleLineUnit`'s placement, keeping the cross-app reference
one-directional (`apps.products` never imports `apps.purchases`); `SerializedUnit.purchase_cost`
(added in Phase 4, unused until now) is the field `ReceiveStockService` actually writes for
cost-basis, the link row is purely for "which PO did this unit come from" traceability. (111)
**API mounted at two new top-level prefixes, `/api/v1/suppliers/` and `/api/v1/purchases/`**
(not `/api/v1/purchases/suppliers/` nested under one prefix) — one `include()` per app, matching
the "one include() per domain app" convention in `hexagare/urls.py`'s header comment; the nested
`/purchases/suppliers` URL only exists as a **frontend** route (`nav.ts` already used that path).
(112) **`ReceiveStockService.receive` validates every `{line, quantity, location}` entry's
`quantity` against `line.quantity_pending` up front**, before generating any unit — a bad entry in
a multi-line receiving call fails the whole request atomically rather than partially receiving
some lines and not others. (113) **A cancelled `PurchaseOrder` never reverses units already
received** — same non-reversal stance `Sale.cancel` takes toward already-`SOLD` units (only
`RESERVED` ones get released); `CANCELLED` is reachable from `DRAFT`/`ORDERED`/
`PARTIALLY_RECEIVED`, marking no more receiving/editing will happen, not undoing what already did.
(114) **A real bug was caught live via the Claude-in-Chrome MCP** during Chrome verification (see
the Status section above for the full writeup) — receiving stock against a variant whose `code`
field had been edited after serials were already issued under the old value produced a
cross-variant `serial_number` collision (a Phase 3 design gap: `allocate_serial`'s per-variant
sequence counter doesn't guarantee the *formatted string* is globally unique, and `create_unit`
doesn't catch/retry the resulting `IntegrityError`), surfacing as a 500 instead of a clean
validation error. **Not fixed this phase** — it's Phase 3 code, and every attempt rolled back
atomically with no data corruption (confirmed via the Django shell); noted for a future session
rather than expanding this phase's scope into `apps.products`. (115) 303→325 backend tests (22
new: `apps/suppliers/tests/test_api.py` covering CRUD/search/RBAC/delete-guard/aggregates,
`apps/purchases/tests/test_api.py` covering create-with-nested-lines/line-lock-after-place/
place-requires-a-line/receive-stock partial-then-full/receive-more-than-pending-rejected/
cannot-receive-a-draft-order/payment-and-balance-due/cancel-from-ordered/cancel-from-received-
rejected/RBAC including a directly-granted-permission test for the `purchases.manage` vs.
`purchases_receiving` split, since every seed role holding one also holds the other). `ruff check`
clean; `python manage.py spectacular --fail-on-warn` needed one new `ENUM_NAME_OVERRIDES` entry
(`PurchaseOrderStatusEnum`) — `PurchaseOrderPayment.method`/`.type` deliberately did **not** get
new override entries — they resolve to the existing `PaymentMethodEnum`/`PaymentTypeEnum` names
from `apps.billing.Payment` by virtue of an identical `(value, label)` set, same reasoning as
`Invoice.status`/`LabelBatchStatusEnum` (Phase 8 note 69) — this was caught manually
(`--fail-on-warn` isn't part of `make lint`/CI, same as every prior phase). (116) `seed_demo_data` gains a new `_seed_suppliers_and_purchases` step —
one demo `Supplier` ("BrightPack Traders") and one `PurchaseOrder` against `HEX-MP-11X23-001`
(20 ordered, 15 received via a real `ReceiveStockService.receive` call, left `PARTIALLY_RECEIVED`
on purpose so the Purchases pages have both an in-progress and, after this phase's live Chrome
verification, a fully-`RECEIVED` order to look at). This pushed `SerializedUnit.objects.count()`
from 7 to 22 in the dev/demo database — `apps/common/tests/test_seed_demo_data.py`'s two hardcoded
counts (`test_creates_demo_users_and_catalog`, `test_is_idempotent`) were updated to match, same
as every phase that adds to the seed data. (117) Chrome DevTools MCP not connected — verified live
via the Claude-in-Chrome MCP: created a supplier, created a PO with a line (unit price/tax rate
correctly pre-filled from `effective_purchase_price`/`effective_tax_rate`), placed it, recorded a
partial payment (balance due recalculated correctly), hit the bug in note 114 on a
pre-existing-data variant, then completed a full create→place→receive→verify cycle on a clean
variant with no pre-existing data pollution — units landed `AVAILABLE` at the chosen location with
`purchase_cost` set correctly, `PurchaseOrderLineUnit` rows confirmed via the Django shell, PO
status auto-flipped to `RECEIVED`, and both the supplier detail page's aggregates and the Purchase
Orders list reflected everything correctly with no console errors.

Phase 11: (100) **`Sale.customer` is `on_delete=PROTECT`,
not `SET_NULL`** — deleting a customer with sales history is blocked at the API level
(`CustomerViewSet.perform_destroy` raises a friendly `ValidationError` before the FK constraint
would ever fire), same guard style as `inventory.Location` (Phase 4 note 40) rather than silently
orphaning historical sales. (101) **Editing a customer's full profile (address/GSTIN/notes) is
only available from the Customer detail page, not inline from the list** — the list row
(`CustomerListItem`) deliberately omits those fields (kept light for the table), so an inline
edit form seeded from a list row would `PATCH` blank values over them; the detail page always has
the full `CustomerDetailSerializer` payload to seed the edit form correctly. (102) **Attaching a
customer to a sale is not gated on `sale.is_editable`** (contrast `lines/`/`units/`, which require
`DRAFT`) — linking a customer is metadata, not a cart/total change, so it works on a `RESERVED`
(on-hold) or `COMPLETED` sale too; `SaleViewSet.set_customer` uses `get_object()`, not
`_editable_sale()`. (103) **`total_purchases` excludes `DRAFT` and `CANCELLED` sales only** — a
`RESERVED` (on-hold, partially paid) sale still counts, since real stock/money may already be
committed; this was a judgment call (not spelled out in HEXAGARE_FEATURES.md §29) rather than a
strict "must be fully paid" rule. (104) **No new `InventoryTransaction`/ledger changes** — this
phase is customer metadata + read-only aggregation, it does not touch the inventory ledger or the
`SerializedUnit` state machine at all. (105) 284→303 backend tests (19 new:
`apps/customers/tests/{test_api,test_services}.py` covering CRUD/search/type-filter/RBAC/
delete-guard and aggregate correctness built on a real `CompleteSaleService`/`ReturnService` flow
rather than hand-built totals; 4 more in `apps/sales/tests/test_sales_api.py` for the
`customer/` attach action). `ruff check` and `eslint`/`tsc -b && vite build` both clean;
`python manage.py spectacular --fail-on-warn` needed one new `ENUM_NAME_OVERRIDES` entry
(`CustomerTypeEnum`, `Customer.Type` collided with another field also named `type`) plus
`@extend_schema_field` on the five new `SerializerMethodField`s on `CustomerDetailSerializer` —
both fixed rather than left as new warnings, unlike the pre-existing `line_id`/`unit_id`/
`return_unit_id` path-param class (Phase 8 note 69) which stays unannotated to match precedent.
(106) Chrome DevTools MCP not connected — verified live via the Claude-in-Chrome MCP instead: full
round trip (create registered customer via the full form → search by phone → walk-in quick-add
from inside New Bill → add product → complete sale → customer detail page shows correct
aggregates/order history/serial history with a working link to the unit) plus the Orders list's
new Customer column, all exercised against the live dev server with no console errors beyond a
pre-existing unrelated React Router warning. Phase 10: (91) **`ReturnUnit.serialized_unit` is a plain
`ForeignKey`, not `OneToOneField`** (contrast `SaleLineUnit`) — a unit restored to `AVAILABLE`
after inspection can be sold and returned again later, so it may legitimately have more than one
`ReturnUnit` row over its lifetime; a `OneToOneField` would have blocked that on the second return.
(92) **The FK field on `ReturnUnit` pointing at `Return` is named `return_record`, not `return`** —
`return` is a Python keyword and Django's `fields.E001` also rejects a trailing-underscore
`return_` — so `return_record` (db column `return_record_id`) was used instead; the reverse
accessor is still the natural `Return.units`. (93) **No new `SerializedInventoryService` methods
were needed** — `.return_unit()` (`SOLD→RETURNED`), `.restore()` (`→AVAILABLE`) and `.damage()`
(`→DAMAGED`) already existed from Phase 4, and `SerializedUnit.ALLOWED_TRANSITIONS` already had
every edge this phase needed; `ReturnService` only orchestrates calls to them. (94) **A return is
one refund transaction against exactly one `Sale`** — `ReturnService.create` rejects a call whose
scanned codes resolve to more than one sale, and one summed `Payment` (`type=REFUND`) is created
per return rather than per unit or split across methods. (95) **`ReturnUnit.refund_amount`
defaults to an even split of the original line's `net_amount` across its bound units** (`SaleLine`
has no per-unit discount breakdown) **but is overridable per unit** at creation time — the frontend
pre-fills the suggested amount from `resolve/` and lets the cashier edit it before submitting,
matching HEXAGARE_FEATURES.md §31 listing "Refund amount" as its own field. (96) **`Sale.status` is
deliberately never written by this flow** — `Status.RETURNED`/`REFUNDED` (added in Phase 7 for
channel-status vocabulary) stay unused by this phase; a sale can have some units returned and
others still `SOLD`, so return state lives at the `Return`/`ReturnUnit` level instead
(`Return.sale` for the reverse lookup), not collapsed into one `Sale.status` value. (97)
**Channel-agnostic resolution closes a gap Phase 9 explicitly deferred** — `ReturnService` resolves
any `SOLD` unit's `SaleLineUnit` regardless of whether it was sold by the offline POS checkout or
the Amazon CSV importer, so an Amazon order a re-imported CSV can't reverse (Phase 9 note 82) is
now returnable manually by scanning its serial; covered by
`AmazonOriginReturnTests.test_a_unit_sold_via_amazon_import_can_be_returned`. (98) 273→284 backend
tests (11 new: `apps/billing/tests/test_returns.py` covering resolve/create/inspect, mismatched-sale
and not-sold rejections, double-inspection rejection, RBAC, and the Amazon-origin case). `ruff check`
and `eslint`/`tsc -b && vite build` both clean; `python manage.py spectacular --fail-on-warn` surfaced
one new warning (`return_unit_id` path param type undeclared) of the same pre-existing class as
`SaleViewSet`'s `line_id`/`unit_id` — not a gate per Phase 8 note 69, left unannotated to match.
(99) **Chrome verification was cut short mid-session by the user** ("don't use claude in chrome
until i tell you") after confirming New Bill's add-to-cart/totals and the Returns list's empty
state render correctly live — the create→refund→inspect round trip itself was not driven through
the browser this phase; it rests on the passing backend test suite instead. Resume a full
click-through (scan → resolve preview → create return → refund `Payment` appears → inspect
resellable/damaged → unit status changes) next session before treating the UI as fully verified.
(Phase 1 notes 1–12, Phase 2 notes 13–24, Phase 3 notes 25–34, Phase 4 notes 35–44 — see git history / earlier revisions of this file.) Phase 9: (79) **`AmazonFeeConfig` gained a `sales_channel` FK (§22's "applicable channel" field) even though only `AMAZON` exists today** — an explicit choice over leaving it implicit, so a second marketplace integration (Flipkart/Meesho) reusing this fee-config shape needs no migration, just new rows (ADR-014 point 6). (80) **The importer bypasses `SaleUnitService`/`CompleteSaleService` entirely** (ADR-014 point 1, resolving the gap ADR-013 explicitly flagged and deferred) — it calls `SerializedInventoryService.reserve()` then `.sell()` directly and writes `SaleLineUnit` itself, and creates **no `Payment`/`Invoice`** (Amazon issues its own invoice). `SerializedUnit.ALLOWED_TRANSITIONS` has no direct `AVAILABLE → SOLD` edge, so both calls are required even though the sale is already historical. (81) **Order-level, not batch-level, atomicity** — rows are grouped by `order_id`, each order is its own `transaction.atomic()`; a bad order lands in `AmazonImportBatch.error_log` and the rest of the file still imports. `run()` itself is deliberately *not* wrapped in an outer atomic. (82) **A "finalized" order (already sold units) only ever has its status advanced forward** along the pre-cancellation happy path on re-import; a CSV trying to move it to CANCELLED/RETURNED/REFUNDED is logged as a failed order rather than silently reversing units the importer has no way to un-sell — that reversal is Phase 10 Returns' job. An order that hasn't sold units yet is fully rebuilt (lines + settlement) on every re-import. (83) **Fee columns: CSV value always wins; `AmazonFeeConfig` is consulted only when a column is blank** — product-specific config beats category-specific beats channel-wide, narrowed to the row's `order_date`. (84) **CSV convention: `selling_price`/`gst_amount` are per-unit, the six fee/charge columns and `refund_amount` are line totals** (matching how Amazon's own reports usually present them) — documented precisely in `docs/amazon-order-import.md` since getting this backwards silently produces wrong money. (85) **Duplicate `(order_id, amazon_sku)` rows within one CSV are rejected** (that whole order fails) rather than the importer guessing how to merge quantities/fees across them. (86) **`apps.integrations` stays one Django app with an `amazon` subpackage**, not a new app — `apps/integrations/amazon/{models,sources,services,tasks,serializers,views,urls,admin}.py`, with thin re-export shims at `apps/integrations/{models,admin,tasks}.py` because Django's app registry / `admin.autodiscover()` / Celery's `autodiscover_tasks()` all resolve `<app>.<module>` directly, never a nested subpackage; migrations stay at the conventional `apps/integrations/migrations/`. A future channel integration is a sibling subpackage, not a new app. (87) **`integrations.amazon` (reserved since Phase 1) gates every endpoint here** — import, SKU mapping, fee config, and settlements alike; no `rbac.py` change, only Admin/Manager hold it today. (88) **`AmazonOrderSettlement`'s `settlements/` list endpoint has no dedicated frontend page this phase** — the build prompt's frontend list was CSV upload / import history / fee settings / SKU mapping, not a settlements viewer; the API exists for Phase 14 Reports to consume later. (89) 244→273 backend tests (29 new: `apps/integrations/amazon/tests/{test_sources,test_fees,test_importer,test_api}.py` covering CSV parsing, fee resolution/precedence, order-level atomicity/idempotency/finalization, SKU auto-mapping, and RBAC). Verified live via the Claude-in-Chrome MCP: uploaded a 2-row demo CSV (one importable Pending order, one unmapped-SKU order), batch went PENDING→PARTIAL with the bad row's exact error message surfaced in the expandable history row; **a bug was caught and fixed live** — the import-history table initially only fetched a row's status/counts once expanded (leaving every row blank until clicked) even though the list endpoint already returns them; fixed to read the list response directly and fetch the detail endpoint (for `error_log`) only on expand. **Also caught (not a code bug): the Celery worker container needed a restart to pick up the new task module** — `autodiscover_tasks()` only runs at process start, so a task added to an app that never had one before is invisible to an already-running worker until restarted; noted here for future phases in the same situation. SKU-mapping create/activate-toggle and fee-config create (percentage + fixed, channel-wide + category-scoped) all verified working; a stray click on a "Delete" button's native `confirm()` dialog froze that tab (a self-inflicted mistake, not a bug — closing the tab recovered it; both test rows were cleaned up via the Django shell instead). (90) **Post-completion addition (user-requested): a "Download sample CSV" button** on the Import page — a static `frontend/public/samples/amazon-orders-sample.csv` (3 rows: one full-fees Shipped order, one blank-fees Pending order to show the fallback, one Delivered order) using SKUs from `seed_demo_data`'s catalog so it imports cleanly against the demo DB out of the box; linked via a plain `<a download>` next to "Import history". Phase 8: (67) **`SaleLineUnit` rows created once a sale completes are a permanent record, never deleted** — Phase 10 (Returns) needs to resolve a sold serial back to its `Sale`/`SaleLine`. Rows for a still-`DRAFT` line *are* deleted on unit-remove/line-delete/cancel, each of which releases the unit first. (68) **`Invoice.sequence` is a plain integer column, not parsed from `invoice_number`** — allocation reads a `Max()` aggregate under the advisory lock, same shape as `SerializedUnit.sequence`/`allocate_serial`, rather than regex-parsing the formatted string (which was the first draft and is both slower and fragile). (69) **`Invoice.status`/`InvoiceDelivery.status` were NOT both given `ENUM_NAME_OVERRIDES` entries** — `Invoice.status`'s `(value, label)` set is byte-identical to `LabelBatch.status` (`PENDING`/`READY`/`FAILED`, same labels), and drf-spectacular's `--fail-on-warn` flags a *new* override name for an identical choice set as an ambiguous duplicate (picks one arbitrarily); `Invoice.status` deliberately reuses the existing `LabelBatchStatusEnum` name instead. `InvoiceDelivery.status` (`PENDING`/`SENT`/`FAILED`) *is* a distinct set and does have its own override. `--fail-on-warn` isn't part of `make lint`/CI — this was caught by running it manually, not a required gate. (70) **`SaleUnitService.add`'s "oldest available unit" pick takes no pre-lock** — a race between two cashiers is resolved safely by `SerializedInventoryService.reserve()`'s own row lock (the loser gets a clean `validation_error` to retry), same reasoning as ADR-004's SKU-suggestion race. (71) **The generic `POST /sales/{id}/lines/` endpoint (ADR-012) is completely unchanged** — sale completion enforces unit-backing (`quantity == units.count()`) at `CompleteSaleService.complete()`, not at line-mutation time, so a draft/quote line built without scanning stays valid until someone tries to sell it. (72) `frontend/src/features/products/api.ts` gained `variantsApi.search()` (`?search=&available=1`) for the POS product-search add — the only change to an existing frontend feature this phase. (73) Chrome DevTools MCP not connected — frontend verified via the Claude-in-Chrome MCP (full scan-add/search-add/split-payment/complete/PDF/cancel-releases flow against the live dev server). **(74) Post-review correction (caught via live manual testing, same phase, ADR-013 addendum): `CompleteSaleService.complete()` originally sold units and created the invoice as soon as ANY payment was recorded, regardless of amount — a ₹500 payment on a ₹5,499 sale marked the unit SOLD with a READY invoice showing a balance due. Fixed:** it now only completes once `sale.amount_paid >= sale.grand_total`; short of that, `Sale.status → RESERVED` ("on hold"), units stay `RESERVED`, no `Invoice` is created. `complete()` now also accepts a `RESERVED` sale (resuming with more payment), and a new `CompleteSaleService.record_payment()` handles settling more of an already-`COMPLETED` sale's receivable (e.g. paying back a `CREDIT` balance) without re-selling units. `CheckoutView` dispatches between the two based on the sale's current status — the frontend always calls the same `POST /billing/checkout/`. New `Sale.amount_paid`/`Sale.balance_due` properties (`apps.sales.models`) back this; `Invoice.amount_paid`/`balance_due` now delegate to them. (75) **New Bill supports resuming a `DRAFT` or `RESERVED` sale** via `/sales/new?sale=<id>` — full cart edit for `DRAFT`, payment-only (cart locked) for `RESERVED`. The Orders list links to this for any `DRAFT`/`RESERVED` row ("Resume" / "Collect payment") — previously Orders was fully read-only. (76) **A real camera scanner is now in New Bill**, not just a text input — `frontend/src/features/sales/camera-scan-panel.tsx`, lazy-loaded behind a toggle button next to the code field (same ADR-011 code-split reasoning as the standalone `/barcode/scan` route: ZXing stays out of New Bill's main chunk — confirmed via the production build, `use-barcode-scanner` lands in its own 458 KB chunk). (77) **Invoice detail page gained a settle-balance mini-form**, shown only when `balance_due > 0` on a completed invoice — posts to the same checkout endpoint, landing on `record_payment`. Under the corrected payment rule this is rarely reachable today (a `COMPLETED` sale's balance is 0 by construction) but matters once Phase 10 refunds can reopen a balance. (78) 235→244 backend tests (9 new: hold/resume/credit-settlement coverage in `apps/billing/tests/test_checkout.py` + `test_invoices.py`). Verified live via the Claude-in-Chrome MCP: partial payment leaves the unit `RESERVED` not `SOLD` (confirmed server-side too) and the sale `RESERVED` with `Bill on hold` banner; resuming from Orders → paying the rest → unit flips to `SOLD` and the invoice generates; Cancel bill works from a held sale (fixed — was accidentally gated to `DRAFT`-only in the first pass); camera-scan panel opens and gracefully shows "Camera is off" in the (camera-less) test environment. Phase 7: (62) **DRF's auto-generated `UniqueTogetherValidator`** (from `Sale`'s conditional `UniqueConstraint` on `(sales_channel, external_reference)`) would otherwise force `external_reference` to be present on every create even though it's optional — `SaleCreateSerializer.Meta.validators = []`, with a manual `validate()` doing the real uniqueness check instead. (63) **`external_reference` is a blank-default `CharField`, not `null=True`** (ruff `DJ001`) — the partial unique constraint's condition excludes the blank value (`~models.Q(external_reference="")`) rather than an `isnull` check. (64) **`SaleViewSet` deliberately omits `UpdateModelMixin`/`DestroyModelMixin`** — a sale is only ever changed via the `lines`/`cancel` actions, never a raw `PATCH`/`DELETE` on `/sales/{id}/`; `http_method_names` still lists `delete` since the `lines/{line_id}/` sub-action needs it, but no route binds `DELETE` to the sale resource itself. (65) **No RBAC role holds `sales.view` without `orders.manage`** (Cashier/Manager/Admin all have both) — the view-vs-manage split test grants `sales.view` directly via `Permission`/`OperationalPermission` rather than a seed role. (66) Chrome DevTools MCP not connected — frontend verified via the Claude-in-Chrome MCP (page load, console, network, both filters). Phase 6: (53) **New frontend deps:** `@zxing/browser` + `@zxing/library` (deps), `vite-plugin-pwa` (devDep). **Rebuild the Docker `frontend` image** (`docker compose build frontend` / `up --build`) — its anonymous `/app/node_modules` volume predates these packages, so the bind-mounted dev server can't resolve them until the image is rebuilt (host `npm run dev` / `build` are fine). (54) **`@zxing/browser` over html5-qrcode** (ADR-011) — headless decoder, so the scanner UI is plain design-system components rather than html5-qrcode's injected widget DOM/CSS. (55) **Camera needs a secure context** — `localhost` / HTTPS only; a phone hitting a bare `http://<LAN-IP>:5173` gets the "camera unavailable" state and must use manual entry. **Not a bug** — the fix is to make the phone's origin `localhost` via `adb reverse tcp:5173 tcp:5173` (then open `http://localhost:5173` on the phone) or an HTTPS tunnel; see `docs/architecture.md` → "Testing the scanner camera on a phone". No HTTPS was added to the Vite config. (56) **`getUserMedia` can hang indefinitely** on some mobile browsers when the camera can't be acquired; the hook's 15 s `START_TIMEOUT_MS` race resolves that to an `error` state ("The camera didn't start…") with Try-again, manual form still available. (57) **First code-split in the frontend** — `routes/router.tsx` `React.lazy(() => import("@/features/scanner"))` behind `<Suspense>`; factor a shared helper if more routes need it. (58) **`barcode.scan` gates the lookup, not the route** — `/barcode/scan` is only auth-gated (consistent with the rest of `router.tsx`); a 403 renders an explanatory card. (59) **`scripts/generate-pwa-icons.py`** (Pillow) is committed and regenerates `frontend/public/pwa-*.png` + `apple-touch-icon.png` + `favicon.ico`; Pillow is a one-off dev tool (system Python), not a frontend dependency. (60) **Chrome verification used the Claude-in-Chrome MCP** (Chrome DevTools MCP still not connected) — equivalent coverage: page load, console, network, scan→card flow, PWA SW/manifest. (61) Pre-existing `apps.accounts` password-reset test failure (Phase 3 note 30) still unaddressed — untouched by this frontend-only phase. Phase 5: (45) **`reportlab==4.4.3` added to `requirements.txt`** — rebuild all three backend-context images (`backend`, `celery-worker`, `celery-beat`; same Dockerfile, separate images). Pure-Python wheels, **no Dockerfile / system-package change** (the reason ReportLab was chosen over the build-prompt's WeasyPrint suggestion — see ADR-010). (46) **Starting serial / prefix from §10–11's UI is a read-only preview, not an input** (ADR-010) — `bulk_generate_units` reuses `allocate_serial`; `GET …/label-batches/next-serial/?variant=` previews without the lock. Operator-set start serials would need a new allocator mode + a new ADR. (47) **Barcode type: Code 128 only** — EAN-13/UPC (serial isn't valid data for them) and QR (extra dep) deferred; `LabelBatch.barcode_type` stored (default `code128`) so the set can grow without a migration. (48) **`render_label_pdf` does not retry** — on failure it records `status=FAILED` + `error_message` and returns; recovery is the manual `regenerate` action (matches §11 "Reprint / Generation history" and avoids Celery eager-retry sleeps in tests). (49) **`transaction.on_commit` enqueues the render** after the unit txn commits; tests use `self.captureOnCommitCallbacks(execute=True)` and **must run under `DJANGO_ENV=test`** (`make test` sets it) for `CELERY_TASK_ALWAYS_EAGER` — a bare `manage.py test` uses dev settings and leaves batches `PENDING`. (50) **`LabelBatch`/`LabelBatchItem` admin is view-only** (created via API only, immutable history), same stance as `SerializedUnit`. (51) Chrome DevTools MCP not connected — frontend verified manually (`eslint` + `tsc -b && vite build` clean; the full generate→poll→download/print→regenerate→history flow exercised against the live API over HTTP, plus RBAC 403s and all-or-nothing rollback). (52) Prior Phase 4 notes retained in git history. Phase 4: (35) **`.gitattributes` added + `backend/hexagare/entrypoint.sh` normalised to LF.** On this Windows checkout `core.autocrlf=true` gave `entrypoint.sh` CRLF endings, so the bind-mounted script broke `sh` inside the container (`set: Illegal option -`) — every `docker compose` command failed. `.gitattributes` pins `*.sh`/`*.py`/`Makefile` to `eol=lf`. (36) **Stale `hexagare_postgres_data` volume (PG 16) removed** — it predated this clone and is incompatible with the compose file's `postgres:17`; the DB is fully reconstructed by `migrate` + `seed_demo_data`, nothing of value lost. (37) **`create_unit` now writes to the inventory ledger** (`OPENING` `InventoryTransaction` + balance) via a *runtime* import of `InventoryService` inside the function — `apps.products` → `apps.inventory` only at call time, no module-load cycle. Migration `inventory/0003_backfill_opening_ledger` backfills one `OPENING` row per pre-existing unit and rebuilds the cache; pre-Phase-4 transitions are **not** reconstructed as individual ledger rows (they were made through the ledger-free path). (38) **`InventoryTransaction.status` is a plain `CharField`, not `choices`** — it carries a `SerializedUnit.Status` value but a cross-app `choices=` import at model-load is avoided; `ENUM_NAME_OVERRIDES` gains `StockTransferStatusEnum` + `InventoryTransactionKindEnum`. (39) **The plain `transition` endpoint keeps Phase 3 behaviour unchanged** (no ledger, no new guard) — the documented gap. `/inventory/overview/` is computed live from `SerializedUnit` rows (not from `InventoryBalance`) precisely so it stays correct across that gap; `rebuild_inventory_balances` is the resync. (40) **`Location` writes reuse `stock_adjustments`** rather than a new `inventory.manage` codename (Warehouse/Manager/Admin already hold it); `Location` delete is blocked while units or balances reference it. (41) **`seed_demo_data`** gains 3 `StockLevelPolicy` rows (one deliberately triggers a `low_stock` alert in dev) and runs `rebuild_balances()` at the end. (42) Chrome DevTools MCP not connected — frontend verified manually (`eslint` + `tsc -b && vite build` clean; open/scan/receive/cancel, overview matrix, drift banner and alerts exercised against the live API over HTTP). (43) Non-serialized "quantity inventory" (§17) is only **partially** covered: `InventoryService.adjust` + the `adjustments/` endpoint exist, but there is no dedicated quantity-stock UI — deferred. (44) **Nav "Serial Numbers" item + `/products/serial-numbers` route removed** — it rendered the exact same `SerializedUnitsPanel` as "Product Units" (`/products/units`); one entry now, keeping the clearer label and the route the unit-detail pages hang off. Prior phase notes: Phase 3: (25) **`python-barcode==0.15.1` added to `requirements.txt`** — all three backend-context images (`backend`, `celery-worker`, `celery-beat`) must be rebuilt (`docker compose build`), they are separate images from the same Dockerfile. (26) **`apps/inventory.Location` pulled forward from Phase 4** (ADR-007): minimal model + `post_migrate` seed + **read-only** API now; Phase 4 extends the app in place (adds `InventoryBalance`/`InventoryTransaction`/`InventoryService`, makes `Location` writable) — does not replace it. `products.0003` migration depends on `inventory.0001`. (27) **`SerializedUnitEvent`** added (ADR-008) — the unit's own append-only status history (rule 4 "History", §8 "Serial history"); it is *not* the Phase 4 `InventoryTransaction` ledger and models a different thing. (28) **Advisory-lock namespace `1001`** is now reserved for serial allocation — use a different constant for any future advisory lock. (29) **`SPECTACULAR_SETTINGS["ENUM_NAME_OVERRIDES"]`** added (`ProductStatusEnum`, `SerializedUnitStatusEnum`) — multiple `status` choice fields otherwise collide into hash-suffixed enum names and trip `--fail-on-warn`. (30) **Pre-existing test failure, not caused by this phase:** `apps.accounts.tests.test_auth … test_password_reset_request_sends_email_for_known_user` fails on a clean `phase-3` checkout too — the test calls the reset endpoint (which enqueues `send_password_reset_email.delay(...)`) without `@override_settings(CELERY_TASK_ALWAYS_EAGER=True)`, so `mail.outbox` stays empty. Left for an accounts-focused fix. (31) Phase 3 frontend is **read-only** (list + detail + barcode) per the prompt — no create/transition UI; single-unit create + `transition` endpoint exist on the API for tests/seed, bulk generation + label PDFs are Phase 5. (32) **`api/client.ts` `parse` option** added (`"json"` default / `"blob"`) so the detail page can fetch the JWT-protected barcode PNG as a blob (an `<img src>` can't send the bearer header); reusable for Phase 5 PDFs. (33) Chrome DevTools MCP not connected — frontend verified manually (SPA serves at `/products/units` and `/products/units/:id`; `eslint` + `tsc -b && vite build` clean; list/detail/barcode/lookup flows exercised via the live API over HTTP). (34) **Serial immutability hardened (post-review):** `SerializedUnit.save()` raises `ValueError` on any post-creation change to `variant`/`serial_number`/`sequence` (a serial must not drift from its variant); `transition_unit`'s `update_fields=[status,location,…]` writes skip the check (no extra query). The admin registers `SerializedUnit` + `SerializedUnitEvent` **view-only** (no add/change/delete) — the original admin left `variant`/`status`/`location` editable, which bypassed the state machine and let a unit's serial mismatch its variant. 130 backend tests. Phase 2 note text retained below for history: Phase 2: (13) **`Pillow==11.1.0` added to `requirements.txt`** for `ProductImage.image` — rebuild the backend image (`docker compose build backend`). (14) [superseded by note 23 / ADR-005] `Product` originally had no pricing columns; it now carries optional default pricing that variants inherit. (15) `apps/products/urls.py` uses **`SimpleRouter`, not `DefaultRouter`** — `ProductViewSet` sits at the app-root prefix and `DefaultRouter`'s API-root would collide with its list route. (16) A partial unique constraint on `(product, variant.code)` was **dropped** — DRF's `UniqueTogetherValidator` forced `code` required and can't express the blank-exempt condition; variant `code` is now an unconstrained SKU hint. (17) `LabelSize` seeding via `post_migrate` (`bootstrap.py`, guarded against a missing table) is beyond the prompt's literal "Locations/SalesChannels" wording — same reference-data pattern, Phase 5 needs it. See ADR-004. (18) SKU suggestion takes **no advisory lock** (contrast Phase 3 serials) — the `sku` unique constraint + `is_sku_available()` are the guard; a race yields a `validation_error` + retry. (19) Chrome DevTools MCP not connected — frontend verified manually (SPA serves, `tsc`/`eslint`/`vite build` clean; catalog CRUD + SKU-suggest + variant nested-attr + GST derivation + image upload exercised via the live API). (20) **Variant-scoped images** wired up (backend `ProductImage.variant` FK already existed): `ImageUploader` has an "Attach to" scope selector, groups the grid by scope, and re-assigns images between scopes; `VariantManager` shows a per-variant thumbnail strip. Backend unchanged; +2 API tests (variant round-trip, cross-product `variant` rejected). (21) **Image URLs are storage-relative** — serializers return `image.url` verbatim (absolute S3 URL in staging/prod, `/media/...` in dev), never `request.build_absolute_uri()` which under the Vite proxy yields the container host (`backend:8000`). `MEDIA_URL` is now `/media/` (leading slash) and the Vite dev proxy forwards `/media` to the backend alongside `/api`. (22) **`seed_demo_data` implemented** (`apps/common/management/commands/`) — the `make seed` command referenced since Phase 0 finally exists: idempotent, adds 4 demo users (`{admin,manager,cashier,warehouse}@hexagare.test` / `demo-Passw0rd!`, password+role realigned every run) and a demo catalog (Peripherals tree, Size/Colour/Switch attrs, 3 products × 2 variants); refuses under `DJANGO_ENV=staging`/`production` without `--force`. Minor known wart: `CategorySerializer.parent_name` is omitted (not `null`) for top-level categories — frontend already treats it as optional. (23) **Pricing moved to a product→variant inheritance model (ADR-005, migration `0002`).** `Product` gained optional `mrp`/`selling_price`/`purchase_price`/`tax_rate`; `ProductVariant`'s same columns are now nullable overrides (`NULL` inherits); read `variant.effective_*` / `base_price` / `gst_amount` / `discount_*`. The `ProductVariant.discount` column was **dropped** — discount is derived (`max(mrp − selling_price, 0)` + percent) on both `Product` and `ProductVariant`. A variant is rejected unless its effective `selling_price` and `mrp` resolve non-null; `selling_price > mrp` just clamps discount to 0. Phase 7 `SalesTotalsService` must use `effective_*`. (24) **Variant availability derives from product status (ADR-006, computed — no migration).** `ProductVariant.is_active` is per-variant intent; `effective_status` (a `Product.Status` value) and `is_available` are derived — `draft`/`inactive`/`discontinued` products override every variant to that status (discontinued reads `discontinued`, not `inactive`), only `active` products defer to `is_active`. `?available=1` filter on the variant list; `ProductListSerializer.available_variant_count` (`0` unless product active). Frontend shows `effective_status`, disables the per-variant Active toggle unless the product is active, and banners non-active products. 92 backend tests.

*(Claude Code: update this section — Status, Next up, Completed phases, Notes — every time a
phase is finished, per Phase G of the workflow above. Keep it to these four lines so it stays
easy to scan at the start of a session.)*