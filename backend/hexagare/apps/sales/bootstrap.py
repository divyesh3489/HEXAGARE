"""Seed the reference sales channels on every ``migrate``.

Wired to ``post_migrate`` in :mod:`apps.sales.apps`. Idempotent -- keyed on
``SalesChannel.code`` so re-running only fills gaps and refreshes ``name``.
Businesses add further channels (Shopify, Flipkart, ...) via the admin or the
write API -- never a code change (ADR-012).
"""

from __future__ import annotations

DEFAULT_CHANNELS = [
    {"code": "AMAZON", "name": "Amazon"},
    {"code": "OFFLINE", "name": "Offline"},
]


def seed_sales_channels(**kwargs) -> None:
    from django.db import connection

    from .models import SalesChannel

    # Guard against being called before this app's table exists (e.g. a
    # ``migrate`` run while 0001_initial is still unapplied).
    if SalesChannel._meta.db_table not in connection.introspection.table_names():
        return

    for spec in DEFAULT_CHANNELS:
        SalesChannel.objects.update_or_create(
            code=spec["code"],
            defaults={"name": spec["name"]},
        )
