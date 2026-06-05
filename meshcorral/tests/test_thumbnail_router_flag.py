"""Tests for native-first thumbnail routing and router selection logic."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings

from meshcorral.app.bridge.job_models import BridgeJobStatus
from meshcorral.services.settings_service import SettingsService
from meshcorral.services.thumbnails.thumbnail_router import ThumbnailRouter


class TestThumbnailRouterRouting(unittest.TestCase):
    def test_default_routes_stl_to_native(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ini = Path(td) / "router.ini"
            settings = SettingsService(QSettings(str(ini), QSettings.Format.IniFormat))
            with patch.dict("os.environ", {}, clear=True):
                router = ThumbnailRouter(settings)
                decision = router.route_for(Path("C:/tmp/mesh.stl"))
                self.assertEqual(decision.selected, "native")

    def test_native_env_disable_falls_back_to_blender(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ini = Path(td) / "router.ini"
            settings = SettingsService(QSettings(str(ini), QSettings.Format.IniFormat))
            with patch.dict("os.environ", {"ROUNDUP_NATIVE_THUMBS": "0"}, clear=True):
                router = ThumbnailRouter(settings)
                with patch(
                    "meshcorral.services.thumbnails.thumbnail_routing_policy.find_blender_executable",
                    return_value=Path("C:/Program Files/Blender/blender.exe"),
                ):
                    decision = router.route_for(Path("C:/tmp/mesh.stl"))
                self.assertEqual(decision.selected, "blender")

    def test_blender_fallback_when_native_disabled_and_no_blender(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ini = Path(td) / "router.ini"
            settings = SettingsService(QSettings(str(ini), QSettings.Format.IniFormat))
            with patch.dict("os.environ", {"ROUNDUP_NATIVE_THUMBS": "0"}, clear=True):
                router = ThumbnailRouter(settings)
                with patch(
                    "meshcorral.services.thumbnails.thumbnail_routing_policy.find_blender_executable",
                    return_value=None,
                ):
                    res = router.generate_to_cache(Path("C:/tmp/mesh.stl"))
                self.assertEqual(res.status, BridgeJobStatus.FAILED)

    def test_blender_generate_when_selected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            src = tmp / "mesh.stl"
            src.write_bytes(b"not a real mesh")
            thumb = tmp / "thumb.png"
            thumb.write_bytes(b"fakepng")

            ini = tmp / "router.ini"
            settings = SettingsService(QSettings(str(ini), QSettings.Format.IniFormat))
            router = ThumbnailRouter(settings)

            with patch(
                "meshcorral.services.thumbnails.thumbnail_routing_policy.find_blender_executable"
            ) as m_find, patch(
                "meshcorral.services.thumbnails.blender_thumbnail_backend.BlenderThumbnailBackend.generate"
            ) as m_gen:
                m_find.return_value = Path("C:/Program Files/Blender/blender.exe")
                settings.set_thumbnail_renderer_preference(
                    SettingsService.THUMBNAIL_RENDERER_BLENDER_FIRST
                )

                def _fake_generate(_p: Path, _out: Path, *, max_px: int = 512):
                    _ = max_px
                    from meshcorral.services.thumbnails.thumbnail_backend_base import (
                        ThumbnailBackendId,
                        ThumbnailResult,
                    )

                    return ThumbnailResult(
                        backend_id=ThumbnailBackendId.BLENDER,
                        source_file=_p,
                        output_dir=_out,
                        thumbnail_path=thumb,
                        ok=True,
                        error_message=None,
                        log_path=None,
                    )

                m_gen.side_effect = _fake_generate
                res = router.generate_to_cache(src)
                self.assertEqual(res.status, BridgeJobStatus.COMPLETE)


if __name__ == "__main__":
    unittest.main()
