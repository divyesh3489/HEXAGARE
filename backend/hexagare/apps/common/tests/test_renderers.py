from django.test import SimpleTestCase

from apps.common.renderers import BinaryRenderer


class BinaryRendererTests(SimpleTestCase):
    def test_bytes_pass_through_unchanged(self):
        payload = b"\x89PNG\r\n\x1a\n binary blob"
        self.assertEqual(BinaryRenderer().render(payload), payload)

    def test_none_becomes_empty_bytes(self):
        self.assertEqual(BinaryRenderer().render(None), b"")

    def test_str_is_encoded(self):
        self.assertEqual(BinaryRenderer().render("hello"), b"hello")

    def test_render_style_is_binary(self):
        self.assertEqual(BinaryRenderer.render_style, "binary")
        self.assertIsNone(BinaryRenderer.charset)
