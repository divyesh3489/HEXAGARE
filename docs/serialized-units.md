# Serialized Units

Authoritative for the serial-number format, the advisory-lock reasoning, and the
`SerializedUnit` state machine. Built in Phase 3 (`apps/products`); the ledger
wiring (`SerializedInventoryService`) arrives in Phase 4. Keep this file in step
with `apps/products/models.py` and `apps/products/services/serial_numbers.py`.

Related: ADR-007 (`inventory.Location` pulled into Phase 3), ADR-008 (per-variant
advisory-locked sequence + the `SerializedUnitEvent` log).

---

## What a serialized unit is

One physical, individually-tracked item of a `ProductVariant`. Rule 1/2/3 of
`HEXAGARE_FEATURES.md` §55:

```
Barcode  →  Serial Number  →  Product Unit  →  SKU  →  Variant  →  Product
```

A barcode never stands for a bare SKU — it always resolves to exactly one unit.
Each unit has a unique id, a unique serial number, and (therefore) a unique
barcode.

### Fields (`SerializedUnit`)

| Field | Notes |
|---|---|
| `variant` | FK → `products.ProductVariant`, `PROTECT`. |
| `serial_number` | `CharField(unique, editable=False)`. Immutable, never reused. |
| `sequence` | `PositiveIntegerField(editable=False)`. Per-variant counter behind the serial. `(variant, sequence)` is unique. |
| `status` | One of the nine lifecycle statuses (below). `db_index`. |
| `location` | FK → `inventory.Location`, `PROTECT`. **Independent of `status`** — an `IN_TRANSIT` unit still records where it physically is. No free-text location. |
| `purchase_cost` | Optional `Decimal`. |
| `created_by` | FK → user, `SET_NULL`. |
| `created_at` / `updated_at` | Timestamps. |

Barcodes are **not** a field — see "Barcodes" below.

---

## Serial number format

```
<HEXAGARE_SERIAL_PREFIX><variant token>-<zero-padded sequence>
```

Example: `HX11X23-000001`

- **`HEXAGARE_SERIAL_PREFIX`** — from settings, default `HX`. Distinct from
  `HEXAGARE_SKU_PREFIX` (`HEX`): a serial is not a SKU.
- **variant token** — `ProductVariant.code` when set (upper-cased, reduced to
  `A-Z0-9`, capped at 16 chars, e.g. `11X23`). When the variant has no `code`,
  the token is derived from the SKU: the configured SKU prefix is stripped from
  the front and the remaining separators removed (`HEX-MP-NOCODE-9` → `MPNOCODE9`).
  Falls back to `V` if nothing usable is left.
- **sequence** — a per-variant counter, zero-padded to `HEXAGARE_SERIAL_PADDING`
  digits (default `6`). Variant A's units are `…-000001`, `…-000002`, …
  independently of variant B's.

The serial is assigned once, at creation, and never changes or is reused.
`(variant, sequence)` carries a DB `UniqueConstraint` as a backstop so a serial
physically cannot be handed out twice.

`format_serial(variant, sequence)` builds the string;
`_variant_token(variant)` builds the token.

---

## Allocation & the advisory lock

`apps/products/services/serial_numbers.py`:

- **`allocate_serial(variant) → (serial_number, sequence)`** — must run inside a
  transaction. It takes a **per-variant** Postgres advisory lock
  (`pg_advisory_xact_lock(1001, variant_id)` — `1001` is the serial-allocation
  namespace), then reads `MAX(sequence)` for that variant and returns the next
  value. The lock is released when the surrounding transaction ends.
- **`create_unit(*, variant, location, status=GENERATED, purchase_cost=None, actor=None)`**
  — the single-unit path. One `transaction.atomic()` block: allocate the serial,
  insert the `SerializedUnit`, write the opening `SerializedUnitEvent`. `status`
  must be an *initial* status (`GENERATED` or `AVAILABLE`).

### Why a lock here, but none for SKU suggestion

A SKU **suggestion** is advisory (ADR-004): if two callers race, the loser hits
the `sku` unique constraint, gets a `validation_error`, and retries with the next
candidate — no lock needed.

