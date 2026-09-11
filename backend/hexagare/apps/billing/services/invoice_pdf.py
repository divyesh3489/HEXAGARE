"""Invoice PDF rendering (Phase 8).

``build_invoice_pdf(invoice)`` lays out an A4 GST invoice: header, invoice
number/date/channel, one row per sale line with its serial number(s), and the
taxable value / CGST / SGST / total breakdown from HEXAGARE_FEATURES.md
section 28's own example. ReportLab, not WeasyPrint -- same rationale as
``apps.products.services.labels`` (ADR-010): pure-Python, no extra system
libraries in the slim backend image.

**CGST/SGST only, no IGST** (ADR-013) -- inter-state detection needs a
customer/business "place of supply", which doesn't exist until
``apps.customers`` (Phase 11). Documented simplification, not an oversight.

Called only from ``apps.billing.tasks.render_invoice_pdf``.
"""

from __future__ import annotations

from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

_MARGIN = 18 * mm
_HEADER = "HEXAGARE"


def _line_rows(sale) -> list[list[str]]:
    rows = []
    for line in sale.lines.select_related("variant__product").prefetch_related(
        "units__serialized_unit"
    ):
        serials = ", ".join(u.serialized_unit.serial_number for u in line.units.all())
        rows.append(
            [
                line.variant.product.name,
                line.variant.sku,
                serials or "-",
                str(line.quantity),
                f"{line.taxable_value}",
                f"{line.cgst_amount}",
                f"{line.sgst_amount}",
                f"{line.net_amount}",
            ]
        )
    return rows


def build_invoice_pdf(invoice) -> bytes:
    sale = invoice.sale
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(invoice.invoice_number)
    page_w, page_h = A4
    x = _MARGIN
    y = page_h - _MARGIN

    c.setFont("Helvetica-Bold", 16)
    c.drawString(x, y, _HEADER)
    c.setFont("Helvetica", 9)
    c.drawRightString(page_w - _MARGIN, y, invoice.invoice_number)
    y -= 14
    c.drawRightString(
        page_w - _MARGIN, y, invoice.created_at.strftime("%d %b %Y, %H:%M")
    )
    y -= 6
    c.line(x, y, page_w - _MARGIN, y)
    y -= 16

    c.setFont("Helvetica", 10)
    c.drawString(x, y, f"Channel: {sale.sales_channel.name}")
    y -= 14
    order_line = f"Order: #{sale.pk}"
    if sale.external_reference:
        order_line += f" ({sale.external_reference})"
    c.drawString(x, y, order_line)
    y -= 20

    headers = ["Product", "SKU", "Serial(s)", "Qty", "Taxable", "CGST", "SGST", "Total"]
    col_w = [130, 65, 105, 25, 55, 45, 45, 55]
    c.setFont("Helvetica-Bold", 8)
    cx = x
    for header, w in zip(headers, col_w, strict=False):
        c.drawString(cx, y, header)
        cx += w
    y -= 4
    c.line(x, y, page_w - _MARGIN, y)
    y -= 12

    c.setFont("Helvetica", 8)
    for row in _line_rows(sale):
        if y < _MARGIN + 80:
            c.showPage()
            y = page_h - _MARGIN
            c.setFont("Helvetica", 8)
        cx = x
        for value, w in zip(row, col_w, strict=False):
            c.drawString(cx, y, str(value)[: max(1, w // 5)])
            cx += w
        y -= 13

    y -= 10
    c.line(x, y, page_w - _MARGIN, y)
    y -= 16

    c.setFont("Helvetica", 10)
    for label, value in [
        ("Taxable value", invoice.subtotal - invoice.discount_total),
        ("Discount", invoice.discount_total),
        ("Tax (CGST + SGST)", invoice.tax_total),
        ("Grand total", invoice.grand_total),
    ]:
        c.drawRightString(page_w - _MARGIN - 120, y, label)
        c.drawRightString(page_w - _MARGIN, y, f"Rs {value}")
        y -= 14

    y -= 10
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(page_w - _MARGIN - 120, y, "Amount paid")
    c.drawRightString(page_w - _MARGIN, y, f"Rs {invoice.amount_paid}")
    y -= 14
    balance = invoice.balance_due
    if balance != 0:
        c.setFont("Helvetica", 9)
        c.drawRightString(page_w - _MARGIN - 120, y, "Balance due")
        c.drawRightString(page_w - _MARGIN, y, f"Rs {balance}")

    c.showPage()
    c.save()
    return buffer.getvalue()


__all__ = ["build_invoice_pdf"]
