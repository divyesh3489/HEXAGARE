"""Seed reference data for the catalog on every ``migrate``.

Wired to ``post_migrate`` in ``apps.products.apps``. Idempotent -- keyed on
``LabelSize.code`` so re-running only fills gaps and refreshes dimensions.
"""

from __future__ import annotations

from decimal import Decimal

# A small starter set. Businesses add their own via the API / admin.
DEFAULT_LABEL_SIZES = [
    {
        "code": "a4-24up",
        "name": "A4 sheet - 24 labels (3 x 8)",
        "width_mm": Decimal("70.00"),
        "height_mm": Decimal("37.00"),
        "columns": 3,
        "rows": 8,
        "margin_mm": Decimal("8.00"),
        "gutter_mm": Decimal("2.00"),
        "orientation": "horizontal",
        "is_default": True,
    },
    {
        "code": "thermal-50x25",
        "name": "Thermal roll - 50 x 25 mm",
        "width_mm": Decimal("50.00"),
        "height_mm": Decimal("25.00"),
        "columns": 1,
        "rows": 1,
        "margin_mm": Decimal("1.00"),
        "gutter_mm": Decimal("0.00"),
        "orientation": "horizontal",
        "is_default": False,
    },
]


def seed_label_sizes(**kwargs) -> None:
    from django.db import connection

    from .models import LabelSize

    # Guard against being called before this app's tables exist (e.g. a
    # ``migrate`` run while 0001_initial is still unapplied).
    if LabelSize._meta.db_table not in connection.introspection.table_names():
        return

    for spec in DEFAULT_LABEL_SIZES:
        LabelSize.objects.update_or_create(
            code=spec["code"],
            defaults={k: v for k, v in spec.items() if k != "code"},
        )