A serial **sequence** is different: it must be gapless-by-construction and
collision-free *per variant*. Two bulk generators running for the same variant
must not both compute "next = 42". The advisory lock serialises allocation for a
single variant while letting allocations for **different** variants proceed in
parallel (the lock key includes `variant_id`). It is an advisory (not row) lock
so it doesn't depend on a placeholder row existing, and it auto-releases at
transaction end.

Bulk generation (Phase 5) calls `allocate_serial` / `create_unit` N times inside
one transaction — the lock is held once for the batch.

---

## Lifecycle: statuses & the state machine

Nine statuses (`HEXAGARE_FEATURES.md` §14):

| Status | Meaning |
|---|---|
| `GENERATED` | Serial assigned; unit not yet in usable inventory. |
| `AVAILABLE` | Sellable / allocatable. |
| `RESERVED` | Allocated to an order/invoice; sale not completed. |
| `IN_TRANSIT` | Moving between locations / in an active shipment. |
| `SOLD` | Sale completed. |
| `RETURNED` | Returned by a customer; must be classified resellable → `AVAILABLE` or damaged → `DAMAGED`. |
| `DAMAGED` | Cannot currently be sold. |
| `LOST` | Physical unit cannot be located. |
| `CANCELLED` | Allocation cancelled. Terminal. |

`SerializedUnit.ALLOWED_TRANSITIONS` (`{status: {reachable statuses}}`):

| From | To |
|---|---|
| `GENERATED` | `AVAILABLE`, `CANCELLED` |
| `AVAILABLE` | `RESERVED`, `IN_TRANSIT`, `DAMAGED`, `LOST` |
| `RESERVED` | `AVAILABLE`, `SOLD`, `CANCELLED` |
| `IN_TRANSIT` | `AVAILABLE`, `SOLD`, `LOST` |
| `SOLD` | `RETURNED` |
| `RETURNED` | `AVAILABLE`, `DAMAGED` |
| `DAMAGED` | `AVAILABLE`, `LOST` |
| `LOST` | `AVAILABLE` |
| `CANCELLED` | — (terminal) |

`can_transition_to(status)`, `allowed_transitions`, and `is_terminal` are model
helpers. A no-op (moving to the current status) is rejected.

Some transitions are only *meaningful* through a specific business action. From
Phase 4 those go through `SerializedInventoryService`, which also writes the
stock ledger (`inventory-ledger.md`, ADR-009). This is enforced by **convention**
plus reconciliation, not a hard lock — the plain `transition` endpoint can still
apply any legal move, it just won't touch the ledger (see "Mutation path").

| Transition | Business action (Phase) | Service verb |
|---|---|---|
| `AVAILABLE → RESERVED` / back | Order / invoice reservation (Phase 7) | `reserve` / `release` |
| `RESERVED → SOLD`, `IN_TRANSIT → SOLD` | Sale completion / payment (Phase 8) | `sell` |
| `AVAILABLE → IN_TRANSIT`, `IN_TRANSIT → AVAILABLE` | Stock transfer (Phase 4) | `start_transfer` / `complete_transfer` / `cancel_transfer` |
| `SOLD → RETURNED`, `RETURNED → AVAILABLE/DAMAGED` | Returns processing (Phase 10) | `return_unit` / `restore` / `damage` |
| `AVAILABLE → DAMAGED/LOST`, back | Write-off / recovery (Phase 10) | `damage` / `lose` / `restore` |

---

## Mutation path

- **Phase 3** — `transition_unit(unit, *, to_status, location=None, actor=None,
  note="")`: locks the unit row (`select_for_update`), validates against
  `ALLOWED_TRANSITIONS`, updates `status` (and optionally `location`), writes a
  `SerializedUnitEvent`. It does **not** touch any stock ledger (there isn't one
  until Phase 4). Exposed as `POST /serialized-units/{id}/transition/`.
