"""Turns a report's flat ``rows`` (see ``apps.reports.services``) into
downloadable bytes. One pair of functions for every report type -- CLAUDE.md's
"shared query logic in one reports service module, not duplicated per report"
extends to export rendering too.
"""

from __future__ import annotations

import csv
import io
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font


def _stringify(value: Any) -> Any:
    """A report row can hold a ``dict`` (e.g. a status breakdown) -- flatten it
    to plain text; everything else (``Decimal``, ``date``, ``str``, ``int``) is
    left as-is for the ``csv``/``openpyxl`` writers to render natively."""
    if isinstance(value, dict):
        return ", ".join(f"{k}: {v}" for k, v in value.items())
    return value


def rows_to_csv(fieldnames: list[str], rows: list[dict]) -> bytes:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: _stringify(row.get(key)) for key in fieldnames})
    return buffer.getvalue().encode("utf-8")


def rows_to_xlsx(fieldnames: list[str], rows: list[dict], title: str = "Report") -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title[:31] or "Report"

    sheet.append(fieldnames)
    for cell in sheet[1]:
        cell.font = Font(bold=True)

    for row in rows:
        sheet.append([_stringify(row.get(key)) for key in fieldnames])

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
