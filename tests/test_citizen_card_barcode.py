from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from myapp.views import generate_barcode_image


class CitizenCardBarcodeTests(SimpleTestCase):
    def test_barcode_image_url_uses_public_base_url_from_settings(self):
        with TemporaryDirectory() as media_root:
            writer = Mock()
            writer.save.return_value = str(Path(media_root) / "barcodes" / "ABC12345678901.png")
            with override_settings(
                MEDIA_ROOT=media_root,
                MEDIA_URL="/media/",
                PUBLIC_BASE_URL="https://current-ngrok.example",
            ), patch("myapp.views.barcode.get", return_value=writer):
                url = generate_barcode_image("ABC12345678901")

        self.assertEqual(url, "https://current-ngrok.example/media/barcodes/ABC12345678901.png")
