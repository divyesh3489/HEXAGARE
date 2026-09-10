# Hexagare — Claude Code Build Plan (Fresh Repo, Real Architecture)

Target architecture: the modular-monolith design in your CLAUDE.md (Django/DRF + Celery/Redis +
Postgres backend, React/Vite/TS frontend, Docker Compose locally, AWS in prod). This plan builds
that design from an empty repo, one domain at a time, backend + frontend together.

---

## How to use this file

1. Drop your CLAUDE.md (the one you pasted — use it as-is) into the new repo root. Claude Code
   reads it automatically every session — none of the prompts below re-explain conventions
   (response envelopes, RBAC pattern, ledger-only writes, Celery pattern, etc.) because your
   CLAUDE.md already documents them. That's the main token-saver here.
2. Your CLAUDE.md has a **mandatory plan → approval workflow**. Paste a phase prompt, read
   Claude Code's plan, reply `approved` (or `go ahead`) to let it build. If you trust a phase and
   want it to skip the pause, add *"Make the plan and implement it without waiting for approval"*
   to the end of that phase's prompt.
3. One phase = one Claude Code session. Commit after each phase (`git add -A && git commit -m
   "phase N: ..."`), then start a fresh session for the next phase.
4. Where a phase needs the original feature spec for field-level detail (`HEXAGARE_FEATURES.md`,
   from your earlier upload), the prompt names the exact line range to read — same reasoning as
   before, keeps Claude Code from re-reading the whole 2500-line file every time.
5. **Docs Claude Code expects to exist** (referenced as authoritative in your CLAUDE.md): create
   thin stubs for `docs/architecture.md`, `docs/domain-model.md`, `docs/decisions.md` (ADR log),
   `docs/serialized-units.md`, `docs/amazon-order-import.md` in Phase 0, and keep them updated as
   you go — each phase prompt below tells Claude Code to update the relevant doc/ADR when it makes
   a structural decision, so the docs stay authoritative instead of drifting from the code.
6. Phase 6 (barcode scanner) and any later UI-heavy phase ask for Chrome DevTools MCP
   verification, matching your CLAUDE.md's Phase 6 workflow — if you don't have that MCP tool
   connected yet, tell Claude Code to skip that step and verify manually instead.

---

## Phase 0 — Backend Infra Scaffold

```
Set up the backend per CLAUDE.md's Architecture section: Django project at
backend/hexagare, domain apps under backend/hexagare/apps/ — accounts,
products, inventory, sales, integrations, billing, customers, purchases,
suppliers, expenses, reports, notifications, common — each just
apps.py/__init__.py for now except common, which needs real content this
phase.

Build in common: the global DRF EXCEPTION_HANDLER
(apps.common.exceptions.api_exception_handler) producing
{"error": {"code","message","fields"?}}, StandardPagination
(apps/common/pagination.py) wrapping lists as {"data": [...], "meta":
{"count","next","previous"}} with page/page_size params (max 100), and
BinaryRenderer (apps/common/renderers.py) for raw binary responses
(barcode images, PDFs).

Settings: backend/hexagare/hexagare/settings/{base,development,staging,
production}.py, selected via DJANGO_ENV in settings/__init__.py.
django-environ for .env. django-storages + boto3 for S3 in
staging/production (DEFAULT_FILE_STORAGE conditional on USE_S3), local
MEDIA_ROOT volume in development. drf-spectacular wired at /api/schema/
and /api/docs/. All routes mounted under /api/v1/ in hexagare/urls.py.

Celery: hexagare/celery.py with autodiscover_tasks(), Redis as broker,
CELERY_TASK_ALWAYS_EAGER=True + CELERY_TASK_EAGER_PROPAGATES=True in test
settings.

Infra: Dockerfile for backend (gunicorn, migration entrypoint script),
docker-compose.yml running postgres, redis, backend, celery-worker,
celery-beat (frontend added in Phase 1). Makefile with: up, down, logs,
migrate, test, lint (ruff check), seed, backend-shell, frontend-shell —
matching the commands in CLAUDE.md exactly. .env.example with
DJANGO_SECRET_KEY, DJANGO_ENV, DATABASE_URL, REDIS_URL,
AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY/AWS_STORAGE_BUCKET_NAME/
AWS_S3_REGION_NAME, HEXAGARE_SKU_PREFIX (default HEX),
HEXAGARE_SERIAL_PREFIX (default HX), HEXAGARE_SERIAL_PADDING (default 6).

Docs: create docs/architecture.md, docs/domain-model.md,
docs/decisions.md (ADR log, start with ADR-001 "modular monolith over
microservices" and ADR-002 "SKU/pricing as columns on ProductVariant, not
standalone entities, for now"), docs/serialized-units.md,
docs/amazon-order-import.md as short stubs to be filled in as each domain
is built.

Make the plan and implement it without waiting for approval — this is
pure scaffolding with nothing to design-review yet.
```