- **Phase 4+** — `SerializedInventoryService`
  (`apps/products/services/serialized_inventory.py`) is the **only** path that
  changes a unit's status as part of a business action
  (generate / reserve / release / start_transfer / complete_transfer /
  cancel_transfer / sell / return_unit / damage / lose / restore / cancel). Each
  verb locks the unit row, calls `transition_unit` **and**
  `InventoryService.move_unit` in one `transaction.atomic`, so the status and the
  stock ledger never diverge; a rejected transition rolls back both.
  `create_unit` now also emits an `OPENING` ledger row.
- **The plain `transition` endpoint is unchanged and still writes no ledger row**
  — the deliberate gap (ADR-009). It is for status-only corrections; a move with
  stock meaning made through it leaves `InventoryBalance` stale until
  `manage.py rebuild_inventory_balances` runs. `GET /inventory/overview/`
  (computed live from the units) reports `cache_matches: false` and a
  `balance_mismatch` alert fires meanwhile. Do not "fix" this by wiring the
  endpoint to the ledger.

Never change `status`, `serial_number`, `sequence` or `location` with a direct
field write.

`SerializedUnit.save()` **hard-blocks** any post-creation change to
`variant` / `serial_number` / `sequence` (raises `ValueError`) — a serial is a
permanent physical identity and must not drift from the variant it was minted
for. `status` / `location` writes via `transition_unit` pass an explicit
`update_fields` and skip the check. The Django admin registers `SerializedUnit`
and `SerializedUnitEvent` **view-only** (no add / change / delete) for the same
reason — create and transition go through the API.

---

## The event log

`SerializedUnitEvent` (append-only; never updated or deleted):
`unit`, `from_status` (blank on creation), `to_status`, `location`, `note`,
`actor`, `created_at`. Written by `create_unit` and `transition_unit`. This is
the unit's own audit trail and the "History" in a barcode scan (§55 rule 4). It
is **distinct** from the Phase 4 `inventory.InventoryTransaction` stock ledger
(ADR-008) — a unit event records *what happened to this unit*; a ledger row
records *a quantity movement at a location*.

---

## Barcodes

A unit's barcode is the **Code128 rendering of its `serial_number`**, generated
**on demand** and streamed through `apps/common/renderers.py:BinaryRenderer`
(`image/png`), never stored as a file. `apps/products/services/barcodes.py:
render_code128_png(data)` (python-barcode + Pillow `ImageWriter`, `write_text`
on). Endpoint: `GET /serialized-units/{id}/barcode/`.

---

## Lookup / scan (§55 rule 4)

`resolve_unit(code)` takes a serial number **or** a scanned barcode value (they
are the same string) — case-insensitive, whitespace-trimmed — and returns the
unit with variant / product / category / location / events pre-loaded, or raises
`Http404`. Exposed as `GET /serialized-units/lookup/?code=<serial>` (permission
`barcode.scan`). The response carries the full chain plus the resolved pricing
block (`effective_selling_price`, `base_price`, `gst_amount`, `cgst_amount`,
`sgst_amount`, `effective_mrp`, `discount_*`), the current location and status,
and the event history — everything the Phase 6 scanner PWA needs from one call.

---

## API surface (`/api/v1/products/serialized-units/`)

| Route | Method | Permission | Purpose |
|---|---|---|---|
| `` | GET | `serials.view` | List. Filters: `?status=` `?location=` `?variant=` `?product=` `?search=` (serial). |
| `` | POST | `serials.manage` | Create one unit (allocates its serial). Bulk + label PDFs are Phase 5. |
| `{id}/` | GET | `serials.view` | Full chain + pricing + `allowed_transitions` + events. |
| `{id}/transition/` | POST | `serials.manage` | `{status, location?, note?}` — status-only move (no ledger). |
| `{id}/barcode/` | GET | `serials.view` | On-demand Code128 PNG. |
| `lookup/?code=` | GET | `barcode.scan` | Resolve a serial / scanned barcode to the full chain. |

`PUT` / `PATCH` / `DELETE` are not exposed — serials are immutable and status
moves only via `transition` (or `SerializedInventoryService` from Phase 4).

