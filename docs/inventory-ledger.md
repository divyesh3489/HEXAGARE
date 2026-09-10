# Inventory Ledger

Authoritative for the Phase 4 stock ledger: the `InventoryTransaction` /
`InventoryBalance` shape, `InventoryService` and `SerializedInventoryService`,
the stock-transfer lifecycle, the alert rules, and the deliberate gap around the
plain `transition` endpoint. Keep this in step with `apps/inventory/models.py`,
`apps/inventory/services/`, and `apps/products/services/serialized_inventory.py`.

Related: ADR-009 (this design), ADR-007 (`Location` pulled into Phase 3),
ADR-008 (`SerializedUnitEvent` vs the ledger). The unit state machine itself
lives in `serialized-units.md`.

---

## The two models

### `InventoryTransaction` — the append-only ledger

One row is one **signed change to a stock bucket** — a `(variant, location,
status)` triple. Fields: `reference` (UUID), `kind`, `variant`, `location`,
`status` (a `SerializedUnit.Status` value), `quantity` (∈ ℤ, never 0),
`serialized_unit` (nullable — set when the movement is a specific unit),
`note`, `actor`, `created_at`.

Rows are **immutable**: `save()` raises on any post-creation edit, `delete()`
always raises. To reverse a mistake, write a compensating row.

A movement between buckets is the **−1 / +1 pair** that shares one `reference`:

| Action | Rows (same `reference`) |
|---|---|
| Reserve | `−1 AVAILABLE @L`, `+1 RESERVED @L` |
| Start transfer | `−1 AVAILABLE @src`, `+1 IN_TRANSIT @src` |
| Receive transfer | `−1 IN_TRANSIT @src`, `+1 AVAILABLE @dst` |
| Sell | `−1 RESERVED @L` (or `IN_TRANSIT`), `+1 SOLD @L` |
| Opening (new unit) | `+1 <initial status> @L` (single row, `kind=OPENING`) |
| Manual adjustment | single signed row, `kind=ADJUSTMENT`, `serialized_unit` null |

`kind` ∈ `OPENING`, `TRANSFER_OUT`, `TRANSFER_IN`, `RESERVE`, `RELEASE`, `SALE`,
`RETURN`, `DAMAGE`, `LOSS`, `RESTORE`, `CANCEL`, `ADJUSTMENT`.

### `InventoryBalance` — the rebuildable cache

One row per `(variant, location, status)` bucket (`UniqueConstraint`),
`quantity` a `PositiveIntegerField`. It is **only** written by `InventoryService`
and is fully reconstructable — treat it as disposable. Nothing should read a
total from here without being willing to fall back to a live count; the
`/inventory/overview/` endpoint does the live count itself.

---

## `InventoryService` (`apps/inventory/services/ledger.py`)

The **only** writer of both models. Every method opens its own
`transaction.atomic` and locks the affected `InventoryBalance` row
(`select_for_update`).

| Method | Purpose |
|---|---|
| `record(*, variant, location, status, quantity, kind, serialized_unit=None, reference=None, note="", actor=None)` | One bucket change: writes the ledger row + updates the balance. Refuses `quantity == 0` and any move that would drive the bucket negative. |
| `move_unit(*, unit, from_location, from_status, to_location, to_status, kind, reference=None, note="", actor=None)` | The −1 / +1 pair for a serialized unit changing bucket. A true no-op writes nothing. |
| `opening(*, unit, note="opening", actor=None)` | `+1` at the unit's initial status/location. Called by `create_unit`. |
| `adjust(*, variant, location, status, quantity, note="", actor=None)` | Manual non-serialized correction (`kind=ADJUSTMENT`). |
| `rebuild_balances(*, variant=None)` | Wipe & recompute every balance row from the live `SerializedUnit` counts plus non-serialized `ADJUSTMENT` sums. Exposed as `manage.py rebuild_inventory_balances`. |

---

## `SerializedInventoryService` (`apps/products/services/serialized_inventory.py`)

The **only** path allowed to change a serialized unit's status as part of a
business action. Each verb: lock the unit row → `transition_unit(...)` (Phase 3:
`ALLOWED_TRANSITIONS` + `SerializedUnitEvent`) → `InventoryService.move_unit(...)`
— one atomic block. A rejected transition rolls back both the status and the
ledger.

