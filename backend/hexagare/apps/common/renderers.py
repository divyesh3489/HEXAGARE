"""Renderer for raw binary responses (barcode images, label / invoice PDFs).

A view returns ``bytes`` and sets the concrete content type, e.g.::

    class BarcodeRenderer(BinaryRenderer):
        media_type = "image/png"
        format = "png"

    class BarcodePNGView(APIView):
        renderer_classes = [BarcodeRenderer]

        def get(self, request, *args, **kwargs):
            return Response(png_bytes, content_type="image/png")
"""

from rest_framework.renderers import BaseRenderer


class BinaryRenderer(BaseRenderer):
    """Passes ``bytes`` straight through untouched.

    Subclass and override ``media_type`` / ``format`` for a specific type.
    """

    media_type = "application/octet-stream"
    format = "bin"
    charset = None
    render_style = "binary"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        if data is None:
            return b""
        if isinstance(data, str):
            return data.encode(self.charset or "utf-8")
        return data
