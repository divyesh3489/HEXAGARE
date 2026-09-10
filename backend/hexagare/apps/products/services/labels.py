"""Label-sheet PDF rendering (Phase 5).

``build_label_pdf(batch)`` lays the batch's units out on a grid taken straight
from the :class:`~apps.products.models.LabelSize` (``columns`` x ``rows``,
``margin_mm``, ``gutter_mm``, per-label ``width_mm`` x ``height_mm``) and draws
one label per unit -- the "HEXAGARE" header, the optional product / variant / SKU
/ price / custom-text rows (section 11 "Label Content"), the serial number, and a
vector Code 128 barcode of that serial.

ReportLab, not WeasyPrint (ADR-010): labels are a fixed millimetre grid, not an
HTML page, and ReportLab is pure-Python so the slim backend image needs no extra
system libraries. Called only from ``apps.products.tasks.render_label_pdf``.
"""

from __future__ import annotations

from io import BytesIO

from reportlab.graphics.barcode import code128
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

_HEADER = "HEXAGARE"
_PAD = 2 * mm


def _fit(text: str, font: str, size: float, max_w: float) -> str:
    """``text`` truncated with an ellipsis so it fits ``max_w`` points."""
    if stringWidth(text, font, size) <= max_w:
        return text
    ell = "…"
    while text and stringWidth(text + ell, font, size) > max_w:
        text = text[:-1]
    return (text + ell) if text else ""


def _label_lines(batch, unit) -> list[tuple[str, str, float]]:
    """``(text, font, size)`` rows to print on the label, top to bottom."""
    v = unit.variant
    rows: list[tuple[str, str, float]] = [(_HEADER, "Helvetica-Bold", 7)]
    if batch.include_product_name:
        rows.append((v.product.name, "Helvetica", 6))
    if batch.include_variant and (v.name or v.code):
        rows.append((v.name or v.code, "Helvetica", 6))
    if batch.include_sku:
        rows.append((f"SKU: {v.sku}", "Helvetica", 5))
    if batch.include_mrp:
        rows.append((f"MRP: {v.effective_mrp}", "Helvetica", 5))
    if batch.include_selling_price:
        rows.append((f"Price: {v.effective_selling_price}", "Helvetica", 5))
    if batch.custom_text:
        rows.append((batch.custom_text, "Helvetica", 5))
    rows.append((f"Serial: {unit.serial_number}", "Helvetica", 5))
    return rows


def _draw_barcode(c, value: str, x: float, y: float, avail_w: float, height: float) -> None:
    bc = code128.Code128(value, barHeight=height, humanReadable=False)
    scale = min(1.0, avail_w / bc.width) if bc.width else 1.0
    c.saveState()
    c.translate(x, y)
    c.scale(scale, 1.0)
    bc.drawOn(c, 0, 0)
    c.restoreState()


def _draw_label(c, batch, unit, x: float, y: float, w: float, h: float, horizontal: bool) -> None:
    """One label, lower-left corner at ``(x, y)``, size ``(w, h)`` in points."""
    c.rect(x, y, w, h, stroke=1, fill=0)
    inner_w = w - 2 * _PAD
    lines = _label_lines(batch, unit)

    if horizontal:
        bc_w = inner_w * 0.45
        text_x = x + _PAD + bc_w + 2 * mm
        text_w = x + w - _PAD - text_x
        ty = y + h - _PAD
        for text, font, size in lines:
            ty -= size + 2.5
            c.setFont(font, size)
            c.drawString(text_x, ty, _fit(text, font, size, text_w))
        _draw_barcode(c, unit.serial_number, x + _PAD, y + _PAD, bc_w, h - 2 * _PAD)
    else:
        bc_h = max(8 * mm, h * 0.38)
        ty = y + h - _PAD - 6
        for text, font, size in lines:
            c.setFont(font, size)
            c.drawString(x + _PAD, ty, _fit(text, font, size, inner_w))
            ty -= size + 2.5
        _draw_barcode(c, unit.serial_number, x + _PAD, y + _PAD, inner_w, bc_h)


def build_label_pdf(batch) -> bytes:
    """Render the whole batch to PDF bytes."""
    ls = batch.label_size
    label_w, label_h = float(ls.width_mm) * mm, float(ls.height_mm) * mm
    margin = float(ls.margin_mm) * mm
    gutter = float(ls.gutter_mm) * mm
    cols = max(ls.columns, 1)
    rows = max(ls.rows, 1)
    horizontal = ls.orientation == ls.Orientation.HORIZONTAL

    # A single-label geometry (a thermal roll) is its own page size; a multi-up
    # sheet prints on A4.
    if cols == 1 and rows == 1:
        page_w, page_h = label_w + 2 * margin, label_h + 2 * margin
    else:
        page_w, page_h = A4

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(page_w, page_h))
    c.setTitle(f"Hexagare labels - batch {batch.pk}")

    units = list(batch.units.select_related("variant__product").order_by("sequence"))
    per_page = cols * rows
    for index, unit in enumerate(units):
        slot = index % per_page
        if index and slot == 0:
            c.showPage()
        col, row = slot % cols, slot // cols
        x = margin + col * (label_w + gutter)
        # ReportLab's origin is bottom-left; fill the top row of the sheet first.
        y = page_h - margin - (row + 1) * label_h - row * gutter
        _draw_label(c, batch, unit, x, y, label_w, label_h, horizontal)

    if not units:
        c.setFont("Helvetica", 10)
        c.drawString(margin, page_h - margin - 12, "No units in this batch.")

    c.showPage()
    c.save()
    return buffer.getvalue()
