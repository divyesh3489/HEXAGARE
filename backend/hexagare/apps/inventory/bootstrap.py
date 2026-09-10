"""Seed the reference locations on every ``migrate``.

Wired to ``post_migrate`` in :mod:`apps.inventory.apps`. Idempotent -- keyed on
``Location.code`` so re-running only fills gaps and refreshes ``kind``. The set
is deliberately small (Warehouse / Amazon / Offline); everything else is added
by the business.
"""

from __future__ import annotations

DEFAULT_LOCATIONS = [
    {"code": "warehouse", "name": "Warehouse", "kind": "warehouse"},
    {"code": "amazon", "name": "Amazon", "kind": "marketplace"},
    {"code": "offline", "name": "Offline", "kind": "retail"},
]


def seed_locations(**kwargs) -> None:
    from django.db import connection

    from .models import Location

    # Guard against being called before this app's table exists (e.g. a
    # ``migrate`` run while 0001_initial is still unapplied).
    if Location._meta.db_table not in connection.introspection.table_names():
        return

    for spec in DEFAULT_LOCATIONS:
        Location.objects.update_or_create(
            code=spec["code"],
            defaults={"name": spec["name"], "kind": spec["kind"]},
        )
