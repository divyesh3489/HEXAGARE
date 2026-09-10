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

---

## ADR-004 — Catalog shape: data-driven attributes, advisory SKU suggestion

**Status:** Accepted (Phase 2)

**Context.** The catalog must work for any product category, not just mouse pads.
Variants differ by size / colour / material / "whatever the next category needs",
and SKUs are auto-suggested but must stay hand-editable. Two shape questions:
where do variant properties live, and how strong is the SKU sequence guarantee?

**Decision.**
1. **Variant properties are data, not columns.** `ProductAttribute` defines a
   reusable property (Size, Colour, …); `ProductAttributeValue` is a
   `(variant, attribute) → value` row, unique per pair. No `size` / `colour`
   columns anywhere. Adding a property is a row, not a migration.
2. **Every product has ≥ 1 `ProductVariant`.** Pricing and SKU live only on the
   variant (ADR-002); a "simple" product is just a product with one variant.
   `Product` carries no price fields even though `HEXAGARE_FEATURES.md` §4 lists
   them at product level.
3. **SKU suggestion is advisory.** `apps/products/services/sku.py` builds
   `<prefix>-<category>-<fragment>-<NNN>` and increments past collisions, but
   takes **no advisory lock** (unlike the Phase 3 serial-number service, whose
   sequence must be gapless). The `ProductVariant.sku` unique constraint and the
   serializer's `is_sku_available()` check are the only hard guarantees.
4. **`LabelSize` is catalog reference data**, seeded with two defaults via a
   `post_migrate` hook (`apps/products/bootstrap.py`), matching the
   Locations / SalesChannels seeding pattern. (The Phase 2 prompt only named
   Locations / SalesChannels; this extends the same convention because Phase 5
   needs label geometries to exist.)

**Consequences.** New categories need zero schema work — define attributes, create
products, done. Reads cost a join for attribute values (mitigated by
`prefetch_related`). SKU suggestion can, in theory, race two concurrent
suggestions to the same string; the loser gets a `validation_error` and retries —
acceptable because SKUs are not sequence-critical. Promoting SKU, pricing, or
attribute values to richer entities still requires a new ADR (see ADR-002).
A partial unique constraint on `(product, variant.code)` was prototyped and
dropped: DRF's `UniqueTogetherValidator` forced `code` to be a required field and
could not express the "blank is exempt" condition; variant `code` is now just an
un-constrained SKU-building hint.

**Note.** `apps/products/urls.py` uses DRF's `SimpleRouter`, not `DefaultRouter`
(CLAUDE.md's default phrasing): `ProductViewSet` is registered at the app's root
prefix, so `DefaultRouter`'s API-root view would collide with the product list
route.

---

## ADR-005 — Product-level default pricing, nullable variant overrides, derived discount

**Status:** Accepted (Phase 2, amends ADR-002 / ADR-004)

**Context.** Most products in Hexagare's catalog carry one price across every
variant; typing MRP / selling price / purchase price / GST rate on each variant
is pure friction, and keeping them in sync by hand drifts. Separately, "discount"
had been a stored, hand-entered column that could contradict `mrp - selling_price`.

**Decision.**
1. **`Product` gains optional default pricing** — `mrp`, `selling_price`
   (GST-inclusive), `purchase_price`, `tax_rate`, all `null=True, blank=True`.
2. **`ProductVariant`'s four price columns become nullable overrides.** `NULL`
   means "inherit the product's value"; a value overrides it for that variant.
   `ProductVariant.effective_mrp` / `effective_selling_price` /
   `effective_purchase_price` / `effective_tax_rate` resolve
   *variant value → product default → `0`*. `base_price` / `gst_amount` /
   `cgst_amount` / `sgst_amount` all derive from the **effective** figures.
3. **`discount` is never stored.** Both `Product` and `ProductVariant` expose
   `discount_amount` (`max(mrp − selling_price, 0)`, 2 dp) and `discount_percent`
   (`discount_amount / mrp × 100`, `0` when MRP is missing/zero) as read-only
   properties. The `ProductVariant.discount` column is dropped
   (migration `0002`).
4. **A variant must resolve to a non-null `selling_price` and `mrp`** — the
   serializer rejects a create/update whose effective value for either is `NULL`,
   with a message pointing at "set it on the variant or the product".
5. `selling_price > mrp` is **not** rejected; `discount_amount` simply clamps to
   `0`.

**Consequences.** Price a product once, add variants with no pricing, done; a
per-variant exception is a single field. `discount` can never disagree with the
prices it's computed from. Trade-offs: a variant's effective price now depends on
its product row (loaded via `select_related` / the already-loaded parent in list
serialization — no N+1); changing a product's default price retroactively moves
every inheriting variant (intended); `HEXAGARE_FEATURES.md` §4's product-level
price fields are now honoured literally, and its §5 "Discount (Auto)" is now
actually automatic. **Phase 7's `SalesTotalsService` must read the `effective_*`
figures, not the raw override columns.** This does not reopen ADR-002 — pricing
is still plain columns, not entities; it just lives on both levels now.

---

## ADR-006 — Variant availability is derived from product status

**Status:** Accepted (Phase 2)

**Context.** `ProductVariant.is_active` was shown and treated as absolute, so a
`draft` product's variants read as "Active" — a variant can't sensibly be live
when its product isn't. Product status has four values
(`active` / `inactive` / `draft` / `discontinued`); the per-variant flag should
only matter once the product is actually published.

**Decision.** `is_active` stays as the per-variant *intent*. Two derived,
read-only properties express reality:
- `ProductVariant.effective_status` → a `Product.Status` value:
  product `active` ⇒ `active` if `is_active` else `inactive`;
  product `draft` / `inactive` / `discontinued` ⇒ that status verbatim
  (a discontinued product's variants read `discontinued`, **not** `inactive`).
- `ProductVariant.is_available` → `True` only when the product is `active` **and**
  `is_active` is `True`.

The serializer exposes both; `ProductVariant`'s list endpoint gains an
`?available=1` / `?available=0` filter
(`Q(product__status=active, is_active=True)`); `ProductListSerializer` adds
`available_variant_count` (`0` unless the product is active). The frontend shows
`effective_status`, disables the per-variant Active toggle unless the product is
`active`, and banners draft/inactive/discontinued products. No schema change —
all computed.

**Consequences.** One place decides "is this sellable"; a future POS/storefront
filters `?available=1`. Existing `is_active` values are preserved and
reinterpreted as "intended once live". A discontinued product's variants are not
individually revivable — reactivating the product restores each variant's stored
`is_active`. Nothing enforces hiding draft/inactive variants in the management
UI itself (you must be able to build a product before publishing it).
