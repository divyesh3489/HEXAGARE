# Architecture Decision Record (ADR) Log

Newest last. Each entry: context, decision, consequences. Add an ADR whenever a
phase makes a structural or architectural decision.

---

## ADR-001 — Modular monolith over microservices

**Status:** Accepted (Phase 0)

**Context.** Hexagare is a product / inventory / billing system for a small
business, built and operated by a very small team. The domains (catalog,
inventory, sales, billing, integrations, …) are tightly coupled: a sale touches
the inventory ledger, serialized units, invoices and payments in one atomic
transaction.

**Decision.** Build a single Django/DRF backend split into domain apps under
`backend/hexagare/apps/` (`accounts`, `products`, `inventory`, `sales`,
`billing`, `integrations`, `customers`, `purchases`, `suppliers`, `expenses`,
`reports`, `notifications`, `common`). One database, one deployable, one codebase.
Cross-app model references use string FKs to avoid circular imports. Slow or
externally-delivered work runs on Celery, not separate services.

**Consequences.** Atomic cross-domain transactions stay simple (no distributed
transactions, no eventual consistency). One migration history, one test suite,
one deploy. If a domain ever needs independent scaling it can be extracted later,
but nothing in the design should assume that. Module boundaries are enforced by
convention (put code in the app it belongs to), not by process isolation.

---

## ADR-002 — SKU and pricing as columns on `ProductVariant`, not standalone entities

**Status:** Accepted (Phase 0, to be implemented in Phase 2)

**Context.** A full catalog model could give SKU, price lists, tax rules and
cost history their own tables with effective-dated rows. Hexagare currently sells
one product family through two channels and needs current price, MRP, purchase
price and tax rate per sellable variant — nothing more.

**Decision.** `SKU` is a unique `CharField` column on `ProductVariant`.
`mrp`, `selling_price`, `purchase_price` and `tax_rate` are likewise plain
columns on `ProductVariant`. No `Sku`, `Price`, or `PriceList` entities.

**Consequences.** Simple reads and writes, one row per sellable variant, easy
SKU-uniqueness enforcement at the DB level. No historical price tracking beyond
what the audit log captures, and no per-customer or per-channel price lists.
Promoting any of these to a standalone entity requires a new ADR and a
migration; do not do it ad hoc.
