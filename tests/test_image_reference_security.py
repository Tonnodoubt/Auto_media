import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app.services.image import _resolve_reference_image_value


class ImageReferenceSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_reference_image_value_rejects_non_media_local_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            rogue_file = Path(tmpdir) / "secret.png"
            rogue_file.write_bytes(b"secret")

            value = await _resolve_reference_image_value(
                {"image_path": str(rogue_file)},
                AsyncMock(),
            )

        self.assertEqual(value, "")

    async def test_resolve_reference_image_value_accepts_media_relative_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            media_root = Path(tmpdir)
            media_file = media_root / "images" / "test_reference_security.png"
            media_file.parent.mkdir(parents=True, exist_ok=True)
            media_file.write_bytes(b"png-bytes")

            with patch("app.services.image.MEDIA_DIR", media_root):
                value = await _resolve_reference_image_value(
                    {"image_path": str(media_file)},
                    AsyncMock(),
                )

        self.assertTrue(value.startswith("data:image/"))

    async def test_resolve_reference_image_value_rejects_private_network_http_fetch(self):
        client = AsyncMock()
        value = await _resolve_reference_image_value(
            {"image_url": "http://192.168.1.9/internal.png"},
            client,
        )

        self.assertEqual(value, "")
        client.get.assert_not_called()

    async def test_resolve_reference_image_value_rejects_private_hostname_after_dns_resolution(self):
        client = AsyncMock()
        with patch("app.services.image._resolve_hostname_ips", new=AsyncMock(return_value=["127.0.0.1"])):
            value = await _resolve_reference_image_value(
                {"image_url": "http://host.docker.internal./internal.png"},
                client,
            )

        self.assertEqual(value, "")
        client.get.assert_not_called()
