# Serialized Units

> Stub created in Phase 0. Fill in during Phase 3 (serial format + advisory lock)
> and Phase 4 (`SerializedInventoryService`). `CLAUDE.md` treats this document as
> authoritative once complete — keep it accurate.

## Serial number format
Planned: `<HEXAGARE_SERIAL_PREFIX><variant-code>-<zero-padded sequence>`, e.g.
`HXMP1123-000001`. Prefix and padding come from the `HEXAGARE_SERIAL_PREFIX` /
`HEXAGARE_SERIAL_PADDING` settings (distinct from `HEXAGARE_SKU_PREFIX`).
Immutable and never reused.

## Allocation
Planned: sequence allocated under a Postgres advisory lock in
`apps/products/services/serial_numbers.py` so concurrent bulk generation cannot
collide.

## State machine
Planned: `ALLOWED_TRANSITIONS` on the `SerializedUnit` model. Statuses and
transitions to be documented here in Phase 3.

## Mutation path
Planned: `SerializedInventoryService` is the only path allowed to
transfer / sell / damage / lose / return a unit. It locks the unit row, applies
the state machine, and writes the matching `InventoryTransaction` in the same
atomic block. The plain status-transition endpoint from Phase 3 stays available
for status-only changes and must not touch the ledger (intentional gap).

## Barcodes
Code128 renderings of the serial, generated on demand via `BinaryRenderer`,
never stored as images.