| Verb | Move | Ledger `kind` | Used by |
|---|---|---|---|
| `generate` | create → `GENERATED`/`AVAILABLE` | `OPENING` | Phase 5 bulk generate |
| `reserve` / `release` | `AVAILABLE ↔ RESERVED` | `RESERVE` / `RELEASE` | Phase 7 / 8 |
| `start_transfer` | `AVAILABLE → IN_TRANSIT` (location unchanged) | `TRANSFER_OUT` | Phase 4 transfers |
| `complete_transfer` | `IN_TRANSIT → AVAILABLE` @ `to_location` | `TRANSFER_IN` | Phase 4 transfers |
| `cancel_transfer` | `IN_TRANSIT → AVAILABLE` @ current location | `TRANSFER_IN` | Phase 4 transfers |
| `sell` | `RESERVED`/`IN_TRANSIT → SOLD` | `SALE` | Phase 8 |
| `return_unit` | `SOLD → RETURNED` | `RETURN` | Phase 10 |
| `damage` / `lose` | `→ DAMAGED` / `→ LOST` | `DAMAGE` / `LOSS` | Phase 10 |
| `restore` | `DAMAGED`/`LOST`/`RETURNED → AVAILABLE` | `RESTORE` | Phase 10 |
| `cancel` | `GENERATED`/`RESERVED → CANCELLED` | `CANCEL` | — |

---

## The intentional gap: the plain `transition` endpoint

`POST /api/v1/products/serialized-units/{id}/transition/` (Phase 3) still applies
a status move directly and **writes no ledger row**. It is kept for status-only
corrections. Using it for a move with stock meaning leaves `InventoryBalance`
stale.

How the staleness is visible and fixable:

- `GET /inventory/overview/` computes stock **live** from the `SerializedUnit`
  rows and returns `cache_matches: false` when the cache disagrees.
- `compute_alerts()` emits a `balance_mismatch` alert per drifted bucket.
- `manage.py rebuild_inventory_balances` (optionally `--variant <id>`) resyncs.

This is deliberate (ADR-009): the alternative — routing every status change
through the ledger — removes the simple correction path. Do **not** "fix" it by
having the endpoint call the ledger.

---

## Stock transfers (`StockTransfer` / `StockTransferLine`)

Scan-built movement of serialized units between two locations, with history
(§16). Lifecycle: `OPEN` (accumulating scanned units, each already
`IN_TRANSIT`) → `COMPLETED` (`receive`) or `CANCELLED` (`cancel`).

| Route | Method | Permission | Effect |
|---|---|---|---|
| `/inventory/transfers/` | GET / POST | `inventory.transfer` | list / open a transfer (`from_location`, `to_location`, `note`) |
| `/inventory/transfers/{id}/scan/` | POST `{serial}` | `inventory.transfer` | resolve the serial; require `AVAILABLE` at `from_location`; `start_transfer` + add a line |
| `/inventory/transfers/{id}/receive/` | POST | `inventory.transfer` | every open line `IN_TRANSIT → AVAILABLE` at `to_location`; transfer `COMPLETED` |
| `/inventory/transfers/{id}/cancel/` | POST | `inventory.transfer` | every open line back to `AVAILABLE` at `from_location`; transfer `CANCELLED` |

---

## Alerts (`apps/inventory/services/alerts.py`)

Computed on demand from `InventoryBalance` + `StockLevelPolicy` — nothing stored.

`StockLevelPolicy`: `variant`, optional `location` (blank = the variant's total
across all locations), `min_quantity`, `max_quantity` (nullable), `is_active`.

| Alert `type` | Condition (on the `AVAILABLE` quantity for the policy's scope) |
|---|---|
| `out_of_stock` | `available == 0` |
| `low_stock` | `0 < available ≤ min_quantity` |
| `overstock` | `max_quantity` set and `available ≥ max_quantity` |
| `balance_mismatch` | a `(variant, location, status)` bucket where the cache ≠ the live unit count (reconciliation; toggle with `?reconcile=false`) |

`GET /inventory/alerts/` (`inventory.view`) returns the list; `?variant=` /
`?location=` narrow it.

---

## API surface (`/api/v1/inventory/`)

| Route | Method(s) | Permission | Purpose |
|---|---|---|---|
| `locations/` | GET / POST / PATCH / DELETE | `inventory.view` read, `stock_adjustments` write | CRUD; delete blocked while stock/history exists |
| `balances/` | GET | `inventory.view` | the balance cache; `?variant=` `?location=` `?status=` `?product=` |
| `transactions/` | GET | `inventory.view` | the ledger; `?variant=` `?location=` `?status=` `?kind=` `?reference=` `?serialized_unit=` `?search=` |
| `policies/` | GET / POST / PATCH / DELETE | `inventory.view` read, `stock_adjustments` write | stock-level policies |
| `transfers/` (+ `scan/` `receive/` `cancel/`) | GET / POST | `inventory.transfer` | scan-based transfers |
| `overview/` | GET | `inventory.view` | live stock by variant × location × status + `totals_by_status` + `cache_matches` |
| `alerts/` | GET | `inventory.view` | computed alerts |
| `adjustments/` | POST | `stock_adjustments` | one manual non-serialized quantity correction |
