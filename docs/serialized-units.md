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

Some transitions are only *meaningful* through a specific business action — from
Phase 4 those are **enforced** to go through `SerializedInventoryService` (which
also writes the stock ledger):

| Transition | Business action (Phase) |
|---|---|
| `AVAILABLE → RESERVED` | Order / invoice reservation (Phase 7) |
| `RESERVED → SOLD`, `IN_TRANSIT → SOLD` | Sale completion / payment (Phase 8) |
| `AVAILABLE → IN_TRANSIT`, `IN_TRANSIT → AVAILABLE` | Stock transfer (Phase 4) |
| `SOLD → RETURNED`, `RETURNED → AVAILABLE/DAMAGED` | Returns processing (Phase 10) |

---

## Mutation path

- **Phase 3** — `transition_unit(unit, *, to_status, location=None, actor=None,
  note="")`: locks the unit row (`select_for_update`), validates against
  `ALLOWED_TRANSITIONS`, updates `status` (and optionally `location`), writes a
  `SerializedUnitEvent`. It does **not** touch any stock ledger (there isn't one
  until Phase 4). Exposed as `POST /serialized-units/{id}/transition/`.
- **Phase 4+** — `SerializedInventoryService` becomes the **only** path allowed
  to transfer / sell / damage / lose / return a unit: it wraps
  `transition_unit` **and** `InventoryService` in one atomic block so the ledger
  stays in step. The plain `transition` endpoint stays available for simple
  status-only corrections.

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
