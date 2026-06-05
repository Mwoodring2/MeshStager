"""Prime v1.0 — MainWindow enqueue paths must activate native routing for STL/OBJ."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QSettings

from meshcorral.app.bridge.bridge_backpressure import (
    BridgeEnqueueReject,
    enqueue_tiered_bridge_thumbnails,
)
from meshcorral.app.bridge.job_models import BridgeJobResult, BridgeJobStatus
from meshcorral.app.bridge.job_origin import JobOrigin
from meshcorral.models.file_record import FileRecord
from meshcorral.services.settings_service import SettingsService
from meshcorral.services.thumbnails.native_thumbnail_queue import NativeEnqueueReject
from meshcorral.services.thumbnails.thumbnail_routing_policy import (
    ThumbnailManualOverride,
    route_thumbnail,
)
from meshcorral.ui.main_window import MainWindow
from meshcorral.ui.thumb_paint_diagnostics import ThumbPaintDiagnostics
from meshcorral.tests.native_health_fixtures import (
    healthy_native_health,
    patch_healthy_native_routing,
)


def _rec(name: str, ext: str = ".stl") -> FileRecord:
    p = Path(f"C:/work/{name}")
    return FileRecord(
        path=p,
        name=name,
        extension=ext,
        parent_folder="work",
        size_bytes=1024,
        modified_time=0.0,
    )


def _window_stub(settings: SettingsService) -> MagicMock:
    window = MagicMock()
    window._settings_service = settings
    window._thumb_controller = MagicMock()
    window._thumb_controller.paint_diagnostics.return_value = ThumbPaintDiagnostics()
    window._native_thumb_queue = MagicMock()
    window._native_thumb_queue.try_enqueue_native.return_value = (
        True,
        "",
        NativeEnqueueReject.OK,
    )
    window._native_thumb_queue.in_flight_count.return_value = 0
    window._bridge_queue = MagicMock()
    window._bridge_queue.try_enqueue_thumbnail.return_value = (
        True,
        "",
        BridgeEnqueueReject.OK,
    )
    window._bridge_queue.in_flight_load.return_value = (0, 0)
    window._native_job_origins = {}
    window._native_renderer_health = healthy_native_health()
    window._native_degraded_footer_shown = False
    window._map_native_reject = lambda reject: MainWindow._map_native_reject(reject)
    window._show_native_degraded_footer_once = MagicMock()
    return window


class TestMainWindowTryEnqueueThumbnailRecord(unittest.TestCase):
    """Exercise MainWindow._try_enqueue_thumbnail_record routing activation."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        ini = Path(self._tmp.name) / "routing.ini"
        self.settings = SettingsService(QSettings(str(ini), QSettings.Format.IniFormat))
        self.settings.set_thumbnail_renderer_preference(SettingsService.THUMBNAIL_RENDERER_AUTO)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_auto_stl_enqueues_native_not_blender(self) -> None:
        window = _window_stub(self.settings)
        record = _rec("part.stl")

        ok, _msg, reject = MainWindow._try_enqueue_thumbnail_record(
            window,
            record,
            origin=JobOrigin.BACKGROUND_AUTO,
            for_auto_enqueue=True,
        )

        self.assertTrue(ok)
        self.assertEqual(reject, BridgeEnqueueReject.OK)
        window._native_thumb_queue.try_enqueue_native.assert_called_once()
        window._bridge_queue.try_enqueue_thumbnail.assert_not_called()
        diag = window._thumb_controller.paint_diagnostics.return_value
        self.assertEqual(diag.native_jobs_enqueued, 1)
        self.assertEqual(diag.blender_jobs_skipped_native_supported, 1)

    def test_idle_tier_skips_stl_without_blender(self) -> None:
        window = _window_stub(self.settings)
        record = _rec("part.stl")

        ok, _msg, reject = MainWindow._try_enqueue_thumbnail_record(
            window,
            record,
            origin=JobOrigin.BACKGROUND_AUTO,
            for_auto_enqueue=True,
            idle_tier=True,
        )

        self.assertFalse(ok)
        self.assertEqual(reject, BridgeEnqueueReject.NOT_ROUTED)
        window._native_thumb_queue.try_enqueue_native.assert_not_called()
        window._bridge_queue.try_enqueue_thumbnail.assert_not_called()
        diag = window._thumb_controller.paint_diagnostics.return_value
        self.assertEqual(diag.blender_jobs_skipped_native_supported, 1)

    def test_generate_missing_style_uses_native(self) -> None:
        window = _window_stub(self.settings)
        record = _rec("part.obj", ext=".obj")

        ok, _msg, reject = MainWindow._try_enqueue_thumbnail_record(
            window,
            record,
            origin=JobOrigin.MANUAL_BATCH,
            for_auto_enqueue=False,
        )

        self.assertTrue(ok)
        self.assertEqual(reject, BridgeEnqueueReject.OK)
        window._native_thumb_queue.try_enqueue_native.assert_called_once()
        window._bridge_queue.try_enqueue_thumbnail.assert_not_called()

    def test_manual_blender_override_still_uses_bridge(self) -> None:
        window = _window_stub(self.settings)
        record = _rec("part.stl")

        with patch(
            "meshcorral.services.thumbnails.thumbnail_routing_policy.find_blender_executable",
            return_value=Path("C:/Blender/blender.exe"),
        ):
            ok, _msg, reject = MainWindow._try_enqueue_thumbnail_record(
                window,
                record,
                origin=JobOrigin.MANUAL_SINGLE,
                manual_override=ThumbnailManualOverride.BLENDER,
            )

        self.assertTrue(ok)
        self.assertEqual(reject, BridgeEnqueueReject.OK)
        window._native_thumb_queue.try_enqueue_native.assert_not_called()
        window._bridge_queue.try_enqueue_thumbnail.assert_called_once()
        _args, kwargs = window._bridge_queue.try_enqueue_thumbnail.call_args
        self.assertEqual(kwargs.get("manual_override"), ThumbnailManualOverride.BLENDER)