---

## Phase 1 — Frontend Foundation + Accounts (Auth + RBAC)

**Read:** `HEXAGARE_FEATURES.md` lines 72-93 (section 2, for the permission areas list)

```
Two things this phase, backend then frontend:

Backend — apps/accounts: custom User model, JWT auth via
rest_framework_simplejwt (login/refresh/logout), apps/accounts/rbac.py
defining ROLE_PERMISSIONS (roles → permission-name sets: start with
Admin, Manager, Cashier, Warehouse — include placeholder codenames for
features not built yet, e.g. "pos", "returns", "stock_adjustments",
"purchases_receiving", per the permission areas listed in section 2 of
HEXAGARE_FEATURES.md, lines 72-93) materialized into Django
Group/Permission objects via ensure_role_groups(), wired to a post_migrate
hook. apps/accounts/permissions.py:HasOperationalPermission as the base
custom permission class other apps will extend. Password reset,
profile endpoint, login history model (for later audit use).

Frontend — bring frontend/ up to the CLAUDE.md target: add React Router,
TanStack Query, Zustand (auth store), Tailwind + shadcn/ui as the
component layer, a base app shell (sidebar/topbar) with routes stubbed
for each domain area, rebuild the existing serialized-units panel to use
the new fetch client conventions consistently. Add the login page wired
to the new auth endpoints, protected-route wrapper reading the Zustand
auth store.

Update docs/domain-model.md with the Accounts/RBAC section and
docs/decisions.md with an ADR for the role-permission model.
```

---

## Phase 2 — Catalog (Product / Variant / Attributes / SKU)

**Read:** lines 154-305 (sections 4-7)

```
Backend — apps/products (catalog part only, serialized units come next
phase): Category, Product, ProductVariant, ProductAttribute/
ProductAttributeValue (data-driven variant properties — size/color/
material as data, never product-specific columns), ProductImage,
LabelSize models per CLAUDE.md's documented shape (SKU is a unique column
on ProductVariant, pricing — mrp/selling_price/purchase_price/tax_rate —
are columns on ProductVariant, not separate models). apps/products/
services/sku.py: SKU auto-suggestion using HEXAGARE_SKU_PREFIX +
category/variant code + sequence, duplicate check, manually editable.
GST-inclusive pricing formula (taxable price + GST auto-derived) as a
model property — see section 5, read lines 187-242, for the exact
formula. DRF viewsets under apps/products/urls.py, permission classes
gated per-action via get_permissions().

Frontend: Category management, Product list/create/edit with image
upload (to S3 via the backend), variant management (multiple
sizes/colors per product) using ProductAttribute/Value, SKU field that
auto-suggests but stays editable.
```

---

## Phase 3 — Serialized Units + On-Demand Barcode

**Read:** lines 306-676 (sections 8-9, 12), 678-805 (sections 14-15)

