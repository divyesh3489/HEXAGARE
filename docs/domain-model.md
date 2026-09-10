# Domain Model

> Stub created in Phase 0. Each phase adds its section here as the models land.

## Accounts / RBAC
_Not yet built (Phase 1)._ Custom `User`, JWT auth, roles → permission-name sets
in `apps/accounts/rbac.py`.

## Catalog
_Not yet built (Phase 2)._ `Category` → `Product` → `ProductVariant`
(SKU + pricing are columns on `ProductVariant` — see ADR-002),
`ProductAttribute` / `ProductAttributeValue`, `ProductImage`, `LabelSize`.

## Serialized units
_Not yet built (Phase 3)._ `SerializedUnit` with immutable serial number and a
required `location` FK. See `serialized-units.md`.

## Inventory
_Not yet built (Phase 4)._ `Location`, `InventoryBalance` (read cache),
`InventoryTransaction` (immutable ledger). `InventoryService` is the only writer.

## Sales and billing
_Not yet built (Phases 7-8)._ `SalesChannel`, generic `Sale` / `SaleLine`
(derived totals via `SalesTotalsService`), `Payment`, `Invoice`,
`InvoiceDelivery`.

## Integrations (Amazon)
_Not yet built (Phase 9)._ `AmazonOrderSettlement` holds channel-specific
financials, keyed `(sale, sku)`. See `amazon-order-import.md`.

## Customers / Purchases / Suppliers / Expenses / Reports / Notifications
_Not yet built (later phases)._ Scaffold apps only.
