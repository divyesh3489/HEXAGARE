"""SKU auto-suggestion.

The suggested SKU looks like ``HEX-MP-11X23-001``:

    <HEXAGARE_SKU_PREFIX>-<CATEGORY CODE>-<VARIANT FRAGMENT>-<3-digit sequence>

Suggestion is **advisory** -- the caller may accept, edit, or ignore it. The
only hard guarantee is the DB-level ``ProductVariant.sku`` unique constraint
(and the serializer's availability check); a race between two suggestions just
means the loser gets a "SKU already in use" validation error and tries again.
No advisory lock is taken here (contrast the serial-number service in Phase 3,
where the sequence itself must be gapless).
"""

from __future__ import annotations

import re

from django.conf import settings

_NON_ALNUM = re.compile(r"[^A-Z0-9]+")
_SEQ_SUFFIX = re.compile(r"-(\d{3,})$")


def _token(value: str | None, *, max_len: int = 12) -> str:
    """Uppercase, strip to ``A-Z0-9``, truncate. Empty string if nothing usable."""
    if not value:
        return ""
    return _NON_ALNUM.sub("", value.upper())[:max_len]


def _initials(value: str | None, *, max_len: int = 4) -> str:
    if not value:
        return ""
    letters = "".join(word[0] for word in re.findall(r"[A-Za-z0-9]+", value))
    return letters.upper()[:max_len]


def _category_token(category) -> str:
    if category is None:
        return ""
    return _token(getattr(category, "code", "")) or _initials(getattr(category, "name", ""))


def _variant_token(*, variant_code, product, attribute_values) -> str:
    if variant_code:
        return _token(variant_code)
    if attribute_values:
        joined = "".join(_token(v, max_len=10) for v in attribute_values if v)
        if joined:
            return joined[:16]
    if product is not None:
        return _token(getattr(product, "code", "")) or _initials(getattr(product, "name", ""))
    return ""


def _sku_prefix() -> str:
    from apps.accounts.models import BusinessSettings

    try:
        business_settings = BusinessSettings.get_solo()
    except Exception:  # noqa: BLE001 - table not migrated yet
        business_settings = None
    return (business_settings and business_settings.sku_prefix) or getattr(
        settings, "HEXAGARE_SKU_PREFIX", "HEX"
    )


def _stem(category, variant_token: str) -> str:
    parts = [_token(_sku_prefix()) or "HEX"]
    cat = _category_token(category)
    if cat:
        parts.append(cat)
    parts.append(variant_token or "V")
    return "-".join(parts)


def is_sku_available(sku: str, *, exclude_variant_id: int | None = None) -> bool:
    """True when no other ``ProductVariant`` already uses ``sku`` (case-insensitive)."""
    from apps.products.models import ProductVariant

    if not sku:
        return False
    qs = ProductVariant.objects.filter(sku__iexact=sku.strip())
    if exclude_variant_id is not None:
        qs = qs.exclude(pk=exclude_variant_id)
    return not qs.exists()


def suggest_sku(
    *,
    category=None,
    product=None,
    variant_code: str | None = None,
    attribute_values: list[str] | None = None,
) -> str:
    """Return an available SKU string built from the category + variant tokens.

    The 3-digit sequence starts one past the highest sequence already seen on a
    variant sharing the same stem, then increments until the value is free.
    """
    from apps.products.models import ProductVariant

    variant_token = _variant_token(
        variant_code=variant_code,
        product=product,
        attribute_values=attribute_values,
    )
    stem = _stem(category, variant_token)

    existing = ProductVariant.objects.filter(sku__istartswith=f"{stem}-").values_list(
        "sku", flat=True
    )
    highest = 0
    for value in existing:
        match = _SEQ_SUFFIX.search(value)
        if match:
            highest = max(highest, int(match.group(1)))

    seq = highest + 1
    while True:
        candidate = f"{stem}-{seq:03d}"
        if is_sku_available(candidate):
            return candidate
        seq += 1