```
Backend — apps/products (serialized units part): SerializedUnit model
with a required location FK (apps.inventory.Location, string FK to avoid
circular import), immutable serial number generated under a Postgres
advisory lock via apps/products/services/serial_numbers.py — format
<HEXAGARE_SERIAL_PREFIX><variant-code>-<zero-padded sequence>, e.g.
HXMP1123-000001, never reused. ALLOWED_TRANSITIONS state machine on the
model per the statuses/transitions in sections 14-15 (read lines 678-805).
Barcodes are Code128 renderings of the serial generated on demand via
BinaryRenderer — never stored as an image. A lookup service/endpoint that
takes a serial or scanned barcode and returns the full chain (unit → SKU
→ variant → product) in one response, per rule 4 of section 55.

Write docs/serialized-units.md documenting the serial format, advisory
lock reasoning, and the state machine — this doc is referenced as
authoritative by CLAUDE.md so keep it accurate.

Frontend: Product Unit list with status filter, serial search, a unit
detail view rendering the on-demand barcode image and full chain.
```

---

## Phase 4 — Inventory Ledger + SerializedInventoryService

**Read:** lines 807-923 (sections 16-18)

```
Backend — apps/inventory: Location model (seed rows Warehouse/Amazon/
Offline via a post_migrate hook in apps/inventory/bootstrap.py, kind
field for reporting only — never branch logic on location name) and
InventoryBalance as a read-cache, never written directly.
apps/inventory/services/ledger.py:InventoryService as the *only* writer —
every balance change produces an immutable InventoryTransaction row,
optionally tagged with a serialized_unit kwarg.

apps/products (or a shared services module): SerializedInventoryService
wrapping InventoryService + the SerializedUnit state machine — transfer/
sell/damage/lose/return, each locking the unit row and doing the status
transition + ledger transaction in one atomic block. This is the only
path allowed to change a serialized unit's status — the plain transition
endpoint from Phase 3 stays available for simple status-only changes but
must not touch the ledger (document this gap explicitly, it's
intentional, matching CLAUDE.md's note on this).

Low-stock/out-of-stock/overstock alerts computed from InventoryBalance.

Frontend: Inventory overview (stock by status/location computed live,
not from a stored counter), stock transfer flow (scan-based), alerts
panel.
```

---

## Phase 5 — Bulk Unit Generation + Label PDFs

**Read:** lines 397-575 (sections 10-11)

```
Backend: a bulk-generate endpoint (product+variant+quantity+starting
serial+location) that, in one atomic transaction, calls the serial number
service N times, creates N SerializedUnits via SerializedInventoryService,
then enqueues a Celery task (apps/products/tasks.py) to render the label
PDF (barcode + product/variant/SKU/serial text per the label content
fields in section 11) and upload it to S3 — commit the DB transaction
first, enqueue the task after, never hold the request open for PDF work
(per your Celery pattern in CLAUDE.md). All-or-nothing: if unit creation
fails, no PDF task is enqueued; if PDF generation fails, units still
exist and the PDF can be regenerated/reprinted from a label-generation
history table.

Frontend: Bulk Generate wizard (product → variant → quantity → starting
serial → location → generate), progress + result screen, PDF
download/print once the Celery task completes (poll or return a status
endpoint), reprint from history.
```

---

## Phase 6 — Barcode Scanner (Mobile PWA)

**Read:** lines 613-676 (section 13)

```
Frontend: a mobile-first scanner page using html5-qrcode or
@zxing/browser (camera access via getUserMedia), calling the lookup
endpoint from Phase 3 on scan and showing the unit detail card. Add PWA
manifest + service worker (vite-plugin-pwa) so this is installable on a
phone home screen. No new backend work — this phase is frontend-only.

Verify with Chrome DevTools MCP if connected: page loads, camera
permission prompt, console/network clean, scan → detail card renders.
Skip that verification step and confirm manually if the MCP isn't set up.
```

---

## Phase 7 — Sales Core

**Read:** lines 925-951 (section 19)

```
Backend — apps/sales: SalesChannel model (seed rows AMAZON/OFFLINE via
apps/sales/bootstrap.py post_migrate hook, extensible to new channels
with zero code changes — never hardcode a channel code in logic, per your
ADR-003), and a single generic Sale/SaleLine model covering every
channel (no per-channel schemas). apps/sales/services/totals.py:
SalesTotalsService as the only writer of Sale.subtotal/discount_total/
tax_total/grand_total — recalculates from lines under a row lock whenever
a line changes.

Frontend: an Orders list scaffold (channel filter, status) — full detail
view comes with billing in the next phase.
```

