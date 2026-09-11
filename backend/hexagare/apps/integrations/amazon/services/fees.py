"""Fallback Amazon fee computation (HEXAGARE_FEATURES.md section 22).

Only consulted by
:mod:`apps.integrations.amazon.services.importer` when a CSV row leaves a fee
column blank -- an actual figure from Amazon's own report always wins.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..models import AmazonFeeConfig

_HUNDRED = Decimal("100")
_ZERO = Decimal("0.00")
_MONEY = Decimal("0.01")


def resolve_fee(
    fee_name: str,
    *,
    sales_channel_id: int,
    product,
    order_date: date,
    taxable_value: Decimal,
) -> Decimal:
    """The configured fee amount for ``fee_name`` on ``order_date``, most
    specific match wins: product-specific > category-specific >
    channel-wide. Returns ``Decimal('0.00')`` when nothing is configured."""
    base = AmazonFeeConfig.active_between(order_date).filter(
        fee_name=fee_name, sales_channel_id=sales_channel_id
    )

    config = (
        base.filter(applicable_product=product).first()
        or base.filter(
            applicable_product__isnull=True, applicable_category=product.category_id
        ).first()
        or base.filter(applicable_product__isnull=True, applicable_category__isnull=True).first()
    )
    if config is None:
        return _ZERO
    if config.fee_type == AmazonFeeConfig.FeeType.PERCENTAGE:
        return (taxable_value * config.value / _HUNDRED).quantize(_MONEY)
    return config.value


__all__ = ["resolve_fee"]
