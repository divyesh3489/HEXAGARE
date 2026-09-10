# Amazon Order Import

> Stub created in Phase 0. Fill in during Phase 9. `CLAUDE.md` treats this
> document as authoritative once complete.

## Source abstraction
Planned: `apps/integrations/amazon/sources.py:AmazonOrderSource` is the interface.
A CSV implementation ships first; a future SP-API adapter implements the same
interface. `AmazonOrderImportService` depends only on the interface, never on CSV
parsing directly.

## CSV format
_To be documented in Phase 9:_ expected columns, date formats, currency handling.

## Idempotency keys
- `Sale` keyed on `(sales_channel, external_reference)`.
- `AmazonOrderSettlement` keyed on `(sale, sku)`.

Re-importing the same file must not create duplicates or double-count financials.

## Channel-specific financials
Amazon per-line fees, shipping, advertising, refunds and net revenue live on
`AmazonOrderSettlement`, not on the generic `Sale` / `SaleLine`. Fee structure is
configurable because rates change over time.

## Execution
Runs via a Celery task (`apps/integrations/amazon/tasks.py`), never inline on the
upload request.
