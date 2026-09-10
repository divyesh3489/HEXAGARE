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

---

## ADR-003 — Role → permission-name-set RBAC on Django Groups/Permissions

**Status:** Accepted (Phase 1)

**Context.** Hexagare needs action-level permissions (POS, returns, stock
adjustments, receiving, settings, …) across ~13 domain apps, most not built yet.
Users are assigned a job role, not individual permissions. We want role
definitions in one reviewable place, per-action gating in viewsets, and no
custom permission tables to keep in sync with Django's auth system.

**Decision.** `apps/accounts/rbac.py` is the single source of truth:
`OPERATIONAL_PERMISSIONS` maps every action codename to a label (codenames for
unbuilt features are reserved now so roles stay stable); `ROLE_PERMISSIONS` maps
each of the four seed roles (Admin, Manager, Cashier, Warehouse) to a set of
those codenames. `ensure_role_groups()` materializes each codename as a Django
`Permission` and each role as a `Group` with the matching permission set, and
runs from a `post_migrate` hook so it is reapplied on every `migrate`. The
permissions are anchored to a dedicated unmanaged `OperationalPermission` model's
content type, so they resolve as `accounts.<codename>` and never collide with
the model CRUD permissions Django auto-creates (pruning stale operational
permissions is therefore safe). Enforcement is
`apps/accounts/permissions.py:HasOperationalPermission` (+ a `require(...)`
factory); multi-action viewsets gate per action via `get_permissions()`.

**Consequences.** Roles are one dict to review and diff. RBAC state is standard
`auth.Group` / `auth.Permission` rows — `user.has_perm("accounts.pos")`,
`request.user.get_all_permissions()`, and the admin all work unchanged.
`post_migrate` keeps environments converged with zero manual steps. Superusers
bypass all checks (Django default). Trade-offs: no object-level / row-scoped
permissions (add later if needed), no per-user grants outside a role (supported
by Django but not modelled here), and adding a permission means editing
`rbac.py` and migrating. Assigning users to roles/groups is manual until the
Phase 17 settings UI. (The Phase 7 prompt's passing reference to "ADR-003" for
sales-channel extensibility predates this entry; that decision will take the
next free number when Phase 7 lands.)
