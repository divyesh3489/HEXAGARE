# Amazon Order Import

Phase 9. `CLAUDE.md` treats this document as authoritative.

## Source abstraction

`apps/integrations/amazon/sources.py:AmazonOrderSource` is the interface
`apps/integrations/amazon/services/importer.py:AmazonOrderImportService`
depends on. `CSVAmazonOrderSource` is the only implementation today; a future
SP-API adapter implements the same interface (`rows() -> Iterator[AmazonOrderRow
| AmazonOrderRowError]`) and needs no change to the importer.

## CSV format

One row per **order line** (one `amazon_order_id` + `amazon_sku` combination).
If the same order/sku pair appears twice in a file, that whole order is
rejected with an error asking you to merge the quantities in the source file
first — the importer never guesses how to combine two rows for the same line.

| Column              | Required | Meaning                                                                 |
|----------------------|:--------:|--------------------------------------------------------------------------|
| `order_id`           | yes      | The Amazon order id. Becomes `Sale.external_reference`.                 |
| `order_date`         | yes      | `YYYY-MM-DD`. Used to pick the right `AmazonFeeConfig` row.             |
| `order_status`       | yes      | See the status mapping below.                                          |
| `amazon_sku`         | yes      | Resolved to a `ProductVariant` via `AmazonSkuMapping` (see below).      |
| `quantity`           | yes      | Integer, ≥ 1.                                                          |
| `selling_price`      | yes      | **Per unit**, GST-inclusive — what the customer paid for one unit.      |
| `gst_amount`         | no       | **Per unit**. Blank = `0.00`.                                          |
| `referral_fee`       | no       | **Line total** (not per-unit). Blank = compute from `AmazonFeeConfig`.  |
| `closing_fee`        | no       | Line total. Blank = computed.                                          |
| `fulfillment_fee`    | no       | Line total. Blank = computed.                                          |
| `shipping_cost`      | no       | Line total (courier). Blank = computed.                                |
| `advertising_cost`   | no       | Line total. Blank = computed.                                          |
| `other_charges`      | no       | Line total. Blank = computed.                                          |
| `refund_amount`      | no       | Line total. Blank = `0.00`. Never computed/estimated.                  |

`selling_price`/`gst_amount` are per-unit because they're a natural "price of
one" figure; the fee/charge columns are left as Amazon reports them (already
a total for that order line), and a blank fee column is filled in from the
configured fee structure (see below), scaled by the whole line, not
per-unit.

### `order_status` mapping

Case-insensitive. Anything not in this table fails that order with an
"Unknown order_status" error rather than being silently guessed:

| CSV value                | `Sale.status` | Sells serialized units? |
|---------------------------|---------------|:------------------------:|
| `pending`                 | `PENDING`     | no                       |
| `confirmed`               | `CONFIRMED`   | no                       |
| `shipped`                 | `SHIPPED`     | yes                      |
| `in_transit`              | `IN_TRANSIT`  | yes                      |
| `delivered`               | `DELIVERED`   | yes                      |
| `completed`                | `COMPLETED`   | yes                      |
| `cancelled` / `canceled`  | `CANCELLED`   | no                       |
| `returned`                | `RETURNED`    | no                       |
| `refunded`                | `REFUNDED`    | no                       |

## Idempotency keys

- `Sale` keyed on `(sales_channel, external_reference)` — `sales_channel` is
  always the seeded `AMAZON` `SalesChannel`, `external_reference` is
  `order_id`.
- `AmazonOrderSettlement` keyed on `(sale, sku)`.

Re-importing the same file (or an updated extract covering the same orders)
never creates duplicates or double-counts financials — the rules:

- **An order that hasn't sold any units yet is fully rebuilt** on every
  re-import: its lines and settlement rows are recreated from the latest CSV
  values (quantities, prices, fees can all change here — this is expected for
  a `PENDING`/`CONFIRMED` order that later ships).
