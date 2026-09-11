"""Amazon order source abstraction (Phase 9, ADR-014).

``AmazonOrderSource`` is the interface
:class:`apps.integrations.amazon.services.importer.AmazonOrderImportService`
depends on -- a CSV implementation ships now; a future SP-API adapter
implements the same interface and needs no change to the importer.

See ``docs/amazon-order-import.md`` for the exact CSV column list, formats,
and per-line-total vs. per-unit conventions.
"""

from __future__ import annotations

import csv
import io
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import IO

#: Every row must supply these columns.
REQUIRED_COLUMNS = (
    "order_id",
    "order_date",
    "order_status",
    "amazon_sku",
    "quantity",
    "selling_price",
)

#: CSV columns that, left blank, fall back to AmazonFeeConfig at import time.
FEE_COLUMNS = (
    "referral_fee",
    "closing_fee",
    "fulfillment_fee",
    "shipping_cost",
    "advertising_cost",
    "other_charges",
)


@dataclass(frozen=True)
class AmazonOrderRow:
    """One parsed, type-validated CSV row -- one order line.

    ``selling_price``/``gst_amount`` are **per unit**; the fee/charge fields
    (``None`` when the CSV left the column blank, meaning "compute from
    ``AmazonFeeConfig``") and ``refund_amount`` are **line totals**, matching
    how Amazon's own reports usually present them.
    """

    order_id: str
    order_date: date
    order_status: str
    amazon_sku: str
    quantity: int
    selling_price: Decimal
    gst_amount: Decimal
    refund_amount: Decimal
    referral_fee: Decimal | None
    closing_fee: Decimal | None
    fulfillment_fee: Decimal | None
    shipping_cost: Decimal | None
    advertising_cost: Decimal | None
    other_charges: Decimal | None


@dataclass(frozen=True)
class AmazonOrderRowError:
    """A row that failed to parse -- carries its 1-based source row number
    (``0`` for a file-level problem, e.g. a missing header)."""

    row_number: int
    message: str


class AmazonOrderSource(ABC):
    """Abstraction over "where Amazon order rows come from". A future SP-API
    adapter implements just this -- ``AmazonOrderImportService`` never knows
    the difference between that and a CSV file."""

    @abstractmethod
    def rows(self) -> Iterator[AmazonOrderRow | AmazonOrderRowError]:
        """Yield one entry per source row, in file order."""
        raise NotImplementedError


def _parse_decimal(raw: str, *, field: str) -> Decimal:
    try:
        return Decimal(raw.strip())
    except (InvalidOperation, AttributeError) as exc:
        raise ValueError(f"{field}: '{raw}' is not a valid number") from exc


def _parse_optional_decimal(raw: str | None, *, field: str) -> Decimal | None:
    if raw is None or raw.strip() == "":
        return None
    return _parse_decimal(raw, field=field)


class CSVAmazonOrderSource(AmazonOrderSource):
    """Parses an Amazon order-export CSV. See
    ``docs/amazon-order-import.md`` for the exact column list."""

    def __init__(self, file: IO[bytes] | IO[str]):
        self._file = file

    def rows(self) -> Iterator[AmazonOrderRow | AmazonOrderRowError]:
        raw = self._file.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(raw))

        if reader.fieldnames is None:
            yield AmazonOrderRowError(0, "The file is empty or has no header row.")
            return

        missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            yield AmazonOrderRowError(0, f"Missing required column(s): {', '.join(missing)}")
            return

        for row_number, raw_row in enumerate(reader, start=2):  # header is row 1
            try:
                yield self._parse_row(raw_row)
            except ValueError as exc:
                yield AmazonOrderRowError(row_number, str(exc))

    @staticmethod
    def _parse_row(raw_row: dict[str, str]) -> AmazonOrderRow:
        for column in REQUIRED_COLUMNS:
            if not (raw_row.get(column) or "").strip():
                raise ValueError(f"{column} is required")

        raw_date = raw_row["order_date"].strip()
        try:
            order_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
        except ValueError as exc:
            raise ValueError(f"order_date: '{raw_date}' is not YYYY-MM-DD") from exc

        raw_quantity = raw_row["quantity"].strip()
        try:
            quantity = int(raw_quantity)
        except ValueError as exc:
            raise ValueError(f"quantity: '{raw_quantity}' is not an integer") from exc
        if quantity < 1:
            raise ValueError("quantity must be at least 1")

        return AmazonOrderRow(
            order_id=raw_row["order_id"].strip(),
            order_date=order_date,
            order_status=raw_row["order_status"].strip(),
            amazon_sku=raw_row["amazon_sku"].strip(),
            quantity=quantity,
            selling_price=_parse_decimal(raw_row["selling_price"], field="selling_price"),
            gst_amount=(
                _parse_optional_decimal(raw_row.get("gst_amount"), field="gst_amount")
                or Decimal("0.00")
            ),
            refund_amount=(
                _parse_optional_decimal(raw_row.get("refund_amount"), field="refund_amount")
                or Decimal("0.00")
            ),
            referral_fee=_parse_optional_decimal(raw_row.get("referral_fee"), field="referral_fee"),
            closing_fee=_parse_optional_decimal(raw_row.get("closing_fee"), field="closing_fee"),
            fulfillment_fee=_parse_optional_decimal(
                raw_row.get("fulfillment_fee"), field="fulfillment_fee"
            ),
            shipping_cost=_parse_optional_decimal(
                raw_row.get("shipping_cost"), field="shipping_cost"
            ),
            advertising_cost=_parse_optional_decimal(
                raw_row.get("advertising_cost"), field="advertising_cost"
            ),
            other_charges=_parse_optional_decimal(
                raw_row.get("other_charges"), field="other_charges"
            ),
        )


__all__ = [
    "REQUIRED_COLUMNS",
    "FEE_COLUMNS",
    "AmazonOrderRow",
    "AmazonOrderRowError",
    "AmazonOrderSource",
    "CSVAmazonOrderSource",
]