---

## Phase 8 — Billing: Payment / Invoice + POS Flow

**Read:** lines 1048-1298 (sections 23-28)

```
This is net-new — Payment, Invoice, and InvoiceDelivery don't exist yet
per your domain-model.md boundary. Backend — apps/billing: Invoice model
(fields per section 28), Payment model against a Sale, and the missing
link: wiring sale completion to the inventory ledger — on sale
completion, call SerializedInventoryService.sell() for each line's unit
(AVAILABLE/RESERVED → SOLD) inside the same atomic block as Invoice +
Payment creation + SalesTotalsService recalculation, per rule 7 (read
lines 2136-2153 of HEXAGARE_FEATURES.md). Enqueue a Celery task
(apps/billing/tasks.py) to render the invoice PDF and upload to S3 —
commit first, enqueue after. InvoiceDelivery tracks send status (used by
notifications in a later phase).

Update docs/domain-model.md's "Sales and billing" section now that this
boundary is implemented, and add an ADR if the reservation flow
(AVAILABLE→RESERVED on add-to-cart, RESERVED→SOLD on payment) needs any
schema decision beyond what's already documented.

Frontend: the POS / New Bill screen — scan or search adds units to a
cart (RESERVED via the API as items are added), running total from
SalesTotalsService, payment method selection, complete-sale button,
invoice view with download once the PDF task completes.
```

---

## Phase 9 — Amazon Integration (CSV Import)

**Read:** lines 952-1029 (sections 20-22)

```
Backend — apps/integrations/amazon: AmazonOrderSource abstraction
(sources.py) with a CSV implementation for now (SP-API stays
unimplemented — build the interface so a future adapter only needs to
implement AmazonOrderSource, per your existing pattern).
AmazonOrderImportService depends only on that interface. Idempotent
imports: Sale keyed on (sales_channel, external_reference),
AmazonOrderSettlement keyed on (sale, sku) holding Amazon-specific
per-line financials (fees, shipping, advertising, refunds, net revenue —
keep these off the generic Sale/SaleLine, same pattern for any future
channel-specific data). Runs via a Celery task
(apps/integrations/amazon/tasks.py), never inline on upload.
Configurable Amazon fee structure per section 22 (read lines 1030-1047)
since rates change over time.

Update docs/amazon-order-import.md with the CSV format expected and the
idempotency keys.

Frontend: CSV upload page, import history/status, Amazon fee settings
page, SKU mapping UI (Amazon SKU ↔ Hexagare SKU).
```

---

## Phase 10 — Returns

**Read:** lines 1351-1395 (section 31), 2412-2441 (section 59 example)

```
Backend: a returns endpoint using SerializedInventoryService.return()/
damage() (the "returns" permission codename already reserved in rbac.py —
check which roles currently have it before assuming Cashier can process
returns). Flow: scan barcode → resolve serial → find original Sale/
SaleLine → validate unit is SOLD → create Return record → refund via
Payment → unit status → RETURNED → inspection outcome branches to
AVAILABLE (resellable, via SerializedInventoryService) or DAMAGED.

Frontend: Returns flow (scan-based), returns list, inspection action
(resellable/damaged) on a returned unit.
```

---

## Phase 11 — Customers

**Read:** lines 1299-1350 (sections 29-30)

```
Backend — apps/customers: real implementation replacing the scaffold —
Customer model (registered + walk-in, minimal fields for walk-in), FK
from Sale, purchase-history lookup by customer.

Frontend: Customers list + detail with order/purchase history, walk-in
quick-add inside the POS screen from Phase 8.
```

---

## Phase 12 — Purchases + Suppliers

**Read:** lines 1396-1467 (sections 32-33)

