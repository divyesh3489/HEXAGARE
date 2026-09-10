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
                     serialized units + barcodes         (Phase 3)
    inventory/       ledger + balances                   (Phase 4)
    sales/           channel-agnostic orders             (Phase 7)
    billing/         payment / invoice                   (Phase 8)
    integrations/    Amazon import                       (Phase 9)
    customers/ purchases/ suppliers/ expenses/ reports/ notifications/   (later phases)
```

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

Reference data (RBAC role groups, Locations/SalesChannels once built, `LabelSize`
defaults) is seeded on every `migrate` via `post_migrate` hooks — no manual step.
`make seed` (`python manage.py seed_demo_data`, in `apps/common`) is the separate,
idempotent, dev-only command that adds demo **users** (`admin` / `manager` /
`cashier` / `warehouse` `@hexagare.test`, password `demo-Passw0rd!`, realigned to
their role group on every run) and a small demo **catalog** (Peripherals tree,
Size/Colour/Switch attributes, 3 products × 2 variants). It refuses to run under
`DJANGO_ENV=staging`/`production` without `--force`.

## Settings & environment

`DJANGO_ENV` selects the settings module. `django-environ` reads configuration
from the process environment (populated from `.env` via Compose `env_file`).
Media is a local volume in development and S3 (`django-storages`) when
`USE_S3=true`.
