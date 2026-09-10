"""Seed the Phase 4 ledger for serialized units that already existed.

Phase 3 created ``SerializedUnit`` rows (and moved them with the ledger-free
``transition`` endpoint) before any ``InventoryTransaction`` existed. This
migration gives each such unit a single ``OPENING`` ledger row at its *current*
status / location and rebuilds :class:`InventoryBalance` from the live unit
counts, so the cache is correct from the moment Phase 4 ships.

Historical pre-Phase-4 transitions are not reconstructed as individual ledger
rows -- they were made through the path that deliberately does not touch the
ledger (see ``docs/inventory-ledger.md``). Reversible: the down migration clears
the backfilled rows and the cache.
"""

from __future__ import annotations

import uuid

from django.db import migrations


def forwards(apps, schema_editor):
    SerializedUnit = apps.get_model("products", "SerializedUnit")
    InventoryTransaction = apps.get_model("inventory", "InventoryTransaction")
    InventoryBalance = apps.get_model("inventory", "InventoryBalance")

    already_tagged = set(
        InventoryTransaction.objects.filter(serialized_unit__isnull=False).values_list(
            "serialized_unit_id", flat=True
        )
    )
    openings = [
        InventoryTransaction(
            reference=uuid.uuid4(),
            kind="OPENING",
            variant_id=unit.variant_id,
            location_id=unit.location_id,
            status=unit.status,
            quantity=1,
            serialized_unit_id=unit.id,
            note="backfilled at Phase 4",
        )
        for unit in SerializedUnit.objects.all()
        if unit.id not in already_tagged
    ]
    InventoryTransaction.objects.bulk_create(openings, batch_size=500)

    InventoryBalance.objects.all().delete()
    buckets: dict[tuple[int, int, str], int] = {}
    for unit in SerializedUnit.objects.all():
        key = (unit.variant_id, unit.location_id, unit.status)
        buckets[key] = buckets.get(key, 0) + 1
    InventoryBalance.objects.bulk_create(
        [
            InventoryBalance(
                variant_id=variant_id,
                location_id=location_id,
                status=status,
                quantity=quantity,
            )
            for (variant_id, location_id, status), quantity in buckets.items()
        ],
        batch_size=500,
    )


def backwards(apps, schema_editor):
    InventoryTransaction = apps.get_model("inventory", "InventoryTransaction")
    InventoryBalance = apps.get_model("inventory", "InventoryBalance")
    InventoryTransaction.objects.filter(note="backfilled at Phase 4").delete()
    InventoryBalance.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0002_phase4_ledger"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