```
Backend — apps/suppliers and apps/purchases: real implementations
replacing the scaffolds — Supplier model, PurchaseOrder model, a
"receive stock" flow (the "purchases_receiving" permission codename is
already reserved) that creates SerializedUnits via
SerializedInventoryService, linking each unit back to the purchase for
cost-basis tracking.

Frontend: Suppliers CRUD, Purchase Order create/list, Receive Stock
screen (reuse the bulk-generate UI pattern from Phase 5, sourced from a
PO instead of a manual form).
```

---

## Phase 13 — Expenses + Profit/Finance

**Read:** lines 1468-1584 (sections 34-37)

```
Backend — apps/expenses: real implementation — Expense model with
categories, and a finance service combining product cost + all expense
categories + Amazon fees (from Phase 9) into gross/net profit and margin,
plus per-serial-number profit tracking (section 37) using each unit's
purchase cost from Phase 12.

Frontend: Expenses CRUD, a Profit summary view (by period, by channel).
```

---

## Phase 14 — Reports + Exports

**Read:** lines 1585-1769 (sections 38-44)

```
Backend — apps/reports: real implementation — Sales, Inventory, Serial
Number, Serial Number History, Product, and Financial report endpoints
(date range + channel filters), CSV/Excel export per report type,
heavy exports routed through Celery (generate → upload to S3 → return a
download link) rather than blocking the request. Shared query logic in
one reports service module, not duplicated per report.

Frontend: Reports section with tabs per type, filters, export button.
```

---

## Phase 15 — Notifications (Email + WhatsApp)

**Read:** lines 1827-1850 (section 47). See the "WhatsApp Setup" section
below for the Meta Cloud API account setup itself.

```
Backend — apps/notifications: real implementation — Celery tasks
(tasks.py) sending the invoice PDF (S3 link from Phase 8) via email
(Django EmailMessage + SMTP/SendGrid) and via WhatsApp Cloud API
(WHATSAPP_PHONE_NUMBER_ID/WHATSAPP_ACCESS_TOKEN/
WHATSAPP_BUSINESS_ACCOUNT_ID env vars — isolate the Cloud API call in one
service class). Update InvoiceDelivery status (sent/failed) from Phase 8.
Low-stock alerts from Phase 4 routed through the same channel.

Frontend: "Send invoice" button on the invoice view (email/WhatsApp
options), delivery status shown per invoice.
```

---

## Phase 16 — Dashboard

**Read:** lines 94-153 (section 3)

```
Backend: aggregate endpoints per widget group (sales, inventory, finance,
analytics — separate endpoints, not one giant one, so each is
independently cacheable) per section 3.

Frontend: Dashboard page with those widget groups, a sales trend chart
and Amazon-vs-Offline comparison chart (recharts).
```

---

## Phase 17 — Settings + Security/Audit Polish

**Read:** lines 1903-2050 (sections 49-54)

```
Backend: a settings app (business info, tax defaults, serial/barcode
format defaults reading the HEXAGARE_SKU_PREFIX/HEXAGARE_SERIAL_PREFIX/
HEXAGARE_SERIAL_PADDING env-backed config from Phase 0 into an editable
model). Expand login history from Phase 1 into a full activity/audit log
covering every action listed in section 53 (read lines 1991-2038) — hook
into the exception handler / service layer rather than scattering log
calls per view. Manual DB backup command (pg_dump wrapper) + backup
history per section 54.

Frontend: Settings pages (Admin-gated), Activity/Audit log viewer,
Backup trigger + history page.
```

---

## Phase 18 — AWS Deployment

```
Give me a production deployment for AWS built on the Docker images from
Phase 0: backend + celery-worker + celery-beat + frontend images pushed
to ECR, run on ECS Fargate as separate services behind an Application
Load Balancer (frontend + backend routed separately), Postgres on RDS,
Redis on ElastiCache, media/static on S3 (already wired via
django-storages) served through CloudFront, secrets in AWS Secrets
Manager, a GitHub Actions CI step that builds/pushes images and runs
migrations on deploy. List the one-time manual setup (VPC/subnets if not
default, RDS instance, ElastiCache cluster, S3 bucket + policy, ECR
repos, ECS cluster/services/task definitions for all four services, ALB +
target groups + routing rules, IAM roles) versus what CI handles on every
deploy after that.
```

