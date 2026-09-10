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
from apps.products.models import (
    Category,
    Product,
    ProductAttribute,
    ProductAttributeValue,
    ProductVariant,
)

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

        self.stdout.write(self.style.SUCCESS("Demo data ready:"))
        rows = [
            ("users", users),
            ("categories", categories),
            ("attributes", attributes),
            ("products", products),
            ("variants", variants),
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
