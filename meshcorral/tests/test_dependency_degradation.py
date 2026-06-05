"""Routing and enqueue degradation when native dependencies are missing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QSettings

from meshcorral.app.bridge.bridge_backpressure import BridgeEnqueueReject
from meshcorral.app.bridge.job_origin import JobOrigin
from meshcorral.models.file_record import FileRecord
from meshcorral.services.environment.native_renderer_health import (
    NativeRendererHealth,
    reset_native_renderer_health_cache,
)
from meshcorral.services.settings_service import SettingsService
from meshcorral.services.thumbnails.native_thumbnail_queue import NativeEnqueueReject
from meshcorral.services.thumbnails.thumbnail_routing_policy import (
    ThumbnailManualOverride,
    route_thumbnail,
)
from meshcorral.ui.footer_status import status_native_thumbnails_blender_fallback
from meshcorral.ui.main_window import MainWindow


def _unavailable_health() -> NativeRendererHealth:
    return NativeRendererHealth(
        available=False,
        missing_dependencies=("numpy",),
        detail="missing numpy",
        checked_at=0.0,
        can_render_stl_obj=False,
        fallback_backend="blender",
    )


def _rec(name: str = "part.stl") -> FileRecord:
    p = Path(f"C:/work/{name}")
    return FileRecord(
        path=p,
        name=name,
        extension=".stl",
        parent_folder="work",
        size_bytes=1024,
        modified_time=0.0,
    )


class TestRoutingDegradation(unittest.TestCase):
    """STL/OBJ route to Blender when native deps are missing."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        ini = Path(self._tmp.name) / "degrade.ini"
        self.settings = SettingsService(QSettings(str(ini), QSettings.Format.IniFormat))
        self.health = _unavailable_health()

    def tearDown(self) -> None:
        self._tmp.cleanup()
        reset_native_renderer_health_cache()

    def test_stl_routes_blender_when_native_unavailable(self) -> None:
        with patch(
            "meshcorral.services.thumbnails.thumbnail_routing_policy.find_blender_executable",
            return_value=Path("C:/Blender/blender.exe"),
        ):
            plan = route_thumbnail(
                Path("C:/a/part.stl"),
                self.settings,
                native_health=self.health,
            )
        self.assertEqual(plan.backend, "blender")
        self.assertIn("NumPy", plan.fallback_reason or "")

    def test_stl_none_when_native_and_blender_unavailable(self) -> None:
        with patch(
            "meshcorral.services.thumbnails.thumbnail_routing_policy.find_blender_executable",
            return_value=None,
        ):
            plan = route_thumbnail(
                Path("C:/a/part.stl"),
                self.settings,
                native_health=self.health,
            )
        self.assertEqual(plan.backend, "none")
        self.assertIn("NumPy", plan.reason)

    def test_route_never_native_when_health_unavailable(self) -> None:
        with patch(
            "meshcorral.services.thumbnails.thumbnail_routing_policy.find_blender_executable",
            return_value=Path("C:/Blender/blender.exe"),
        ):
            plan = route_thumbnail(
                Path("C:/a/part.stl"),
                self.settings,
                native_health=self.health,
            )
        self.assertNotEqual(plan.backend, "native")

    def test_footer_copy_matches_health(self) -> None:
        self.assertEqual(
            status_native_thumbnails_blender_fallback(),
            _unavailable_health().footer_blender_fallback_message,
        )

    def test_manual_native_blocked_when_unavailable(self) -> None:
        plan = route_thumbnail(
            Path("C:/a/part.stl"),
            self.settings,
            manual_override=ThumbnailManualOverride.NATIVE,
            native_health=self.health,
        )
        self.assertEqual(plan.backend, "none")
        self.assertIn("unavailable", plan.reason.lower())


class TestEnqueueDegradation(unittest.TestCase):
    """MainWindow enqueue must not call native queue when deps are missing."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        ini = Path(self._tmp.name) / "enqueue.ini"
        self.settings = SettingsService(QSettings(str(ini), QSettings.Format.IniFormat))
        self.settings.set_thumbnail_renderer_preference(SettingsService.THUMBNAIL_RENDERER_AUTO)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_auto_stl_uses_blender_not_native_when_unavailable(self) -> None:
        window = MagicMock()
        window._settings_service = self.settings
        window._native_renderer_health = _unavailable_health()
        window._native_degraded_footer_shown = False
        window._thumb_controller = MagicMock()
        window._thumb_controller.paint_diagnostics.return_value = MagicMock()
        window._native_thumb_queue = MagicMock()
        window._bridge_queue = MagicMock()
        window._bridge_queue.try_enqueue_thumbnail.return_value = (
            True,
            "",
            BridgeEnqueueReject.OK,
        )
        window._native_job_origins = {}
        window._map_native_reject = MainWindow._map_native_reject
        window._show_native_degraded_footer_once = MagicMock()
        window.statusBar = MagicMock(return_value=MagicMock())

        with patch(
            "meshcorral.services.thumbnails.thumbnail_routing_policy.find_blender_executable",
            return_value=Path("C:/Blender/blender.exe"),
        ):
            ok, _msg, reject = MainWindow._try_enqueue_thumbnail_record(
                window,
                _rec(),
                origin=JobOrigin.BACKGROUND_AUTO,
                for_auto_enqueue=True,
            )

        self.assertTrue(ok)
        self.assertEqual(reject, BridgeEnqueueReject.OK)
        window._native_thumb_queue.try_enqueue_native.assert_not_called()
        window._bridge_queue.try_enqueue_thumbnail.assert_called_once()

    def test_degraded_footer_shown_once(self) -> None:
        window = MagicMock()
        window._native_renderer_health = _unavailable_health()
        window._native_degraded_footer_shown = False
        sb = MagicMock()
        window.statusBar = MagicMock(return_value=sb)

        MainWindow._show_native_degraded_footer_once(window)
        MainWindow._show_native_degraded_footer_once(window)

        self.assertTrue(window._native_degraded_footer_shown)
        sb.showMessage.assert_called_once()

    def test_native_queue_rejects_when_unavailable(self) -> None:
        from meshcorral.services.thumbnails.thumbnail_router import ThumbnailRouter

        router = ThumbnailRouter(self.settings)
        with patch(
            "meshcorral.services.thumbnails.native_thumbnail_queue.get_native_renderer_health",
            return_value=_unavailable_health(),
        ):
            from meshcorral.services.thumbnails.native_thumbnail_queue import (
                NativeThumbnailQueueManager,
            )

            queue = NativeThumbnailQueueManager(router)
            ok, msg, reject = queue.try_enqueue_native(Path("C:/a/part.stl"))
        self.assertFalse(ok)
        self.assertEqual(reject, NativeEnqueueReject.UNAVAILABLE)
        self.assertIn("NumPy", msg)


if __name__ == "__main__":
    unittest.main()
