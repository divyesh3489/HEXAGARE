"""``rebuild_inventory_balances`` -- rebuild the :class:`InventoryBalance` cache
from the authoritative serialized-unit counts (plus non-serialized adjustments).

Run this after the ledger-free ``POST /products/serialized-units/{id}/transition/``
endpoint has been used on a unit, or any time the ``/inventory/overview/``
endpoint reports ``cache_matches: false``.

    docker compose exec backend python manage.py rebuild_inventory_balances
    docker compose exec backend python manage.py rebuild_inventory_balances --variant 12
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.inventory.services.ledger import InventoryService
from apps.products.models import ProductVariant


class Command(BaseCommand):
    help = "Rebuild the InventoryBalance cache from the serialized units."

    def add_arguments(self, parser):
        parser.add_argument(
            "--variant",
            type=int,
            default=None,
            help="Rebuild only this variant's balances (default: all).",
        )

    def handle(self, *args, **options):
        variant = None
        if options["variant"] is not None:
            variant = ProductVariant.objects.get(pk=options["variant"])

        written = InventoryService.rebuild_balances(variant=variant)
        scope = f"variant {variant.sku}" if variant else "all variants"
        self.stdout.write(self.style.SUCCESS(f"Rebuilt {written} balance row(s) for {scope}."))
