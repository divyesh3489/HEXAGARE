"""On-demand Code128 barcode rendering.

Barcodes are **never stored** -- a unit's barcode *is* the Code128 rendering of
its serial number, produced fresh on each request and streamed back through
``apps.common.renderers.BinaryRenderer`` (see ``docs/serialized-units.md``).
"""

from __future__ import annotations

from io import BytesIO

import barcode
from barcode.writer import ImageWriter

#: python-barcode writer options. ``write_text`` prints the human-readable
#: serial under the bars; the rest keep the PNG compact enough for a label.
_WRITER_OPTIONS = {
    "module_width": 0.25,
    "module_height": 12.0,
    "quiet_zone": 2.0,
    "font_size": 8,
    "text_distance": 3.0,
    "write_text": True,
}


def render_code128_png(data: str) -> bytes:
    """Return a PNG rendering of ``data`` as a Code128 barcode."""
    code = barcode.get("code128", data, writer=ImageWriter())
    buffer = BytesIO()
    code.write(buffer, options=_WRITER_OPTIONS)
    return buffer.getvalue()
