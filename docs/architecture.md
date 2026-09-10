# Architecture

> Stub created in Phase 0. Fill in as each domain is built. `CLAUDE.md` remains
> the authoritative summary until this document catches up.

## Shape

Modular monolith: one Django + DRF backend, one React + Vite + TypeScript
frontend, orchestrated with Docker Compose (PostgreSQL, Redis, Celery worker,
Celery beat).

## Backend layout

```
backend/hexagare/
  manage.py
  hexagare/
    settings/        base.py + development/staging/production/test.py, chosen by DJANGO_ENV
    urls.py          all API routes mounted under /api/v1/
    celery.py        Celery app, autodiscovers apps/<app>/tasks.py
  apps/
    common/          cross-cutting: exception envelope, pagination, binary renderer, health
    accounts/        auth + RBAC                         (Phase 1)
    products/        catalog (Category / Product / ProductVariant / attributes /
                     images / LabelSize + SKU service)   (Phase 2);
                     serialized units + on-demand barcode + scan lookup   (Phase 3)
    inventory/       Location (read-only)                (Phase 3, ADR-007);
                     stock ledger + balance cache + transfers + alerts
                     (Phase 4, ADR-009 — see inventory-ledger.md)
    sales/           channel-agnostic orders             (Phase 7)
    billing/         payment / invoice                   (Phase 8)
    integrations/    Amazon import                       (Phase 9)
    customers/ purchases/ suppliers/ expenses/ reports/ notifications/   (later phases)
```

## Frontend

React + Vite + TypeScript SPA under `frontend/src` — `routes/` (a
`createBrowserRouter` tree behind an auth gate + `AppShell`), `features/<domain>/`
(one folder per domain: `api.ts` fetch wrappers, React Query `hooks.ts`, pages),
`components/ui/` (shadcn/Tailwind primitives), `api/client.ts` (the `{error}` /
`{data,meta}` envelope-aware fetch client with JWT refresh).

Installable **PWA** since Phase 6 (`vite-plugin-pwa`, ADR-011): a service worker
precaches the built app shell for offline launch, but every `/api/` and `/media/`
request is `NetworkOnly` so authed per-user data is never served stale. The
`/barcode/scan` route is a mobile camera scanner (`@zxing/browser`, lazy-loaded)
that resolves a serial through the Phase 3 lookup endpoint.

**Testing the scanner camera on a phone.** Browsers only expose `getUserMedia`
on a *secure context* — HTTPS, or a `localhost` / `127.0.0.1` origin. Loading the
dev server over its LAN IP (`http://192.168.x.x:5173`) shows the scanner's
"Camera unavailable" state; manual serial entry still works, but the camera does
not. To exercise the camera on a real device, make the origin `localhost` via an
Android USB reverse-tunnel:

```
# one-time: install Google "platform-tools" (has adb); enable USB debugging on the phone
adb devices                       # phone shows as "device"
adb reverse tcp:5173 tcp:5173     # phone's localhost:5173 -> this PC's :5173
# then open http://localhost:5173/barcode/scan in Chrome ON THE PHONE
```

`adb reverse` is cleared on unplug/reboot — re-run the line each session
(`adb reverse --remove-all` to clear). A trusted-HTTPS tunnel
(`cloudflared tunnel --url http://localhost:5173`, ngrok) is the alternative when
USB isn't available. iOS Safari has no `adb` equivalent — use a tunnel there.

## Cross-cutting conventions

- **Error envelope**: `apps.common.exceptions.api_exception_handler` →
  `{"error": {"code", "message", "fields"?}}`.
- **List envelope**: `apps.common.pagination.StandardPagination` →
  `{"data": [...], "meta": {"count", "next", "previous"}}`, `page` / `page_size`
  (max 100).
- **Binary responses**: `apps.common.renderers.BinaryRenderer`.
- **API schema**: `drf-spectacular` at `/api/schema/` and `/api/docs/`.
- **Async work**: commit in Postgres first, enqueue the Celery task after.

## Seed & demo data

Reference data (RBAC role groups, `Location` rows Warehouse/Amazon/Offline,
SalesChannels once built, `LabelSize` defaults) is seeded on every `migrate` via
`post_migrate` hooks — no manual step. `make seed`
(`python manage.py seed_demo_data`, in `apps/common`) is the separate,
idempotent, dev-only command that adds demo **users** (`admin` / `manager` /
`cashier` / `warehouse` `@hexagare.test`, password `demo-Passw0rd!`, realigned to
their role group on every run), a small demo **catalog** (Peripherals tree,
Size/Colour/Switch attributes, 3 products × 2 variants), a handful of demo
**serialized units** (skipped for any variant that already has units — serials
are never reused) and a few **stock-level policies** (so the alerts panel isn't
empty). It rebuilds the `InventoryBalance` cache at the end and refuses to run
under `DJANGO_ENV=staging`/`production` without `--force`.

## Settings & environment

`DJANGO_ENV` selects the settings module. `django-environ` reads configuration
from the process environment (populated from `.env` via Compose `env_file`).
Media is a local volume in development and S3 (`django-storages`) when
`USE_S3=true`.