- **Once an order has sold units** (its status reached `SHIPPED` or later at
  least once), it is **finalized**: a re-import only ever advances
  `Sale.status` forward along the pre-cancellation lifecycle (`PENDING` →
  `CONFIRMED` → `RESERVED` → `SHIPPED` → `IN_TRANSIT` → `DELIVERED` →
  `COMPLETED`) — its lines/settlement are left untouched. A CSV trying to move
  a finalized order to `CANCELLED`/`RETURNED`/`REFUNDED` is **not** applied —
  it's recorded as a failed order in `error_log` instead of silently
  mismatching the (unreversed) units. Reversing a sold unit's stock is Phase
  10 Returns' job, not the importer's.

## Amazon SKU ↔ Hexagare SKU mapping

Every `amazon_sku` is resolved through `AmazonSkuMapping`:

1. An active mapping row for that `amazon_sku` — used if present.
2. Otherwise, if `amazon_sku` exactly matches an existing
   `ProductVariant.sku`, a mapping row is **auto-created** (convenience for
   the common case where the business reuses the same SKU everywhere).
3. Otherwise the order fails with "Unknown Amazon SKU — add a mapping before
   importing." Add the mapping via the SKU Mapping page and re-upload.

## Serialized units & stock

An order whose status sells units (see the table above) draws `quantity`
`AVAILABLE` units of the resolved variant **at the `amazon` stock
`Location`**, oldest first (FIFO by `sequence`) — the same location Amazon
fulfillment stock is expected to be transferred to ahead of going live. Each
unit moves `AVAILABLE → RESERVED → SOLD` through
`SerializedInventoryService` (the state machine has no direct
`AVAILABLE → SOLD` edge) and a `SaleLineUnit` binds it permanently to the
line — same record shape Phase 8's POS checkout produces, so Orders/Returns
tooling doesn't need to know which channel sold a unit.

If there isn't enough available stock at the `amazon` location, that order
fails (logged in `error_log`) and nothing about it is written — no partial
line. The rest of the file still imports.

**Deliberately bypasses `apps.sales.services.units.SaleUnitService` and
`apps.billing.services.checkout.CompleteSaleService` (ADR-014).** An imported
order already happened — it isn't a cart being assembled locally — and Amazon
issues its own invoice to the customer, so **no `Payment`/`Invoice` row is
created** for an imported order. Amazon's own financials live entirely in
`AmazonOrderSettlement`.

## Channel-specific financials

Amazon per-line fees, shipping, advertising, refunds and net revenue live on
`AmazonOrderSettlement`, never on the generic `Sale`/`SaleLine` (the same
pattern any future channel's own financials would use). Computed properties,
matching HEXAGARE_FEATURES.md §21:

- `amazon_fees_total` = `referral_fee + closing_fee + fulfillment_fee`
- `total_deductions` = `amazon_fees_total + shipping_cost + advertising_cost
  + other_charges + refund_amount`
- `settlement_amount` = `selling_price − total_deductions` (what actually
  lands in the bank)
- `net_revenue` = `taxable_value − total_deductions` (GST-exclusive, before
  product cost)
- `product_cost` = `variant.effective_purchase_price × quantity` (a snapshot
  at settlement time, not a live reference)
- `net_profit` = `net_revenue − product_cost`

### Fee structure is configurable (§22)

`AmazonFeeConfig` rows (fee name, `PERCENTAGE`/`FIXED`, value, sales channel,
optional category/product scoping, effective date range) are consulted
**only as a fallback** — for whichever fee columns a given CSV export leaves
blank. An actual figure already present in the CSV always wins; nothing
configured is ever used to override real data. Matching precedence when a
column is blank: product-specific config → category-specific config →
channel-wide config, narrowed to rows whose effective date range covers
`order_date`. No match → that fee is `0.00`.

## Execution

Runs via a Celery task (`apps/integrations/amazon/tasks.py:import_amazon_orders`),
enqueued with `transaction.on_commit` right after the uploaded
`AmazonImportBatch` row is saved — never inline on the upload request. Rows
are grouped by `order_id`; **each order commits independently** in its own
`transaction.atomic()`, so one bad order (unknown SKU, insufficient stock,
conflicting statuses across its rows) never blocks the rest of the file. The
batch ends `READY` (everything imported), `PARTIAL` (some orders failed),
or `FAILED` (nothing imported, or the file itself couldn't be read) —
`error_log` carries one entry per failed row/order.