---

## Bulk generation & label PDFs (Phase 5)

Generate many units of one variant at once and get a printable label sheet.
Built in `apps/products` (`services/bulk_generate.py`, `services/labels.py`,
`tasks.py`); ADR-010; `HEXAGARE_FEATURES.md` §10–11.

### `LabelBatch` / `LabelBatchItem`

`LabelBatch` is the **history row** for one generation run — the request
(`variant`, `location`, `quantity`, `initial_status`, `label_size`,
`barcode_type`, the `include_*` label-content flags + `custom_text`), the PDF
render state (`status` `PENDING`/`READY`/`FAILED`, `pdf_file` on
`STORAGES["default"]`, `pdf_generated_at`, `error_message`), and its units via
the `LabelBatchItem` M2M-through. Created only through the API; never edited
(admin is view-only), same as `SerializedUnit`.

### Flow

`bulk_generate_units(*, variant, location, quantity, initial_status, label_size,
barcode_type, label_content, actor)` — **one `transaction.atomic`**:

1. create the `LabelBatch` (`status=PENDING`);
2. call `SerializedInventoryService.generate()` `quantity` times — each
   allocates its serial under the **same per-variant advisory lock** as the
   single-unit path (`allocate_serial`, `MAX(sequence)+1`) and writes the
   `OPENING` ledger row;
3. `bulk_create` the `LabelBatchItem` rows;
4. `transaction.on_commit(…)` enqueues `render_label_pdf` **after** the commit.

**All-or-nothing** (§11 "Transaction Safety"): any failure rolls the whole block
back — no batch, no units, no ledger rows, no render task. `quantity` is capped
at `LabelBatch.MAX_QUANTITY` (5000).

`render_label_pdf` (Celery) renders with `build_label_pdf` and stores the PDF.
On failure it sets `status=FAILED` + `error_message` and returns — the units
stay; an operator re-runs `POST …/label-batches/{id}/regenerate/`.

### Starting serial is a preview, not an input

§10/§11 mention "set starting serial / prefix", but serials stay
allocator-owned (ADR-008). The wizard shows
`GET …/label-batches/next-serial/?variant=<id>` (`next_serial_preview`, **no
lock**); the real serial is assigned under the lock during generation.
`HEXAGARE_SERIAL_PREFIX` remains env config.

### Label rendering

`apps/products/services/labels.py:build_label_pdf(batch) -> bytes` uses
**ReportLab** (ADR-010 — not WeasyPrint; pure-Python, no system libs). The grid
comes straight from the `LabelSize` (`columns`×`rows`, `margin_mm`, `gutter_mm`,
per-label `width_mm`×`height_mm`, `orientation`); a 1×1 size prints one label per
page (thermal roll), anything larger tiles on A4. Each label draws the
`HEXAGARE` header, the enabled content rows, the serial, and a **vector Code 128**
of the serial. Barcode type is Code 128 only this phase (`barcode_type` stored
for forward-compatibility).

### API surface (`/api/v1/products/label-batches/`)

| Route | Method | Permission | Purpose |
|---|---|---|---|
| `` | GET | `serials.view` | Generation history. Filters: `?variant=` `?product=` `?location=` `?status=`. |
| `` | POST | `serials.manage` | Bulk generate: `{variant, location, quantity, label_size, initial_status?, barcode_type?, include_*?, custom_text?}`. All-or-nothing; returns the `PENDING` batch. |
| `{id}/` | GET | `serials.view` | One batch + `serials` list. Poll `status` for `PENDING → READY`/`FAILED`. |
| `{id}/regenerate/` | POST | `serials.manage` | Re-render the PDF (units untouched). |
| `{id}/pdf/` | GET | `serials.view` | Download the rendered sheet (`application/pdf` via `BinaryRenderer`); 400 until `READY`. |
| `next-serial/?variant=` | GET | `serials.view` | Preview the serial the next allocation will produce. |

`initial_status` must be an initial status (`GENERATED` or `AVAILABLE`), same
rule as single-unit `create_unit`.