class TestBridgeQueueNativeGuard(unittest.TestCase):
    """Bridge queue must refuse auto STL when policy selects native."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        ini = Path(self._tmp.name) / "routing.ini"
        self.settings = SettingsService(QSettings(str(ini), QSettings.Format.IniFormat))
        self.settings.set_thumbnail_renderer_preference(SettingsService.THUMBNAIL_RENDERER_AUTO)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_bridge_queue_rejects_auto_stl(self) -> None:
        from meshcorral.app.bridge.queue_manager import BridgeQueueManager

        mgr = BridgeQueueManager(self.settings)
        with patch_healthy_native_routing():
            ok, _msg, reject = mgr.try_enqueue_thumbnail(Path("C:/work/part.stl"))
        self.assertFalse(ok)
        self.assertEqual(reject, BridgeEnqueueReject.NOT_ROUTED)

    def test_bridge_queue_accepts_manual_blender_stl(self) -> None:
        from meshcorral.app.bridge.queue_manager import BridgeQueueManager

        mgr = BridgeQueueManager(self.settings)
        with patch(
            "meshcorral.app.bridge.queue_manager.find_blender_executable",
            return_value=Path("C:/Blender/blender.exe"),
        ), patch(
            "meshcorral.app.bridge.queue_manager.job_runner.enqueue_generate_thumbnail_job",
            return_value=Path("C:/jobs/pending/job.json"),
        ):
            ok, _msg, reject = mgr.try_enqueue_thumbnail(
                Path("C:/work/part.stl"),
                manual_override=ThumbnailManualOverride.BLENDER,
            )
        self.assertTrue(ok)
        self.assertEqual(reject, BridgeEnqueueReject.OK)


class TestNativeFailureFallbackPolicy(unittest.TestCase):
    """Malformed native failures only schedule Blender when policy allows."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        ini = Path(self._tmp.name) / "routing.ini"
        self.settings = SettingsService(QSettings(str(ini), QSettings.Format.IniFormat))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_native_first_without_blender_disallows_fallback(self) -> None:
        self.settings.set_thumbnail_renderer_preference(
            SettingsService.THUMBNAIL_RENDERER_NATIVE_FIRST
        )
        with patch_healthy_native_routing(), patch(
            "meshcorral.services.thumbnails.thumbnail_routing_policy.find_blender_executable",
            return_value=None,
        ):
            plan = route_thumbnail(Path("C:/a/part.stl"), self.settings)
        self.assertEqual(plan.backend, "native")
        self.assertFalse(plan.fallback_to_blender_on_native_fail)

    def test_completion_handler_skips_blender_when_fallback_disallowed(self) -> None:
        self.settings.set_thumbnail_renderer_preference(
            SettingsService.THUMBNAIL_RENDERER_NATIVE_FIRST
        )
        window = _window_stub(self.settings)
        record = _rec("bad.stl")
        window._record_for_source_path = MagicMock(return_value=record)
        window._bridge_queue.pop_job_origin_for_job_id.return_value = JobOrigin.BACKGROUND_AUTO
        window._shutting_down = False
        window._prime_perf_active = True
        window._thumb_controller.on_job_result = MagicMock()
        window._update_metadata_cache_from_bridge_result = MagicMock()
        window._lazy_thumb_health = MagicMock()
        window._thumb_refresh_accumulator = MagicMock()
        window._thumb_batch_progress = MagicMock()
        window._thumb_batch_progress.active.return_value = False
        window._thumb_progress_timer = MagicMock()

        with patch(
            "meshcorral.services.thumbnails.thumbnail_routing_policy.find_blender_executable",
            return_value=None,
        ):
            MainWindow._on_thumbnail_job_completed(
                window,
                BridgeJobResult(
                    job_id="n1",
                    status=BridgeJobStatus.FAILED,
                    job_type="native_thumbnail",
                    source_file=str(record.path),
                    fallback_reason="parse error",
                ),
            )

        window._try_enqueue_thumbnail_record.assert_not_called()


class TestTieredViewportNativeDiagnostics(unittest.TestCase):
    """Viewport tier enqueue records native diagnostics for STL background work."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        ini = Path(self._tmp.name) / "routing.ini"
        self.settings = SettingsService(QSettings(str(ini), QSettings.Format.IniFormat))
        self.settings.set_thumbnail_renderer_preference(SettingsService.THUMBNAIL_RENDERER_AUTO)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_viewport_tier_records_native_and_skip_counters(self) -> None:
        record = _rec("mesh.stl")
        diag = ThumbPaintDiagnostics()

        def try_enqueue(rec: FileRecord) -> tuple[bool, str, BridgeEnqueueReject]:
            with patch_healthy_native_routing():
                plan = route_thumbnail(rec.path, self.settings, for_auto_enqueue=True)
            if plan.backend == "native":
                diag.note_blender_skipped_native_supported(1)
                diag.note_native_jobs_enqueued(1)
                return True, "", BridgeEnqueueReject.OK
            return False, "unexpected blender", BridgeEnqueueReject.NOT_ROUTED

        stats = enqueue_tiered_bridge_thumbnails(
            try_enqueue,
            {"selected": [record], "visible": [], "directional_preload": [], "idle_background": []},
            has_thumbnail=lambda _r: False,
            include_idle_tier=False,
        )
        self.assertEqual(stats.enqueued, 1)
        self.assertGreater(diag.native_jobs_enqueued, 0)
        self.assertGreater(diag.blender_jobs_skipped_native_supported, 0)


if __name__ == "__main__":
    unittest.main()