---

# WhatsApp Setup (you don't have a WhatsApp Business account yet)

You don't need the WhatsApp Business **app** — the **WhatsApp Cloud API** (Meta's official API,
what Phase 15 integrates with) is separate from the consumer app and free for a solid message
volume to start (check current free-tier limits when you set up, Meta updates these).

1. Create a **Meta Developer account** at developers.facebook.com (any Facebook account works).
2. Create a **Meta Business Portfolio** at business.facebook.com — individual/sole proprietor is
   fine, no registered company needed for this step.
3. Create a **Meta App** (type "Business") in the developer console, add the **WhatsApp** product.
4. Use the **free test phone number** Meta gives you automatically to build/test Phase 15 end to
   end before touching your real number.
5. To add your real number: it must **not currently be active on the regular WhatsApp or
   WhatsApp Business app** — delete that WhatsApp account from the number first (in-app: Settings
   → Account → Delete My Account) if it's currently in use, since a number registers to one
   WhatsApp product at a time. You can reuse your existing SIM/number this way, no second line
   needed.
6. **Verify your business** in Business Settings → Business Info — basic info is enough for the
   free tier and starting message limits; deeper verification only matters if you outgrow those.
7. **Generate a permanent access token**: create a System User under Business Settings, assign it
   to your WhatsApp app with `whatsapp_business_messaging` permission, generate a
   non-expiring token (the quick-start token expires in 24h — don't use that one in Phase 15).
8. Note the **Phone Number ID**, **WhatsApp Business Account ID (WABA ID)**, and the **access
   token** — these are exactly the three env vars Phase 15 expects.
9. **Message templates**: your first message to a customer who hasn't messaged you first must use
   a pre-approved template (e.g. "Your invoice from Hexagare is ready: {{link}}"), submitted in
   WhatsApp Manager for approval (usually minutes to a few hours). After a customer replies once,
   free-form messages work for 24 hours. Build and get this template approved before wiring
   up Phase 15's send call.

---

# Frontend Plugins/Libraries

| Purpose | Library | Why |
|---|---|---|
| Styling | Tailwind CSS | matches "no component framework yet" gap in current frontend |
| Components | shadcn/ui (Radix-based) | accessible primitives, pairs with Tailwind, no runtime CSS-in-JS overhead |
| Routing | React Router | standard, nothing in the repo yet to conflict with |
| Server state | TanStack Query | fits the response-envelope/pagination shape your backend already returns |
| Client/global state | Zustand | small — auth store, cart state during POS, minimal boilerplate |
| Forms | react-hook-form + zod | pairs well with the `{"error": {"fields"}}` shape from your exception handler |
| HTTP | your existing `frontend/src/api/client.ts` fetch wrapper | already exists — extend it, no need for Axios |
| Barcode/QR scanning | html5-qrcode or @zxing/browser | camera access in mobile browsers, no native app |
| Charts | Recharts | simplest for the Phase 16 dashboard |
| PWA | vite-plugin-pwa | Phase 6 manifest/service worker |

# Backend Libraries (beyond what's already in CLAUDE.md's stack)

| Purpose | Library | Why |
|---|---|---|
| PDF (labels + invoices) | WeasyPrint | HTML/CSS → PDF, easiest to template, runs fine in a Celery task |
| Barcode rendering | python-barcode | Code128, matches "generated on demand, never stored" |
| API schema | drf-spectacular | already named in your CLAUDE.md — wire it in Phase 0 |
| S3 storage | django-storages + boto3 | already named in your CLAUDE.md — wire it in Phase 0 |
| Email | Django's EmailMessage + SMTP/SendGrid | Phase 15 |
| WhatsApp | WhatsApp Cloud API (Meta, official) | Phase 15 — see setup above |
| Exports | openpyxl (Excel) / built-in csv | Phase 14 |