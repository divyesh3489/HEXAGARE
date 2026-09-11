"""``seed_demo_data`` -- populate a dev database with demo users and a demo catalog.

Idempotent: every object is matched on a natural key and only created if missing,
so the command is safe to re-run. Reference data (Locations, SalesChannels, RBAC
role groups, LabelSizes) is seeded automatically by ``post_migrate`` hooks and is
NOT touched here.

    docker compose exec backend python manage.py seed_demo_data
    make seed
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.rbac import ROLE_ADMIN, ROLE_CASHIER, ROLE_MANAGER, ROLE_WAREHOUSE
from apps.customers.models import Customer
from apps.integrations.amazon.models import AmazonFeeConfig, AmazonSkuMapping
from apps.inventory.models import Location, StockLevelPolicy
from apps.inventory.services.ledger import InventoryService
from apps.products.models import (
    Category,
    Product,
    ProductAttribute,
    ProductAttributeValue,
    ProductVariant,
)
from apps.products.services.serial_numbers import create_unit
from apps.purchases.models import PurchaseOrder, PurchaseOrderLine
from apps.purchases.services import PurchaseTotalsService, ReceiveStockService
from apps.sales.models import Sale, SaleLine, SalesChannel
from apps.sales.services.totals import SalesTotalsService
from apps.suppliers.models import Supplier

User = get_user_model()

DEFAULT_PASSWORD = "demo-Passw0rd!"  # noqa: S105 -- dev-only fixture credential

# email -> (role group, is_staff, is_superuser)
DEMO_USERS = {
    "admin@hexagare.test": (ROLE_ADMIN, True, True),
    "manager@hexagare.test": (ROLE_MANAGER, True, False),
    "cashier@hexagare.test": (ROLE_CASHIER, False, False),
    "warehouse@hexagare.test": (ROLE_WAREHOUSE, False, False),
}

# code -> (name, parent code or None)
DEMO_CATEGORIES = [
    ("PER", "Peripherals", None),
    ("MP", "Mouse Pads", "PER"),
    ("KB", "Keyboards", "PER"),
    ("DM", "Desk Mats", "PER"),
]

# code -> name
DEMO_ATTRIBUTES = {
    "size": "Size",
    "colour": "Colour",
    "switch": "Switch",
}

# Pricing lives on the product as a default; a variant only lists price keys when
# it overrides one (see ADR-005). ``discount`` is derived, never seeded.
DEMO_PRODUCTS = [
    {
        "name": "Hexagare Mouse Pad",
        "category": "MP",
        "brand": "Hexagare",
        "status": Product.Status.ACTIVE,
        "hsn_sac": "3926",
        "tags": ["cloth", "stitched-edge"],
        "pricing": {
            "mrp": "1500.00",
            "selling_price": "1180.00",
            "purchase_price": "640.00",
            "tax_rate": "18.00",
        },
        "variants": [
            {
                "sku": "HEX-MP-11X23-001",
                "name": "11 x 23 inch",
                "code": "11X23",
                "attrs": {"size": "11 x 23 inch"},
            },
            {
                "sku": "HEX-MP-12X32-001",
                "name": "12 x 32 inch",
                "code": "12X32",
                # larger pad -- overrides the product default
                "pricing": {
                    "mrp": "2200.00",
                    "selling_price": "1770.00",
                    "purchase_price": "980.00",
                },
                "attrs": {"size": "12 x 32 inch"},
            },
        ],
    },
    {
        "name": "Hexagare Desk Mat XL",
        "category": "DM",
        "brand": "Hexagare",
        "status": Product.Status.ACTIVE,
        "hsn_sac": "3926",
        "tags": ["xl", "water-resistant"],
        "pricing": {
            "mrp": "2500.00",
            "selling_price": "1999.00",
            "purchase_price": "1100.00",
            "tax_rate": "18.00",
        },
        "variants": [
            {
                "sku": "HEX-DM-BLACK-001",
                "name": "Black",
                "code": "BLACK",
                "attrs": {"colour": "Black"},
            },
            {
                "sku": "HEX-DM-GREY-001",
                "name": "Grey",
                "code": "GREY",
                "attrs": {"colour": "Grey"},
            },
        ],
    },
    {
        "name": "Hexagare Mechanical Keyboard",
        "category": "KB",
        "brand": "Hexagare",
        "status": Product.Status.DRAFT,
        "hsn_sac": "8471",
        "tags": ["hot-swap", "75-percent"],
        "pricing": {
            "mrp": "6500.00",
            "selling_price": "5499.00",
            "purchase_price": "3200.00",
            "tax_rate": "18.00",
        },
        "variants": [
            {
                "sku": "HEX-KB-RED-001",
                "name": "Red switch",
                "code": "RED",
                "attrs": {"switch": "Linear Red"},
            },
            {
                "sku": "HEX-KB-BROWN-001",
                "name": "Brown switch",
                "code": "BROWN",
                "attrs": {"switch": "Tactile Brown"},
            },
        ],
    },
]

# A handful of serialized units so the Product Unit list isn't empty in dev.
# (sku, location code, [initial status per unit]). Bulk generation is Phase 5;
# this is deliberately tiny. Skipped for any variant that already has units.
DEMO_UNITS = [
    ("HEX-MP-11X23-001", "warehouse", ["AVAILABLE", "AVAILABLE", "GENERATED"]),
    ("HEX-MP-12X32-001", "warehouse", ["AVAILABLE", "AVAILABLE"]),
    ("HEX-DM-BLACK-001", "amazon", ["AVAILABLE", "AVAILABLE"]),
]

# (sku, location code or None for all-locations, min, max) -- so the alerts
# panel isn't empty in dev. The 11x23 pad has 2 available against a min of 5,
# so it shows as a low-stock alert.
DEMO_STOCK_POLICIES = [
    ("HEX-MP-11X23-001", None, 5, 40),
    ("HEX-MP-12X32-001", None, 1, 20),
    ("HEX-DM-BLACK-001", "amazon", 1, 10),
]

# One registered, one walk-in -- shows both Customer.type values in the list.
DEMO_CUSTOMERS = [
    {
        "name": "Rahul Sharma",
        "phone": "+91-98765-43210",
        "email": "rahul.sharma@example.com",
        "type": Customer.Type.REGISTERED,
    },
    {
        "name": "Walk-in — Counter",
        "phone": "",
        "email": "",
        "type": Customer.Type.WALK_IN,
    },
]

# A couple of demo orders so the Orders list isn't empty in dev. Matched on
# (channel, external_reference, note) -- unique enough for this fixed set.
DEMO_SALES = [
    {
        "channel": "OFFLINE",
        "external_reference": "",
        "note": "Demo walk-in counter sale",
        "status": Sale.Status.COMPLETED,
        "lines": [("HEX-MP-11X23-001", 1)],
        "customer_name": "Rahul Sharma",
    },
    {
        "channel": "AMAZON",
        "external_reference": "DEMO-AMZ-0001",
        "note": "",
        "status": Sale.Status.SHIPPED,
        "lines": [("HEX-DM-BLACK-001", 2)],
        "customer_name": None,
    },
]


class Command(BaseCommand):
    help = "Seed the database with demo users and a demo catalog (idempotent)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help=f"Password for newly created demo users (default: {DEFAULT_PASSWORD!r}).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Required to run when DJANGO_ENV is staging or production.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        env = getattr(settings, "DJANGO_ENV", "development")
        if env in {"staging", "production"} and not options["force"]:
            raise CommandError(
                f"Refusing to seed demo data with DJANGO_ENV={env!r}. Pass --force to override."
            )

        password = options["password"]
        users = self._seed_users(password)
        categories = self._seed_categories()
        attributes = self._seed_attributes()
        products, variants = self._seed_catalog(categories, attributes)
        units = self._seed_units()
        policies = self._seed_stock_policies()
        # The opening ledger rows are written as each unit is created; this only
        # matters if units pre-date the Phase 4 migration on an existing DB.
        InventoryService.rebuild_balances()
        customers = self._seed_customers()
        sales = self._seed_sales()
        amazon = self._seed_amazon_integration()
        purchases = self._seed_suppliers_and_purchases()

        self.stdout.write(self.style.SUCCESS("Demo data ready:"))
        rows = [
            ("users", users),
            ("categories", categories),
            ("attributes", attributes),
            ("products", products),
            ("variants", variants),
            ("units", units),
            ("stock policies", policies),
            ("customers", customers),
            ("sales", sales),
            ("amazon integration", amazon),
            ("suppliers/purchases", purchases),
        ]
        for label, counts in rows:
            self.stdout.write(
                f"  {label:<12} {counts['created']} created, {counts['existing']} existing"
            )
        self.stdout.write("")
        self.stdout.write("Sign in with any of:")
        for email in DEMO_USERS:
            self.stdout.write(f"  {email} / {password}")

    # -- users -------------------------------------------------------------
    def _seed_users(self, password: str) -> dict[str, int]:
        """Create the four demo accounts, or realign existing ones.

        These are fixed ``@hexagare.test`` fixtures, not real accounts, so every
        run resets their password, flags and role membership -- the point of
        ``make seed`` is a predictable set of logins.
        """
        created = existing = 0
        for email, (role, is_staff, is_superuser) in DEMO_USERS.items():
            user, was_created = User.objects.get_or_create(email=email)
            user.is_staff = is_staff
            user.is_superuser = is_superuser
            user.is_active = True
            user.first_name = role
            user.last_name = "(demo)"
            user.set_password(password)
            user.save()
            created += was_created
            existing += not was_created
            group = Group.objects.filter(name=role).first()
            if group is not None:
                user.groups.add(group)
        return {"created": created, "existing": existing}

    # -- categories ------------------------------------------------------
    def _seed_categories(self) -> dict:
        result = {"created": 0, "existing": 0, "by_code": {}}
        for code, name, parent_code in DEMO_CATEGORIES:
            parent = result["by_code"].get(parent_code) if parent_code else None
            category, was_created = Category.objects.get_or_create(
                name=name,
                defaults={"code": code, "parent": parent, "is_active": True},
            )
            if was_created:
                result["created"] += 1
            else:
                result["existing"] += 1
            result["by_code"][code] = category
        return result

    # -- attributes ----------------------------------------------------
    def _seed_attributes(self) -> dict:
        result = {"created": 0, "existing": 0, "by_code": {}}
        for code, name in DEMO_ATTRIBUTES.items():
            attribute, was_created = ProductAttribute.objects.get_or_create(
                code=code, defaults={"name": name, "is_active": True}
            )
            result["created" if was_created else "existing"] += 1
            result["by_code"][code] = attribute
        return result

    # -- catalog -----------------------------------------------------
    def _seed_catalog(self, categories: dict, attributes: dict) -> tuple[dict, dict]:
        prod = {"created": 0, "existing": 0}
        var = {"created": 0, "existing": 0}
        for spec in DEMO_PRODUCTS:
            product, was_created = Product.objects.get_or_create(
                name=spec["name"],
                defaults={
                    "category": categories["by_code"][spec["category"]],
                    "brand": spec["brand"],
                    "status": spec["status"],
                    "hsn_sac": spec["hsn_sac"],
                    "tags": spec["tags"],
                    **{k: Decimal(v) for k, v in spec["pricing"].items()},
                },
            )
            prod["created" if was_created else "existing"] += 1

            for vspec in spec["variants"]:
                defaults = {
                    "product": product,
                    "name": vspec["name"],
                    "code": vspec["code"],
                }
                defaults.update(
                    {k: Decimal(v) for k, v in vspec.get("pricing", {}).items()}
                )
                variant, v_created = ProductVariant.objects.get_or_create(
                    sku=vspec["sku"], defaults=defaults
                )
                var["created" if v_created else "existing"] += 1
                for attr_code, value in vspec["attrs"].items():
                    ProductAttributeValue.objects.update_or_create(
                        variant=variant,
                        attribute=attributes["by_code"][attr_code],
                        defaults={"value": value},
                    )
        return prod, var

    # -- serialized units --------------------------------------------
    def _seed_units(self) -> dict:
        """Create a few demo units per variant. Idempotent: a variant that
        already has any unit is left untouched (serials are never reused)."""
        result = {"created": 0, "existing": 0}
        for sku, location_code, statuses in DEMO_UNITS:
            variant = ProductVariant.objects.filter(sku=sku).first()
            location = Location.objects.filter(code=location_code).first()
            if variant is None or location is None:
                continue
            if variant.serialized_units.exists():
                result["existing"] += variant.serialized_units.count()
                continue
            for status in statuses:
                create_unit(variant=variant, location=location, status=status)
                result["created"] += 1
        return result

    # -- stock level policies --------------------------------------
    def _seed_stock_policies(self) -> dict:
        result = {"created": 0, "existing": 0}
        for sku, location_code, minimum, maximum in DEMO_STOCK_POLICIES:
            variant = ProductVariant.objects.filter(sku=sku).first()
            if variant is None:
                continue
            location = (
                Location.objects.filter(code=location_code).first() if location_code else None
            )
            _, created = StockLevelPolicy.objects.get_or_create(
                variant=variant,
                location=location,
                defaults={"min_quantity": minimum, "max_quantity": maximum},
            )
            result["created" if created else "existing"] += 1
        return result

    # -- customers -------------------------------------------------------
    def _seed_customers(self) -> dict:
        result = {"created": 0, "existing": 0}
        for spec in DEMO_CUSTOMERS:
            _, created = Customer.objects.get_or_create(
                name=spec["name"],
                defaults={
                    "phone": spec["phone"],
                    "email": spec["email"],
                    "type": spec["type"],
                },
            )
            result["created" if created else "existing"] += 1
        return result

    # -- sales / orders ------------------------------------------------
    def _seed_sales(self) -> dict:
        """A couple of demo orders across both channels, one per DEMO_SALES
        entry. Pricing is snapshotted from the variant, same as the API."""
        result = {"created": 0, "existing": 0}
        for spec in DEMO_SALES:
            channel = SalesChannel.objects.filter(code=spec["channel"]).first()
            if channel is None:
                continue
            customer = None
            if spec.get("customer_name"):
                customer = Customer.objects.filter(name=spec["customer_name"]).first()
            sale, created = Sale.objects.get_or_create(
                sales_channel=channel,
                external_reference=spec["external_reference"],
                note=spec["note"],
                defaults={"status": spec["status"], "customer": customer},
            )
            if not created:
                result["existing"] += 1
                continue
            for sku, quantity in spec["lines"]:
                variant = ProductVariant.objects.filter(sku=sku).first()
                if variant is None:
                    continue
                SaleLine.objects.create(
                    sale=sale,
                    variant=variant,
                    quantity=quantity,
                    unit_price=variant.effective_selling_price,
                    tax_rate=variant.effective_tax_rate,
                )
            SalesTotalsService.recalculate(sale)
            result["created"] += 1
        return result

    # -- Amazon integration (Phase 9) ------------------------------------
    def _seed_amazon_integration(self) -> dict:
        """A demo SKU mapping and a global referral-fee rule so the Import
        page has something to show without an operator configuring it first."""
        result = {"created": 0, "existing": 0}

        variant = ProductVariant.objects.filter(sku="HEX-DM-BLACK-001").first()
        if variant is not None:
            _, created = AmazonSkuMapping.objects.get_or_create(
                amazon_sku="AMZ-DM-BLACK", defaults={"variant": variant}
            )
            result["created" if created else "existing"] += 1

        channel = SalesChannel.objects.filter(code="AMAZON").first()
        if channel is not None:
            _, created = AmazonFeeConfig.objects.get_or_create(
                fee_name=AmazonFeeConfig.FeeName.REFERRAL,
                sales_channel=channel,
                applicable_category=None,
                applicable_product=None,
                defaults={
                    "fee_type": AmazonFeeConfig.FeeType.PERCENTAGE,
                    "value": Decimal("15.00"),
                    "effective_from": "2020-01-01",
                },
            )
            result["created" if created else "existing"] += 1
        return result

    # -- suppliers / purchases (Phase 12) --------------------------------
    def _seed_suppliers_and_purchases(self) -> dict:
        """One demo supplier and a partially-received purchase order, so the
        Purchases pages have something to show out of the box."""
        result = {"created": 0, "existing": 0}

        supplier, created = Supplier.objects.get_or_create(
            name="BrightPack Traders",
            defaults={
                "company": "BrightPack Traders Pvt Ltd",
                "phone": "+91-90000-11111",
                "email": "sales@brightpack.example",
                "gstin": "27AAAAA0000A1Z5",
                "payment_terms": "Net 30",
            },
        )
        result["created" if created else "existing"] += 1

        variant = ProductVariant.objects.filter(sku="HEX-MP-11X23-001").first()
        warehouse = Location.objects.filter(code="warehouse").first()
        if variant is None or warehouse is None:
            return result

        order, order_created = PurchaseOrder.objects.get_or_create(
            supplier=supplier,
            reference="PO-DEMO-0001",
            defaults={"status": PurchaseOrder.Status.DRAFT},
        )
        result["created" if order_created else "existing"] += 1
        if order_created:
            line = PurchaseOrderLine.objects.create(
                purchase_order=order,
                variant=variant,
                quantity_ordered=20,
                unit_price=Decimal("450.00"),
                tax_rate=variant.effective_tax_rate,
            )
            PurchaseTotalsService.recalculate(order)
            order.status = PurchaseOrder.Status.ORDERED
            order.save(update_fields=["status", "updated_at"])
            ReceiveStockService.receive(
                order, receipts=[{"line": line, "quantity": 15, "location": warehouse}]
            )
        return result
