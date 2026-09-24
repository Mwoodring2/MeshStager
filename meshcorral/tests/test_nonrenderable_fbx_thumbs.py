"""
Known non-renderable FBX thumbnails must stop being auto-queued to Blender.

Covers the classifier (which failures are permanent), the persisted negative cache in the
existing metadata database, the automatic-enqueue gate, manual regenerate bypass, and the
unsupported visual state. Transient failures must stay retryable.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from meshcorral.app.bridge.bridge_backpressure import BridgeEnqueueReject
from meshcorral.app.bridge.job_models import BridgeJobResult, BridgeJobStatus
from meshcorral.app.bridge.job_origin import JobOrigin
from meshcorral.models.file_record import FileRecord
from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.services.metadata_cache import MetadataCache
from meshcorral.services.settings_service import SettingsService
from meshcorral.services.thumbnails.nonrenderable_thumbs import (
    NonRenderableReason,
    classify_non_renderable_result,
    fbx_is_ascii,
    fingerprint_for_path,
    non_renderable_blocks_auto_enqueue,
)
from meshcorral.services.thumbnails.native_thumbnail_queue import NativeEnqueueReject
from meshcorral.services.thumbnails.thumbnail_routing_policy import ThumbnailManualOverride
from meshcorral.tests.native_health_fixtures import healthy_native_health
from meshcorral.ui.main_window import MainWindow
from meshcorral.ui.thumb_paint_diagnostics import ThumbPaintDiagnostics
from meshcorral.ui.thumbnail_controller import ThumbnailViewController

_BINARY_FBX_HEADER = b"Kaydara FBX Binary  \x00\x1a\x00"
_ASCII_FBX_TEXT = (
    "; FBX 7.3.0 project file\n"
    "FBXHeaderExtension:  {\n"
    "    FBXHeaderVersion: 1003\n"
    "}\n"
)

_ARMATURE_ONLY_ERROR = (
    "Imported 1 objects, 0 meshes. Types: [ARMATURE:1]."
    " Unable to derive renderable geometry (check OBJ contents or converters)."
)
_CAMERA_LIGHT_ONLY_ERROR = (
    "Imported 3 objects, 0 meshes. Types: [CAMERA:1, LIGHT:2]."
    " Unable to derive renderable geometry (check OBJ contents or converters)."
)
_EMPTY_SCENE_ERROR = (
    "Imported 0 objects, 0 meshes. Types: [none]."
    " Unable to derive renderable geometry (check OBJ contents or converters)."
)
_ASCII_IMPORT_ERROR = "FBX import failed: ASCII FBX files are not supported"
_GENERIC_IMPORT_ERROR = "FBX import failed: Error: Couldn't open file (Invalid header)"


def _write_binary_fbx(path: Path, payload: bytes = b"\x00" * 64) -> Path:
    """Write a file that passes the binary FBX header sniff."""
    path.write_bytes(_BINARY_FBX_HEADER + payload)
    return path


def _write_ascii_fbx(path: Path) -> Path:
    """Write a plausible ASCII FBX file."""
    path.write_text(_ASCII_FBX_TEXT, encoding="ascii")
    return path


def _failed_result(
    source: Path,
    error_message: str,
    *,
    job_type: str = "generate_thumbnail",
) -> BridgeJobResult:
    return BridgeJobResult(
        job_id="job-1",
        status=BridgeJobStatus.FAILED,
        job_type=job_type,
        source_file=str(source),
        output_dir=str(source.parent),
        error_message=error_message,
    )


def _record_for(path: Path, *, ext: str = ".fbx") -> FileRecord:
    stat_result = path.stat()
    return FileRecord(
        path=path,
        name=path.name,
        extension=ext,
        parent_folder=path.parent.name,
        size_bytes=int(stat_result.st_size),
        modified_time=float(stat_result.st_mtime),
    )


class TestNonRenderableClassifier(unittest.TestCase):
    """Only permanent, well-understood failures may be classified."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_armature_only_import_is_non_renderable(self) -> None:
        src = _write_binary_fbx(self.root / "rig.fbx")
        verdict = classify_non_renderable_result(_failed_result(src, _ARMATURE_ONLY_ERROR))
        self.assertIsNotNone(verdict)
        assert verdict is not None
        self.assertEqual(verdict.reason, NonRenderableReason.NO_MESH_OBJECTS)
        self.assertIn("ARMATURE:1", verdict.detail)

    def test_camera_and_light_only_import_is_non_renderable(self) -> None:
        src = _write_binary_fbx(self.root / "set.fbx")
        verdict = classify_non_renderable_result(_failed_result(src, _CAMERA_LIGHT_ONLY_ERROR))
        self.assertIsNotNone(verdict)
        assert verdict is not None
        self.assertEqual(verdict.reason, NonRenderableReason.NO_MESH_OBJECTS)

    def test_empty_scene_import_is_non_renderable(self) -> None:
        src = _write_binary_fbx(self.root / "empty.fbx")
        verdict = classify_non_renderable_result(_failed_result(src, _EMPTY_SCENE_ERROR))
        self.assertIsNotNone(verdict)
        assert verdict is not None
        self.assertEqual(verdict.reason, NonRenderableReason.NO_MESH_OBJECTS)

    def test_ascii_fbx_error_text_is_non_renderable(self) -> None:
        src = _write_ascii_fbx(self.root / "ascii.fbx")
        verdict = classify_non_renderable_result(_failed_result(src, _ASCII_IMPORT_ERROR))
        self.assertIsNotNone(verdict)
        assert verdict is not None
        self.assertEqual(verdict.reason, NonRenderableReason.ASCII_UNSUPPORTED)

    def test_ascii_fbx_detected_by_header_when_error_text_is_generic(self) -> None:
        src = _write_ascii_fbx(self.root / "ascii2.fbx")
        self.assertIs(fbx_is_ascii(src), True)
        verdict = classify_non_renderable_result(_failed_result(src, _GENERIC_IMPORT_ERROR))
        self.assertIsNotNone(verdict)
        assert verdict is not None
        self.assertEqual(verdict.reason, NonRenderableReason.ASCII_UNSUPPORTED)

    def test_binary_fbx_with_generic_import_error_is_not_classified(self) -> None:
        src = _write_binary_fbx(self.root / "corrupt.fbx")
        self.assertIs(fbx_is_ascii(src), False)
        result = _failed_result(src, _GENERIC_IMPORT_ERROR)
        self.assertIsNone(classify_non_renderable_result(result))

    def test_zero_mesh_with_convertible_geometry_is_not_classified(self) -> None:
        src = _write_binary_fbx(self.root / "curves.fbx")
        message = (
            "Imported 2 objects, 0 meshes. Types: [CURVE:1, EMPTY:1]."
            " Unable to derive renderable geometry (check OBJ contents or converters)."
        )
        self.assertIsNone(classify_non_renderable_result(_failed_result(src, message)))

    def test_transient_failures_are_not_classified(self) -> None:
        src = _write_binary_fbx(self.root / "flaky.fbx")
        transient = (
            "Blender exited with code -1073741819 and did not write result.json.",
            "Imported 1 objects, 0 meshes. Types: [ARMATURE:1]. (Blender exited with code 1.)",
            "Thumbnail job timed out after 120s.",
            "FBX import failed: [Errno 13] Permission denied: 'rig.fbx'",
            "Render finished but thumbnail.png was not found in the output directory.",
            "Source file not found: \\\\share\\assets\\rig.fbx",
            "FBX import failed: network path is unavailable",
            "Traceback (most recent call last):\n  File \"run_job.py\"\nRuntimeError: boom",
        )
        for message in transient:
            with self.subTest(message=message):
                self.assertIsNone(classify_non_renderable_result(_failed_result(src, message)))

    def test_successful_job_is_not_classified(self) -> None:
        src = _write_binary_fbx(self.root / "good.fbx")
        result = BridgeJobResult(
            job_id="ok",
            status=BridgeJobStatus.COMPLETE,
            job_type="generate_thumbnail",
            source_file=str(src),
            thumbnail_path=str(self.root / "thumbnail.png"),
        )
        self.assertIsNone(classify_non_renderable_result(result))

    def test_non_fbx_source_is_not_classified(self) -> None:
        src = self.root / "mesh.obj"
        src.write_text("o empty\n", encoding="utf-8")
        self.assertIsNone(classify_non_renderable_result(_failed_result(src, _EMPTY_SCENE_ERROR)))

    def test_native_job_result_is_not_classified(self) -> None:
        src = _write_binary_fbx(self.root / "native.fbx")
        result = _failed_result(src, _ARMATURE_ONLY_ERROR, job_type="native_thumbnail")
        self.assertIsNone(classify_non_renderable_result(result))


class TestNonRenderableCacheStorage(unittest.TestCase):
    """The negative result lives in the existing metadata database, keyed by fingerprint."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.cache = MetadataCache(self.root / "metadata_cache.sqlite")
        self.src = _write_binary_fbx(self.root / "rig.fbx")
        fingerprint = fingerprint_for_path(self.src)
        assert fingerprint is not None
        self.fingerprint = fingerprint
        self.cache.record_non_renderable_thumb(
            path=self.src,
            reason=NonRenderableReason.NO_MESH_OBJECTS.value,
            detail="objects=1 types=[ARMATURE:1]",
            size_bytes=self.fingerprint.size_bytes,
            modified_time=self.fingerprint.modified_time,
        )

    def tearDown(self) -> None:
        self.cache.close()
        self._tmp.cleanup()

    def test_record_and_lookup_roundtrip(self) -> None:
        entry = self.cache.non_renderable_thumb(self.src)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.reason_enum(), NonRenderableReason.NO_MESH_OBJECTS)
        self.assertEqual(entry.ext, ".fbx")
        self.assertTrue(
            entry.matches_fingerprint(
                size_bytes=self.fingerprint.size_bytes,
                modified_time=self.fingerprint.modified_time,
            )
        )

    def test_size_change_makes_entry_stale(self) -> None:
        entry = self.cache.non_renderable_thumb(self.src)
        assert entry is not None
        self.assertFalse(
            non_renderable_blocks_auto_enqueue(
                entry,
                size_bytes=self.fingerprint.size_bytes + 512,
                modified_time=self.fingerprint.modified_time,
            )
        )

    def test_mtime_change_makes_entry_stale(self) -> None:
        entry = self.cache.non_renderable_thumb(self.src)
        assert entry is not None
        self.assertFalse(
            non_renderable_blocks_auto_enqueue(
                entry,
                size_bytes=self.fingerprint.size_bytes,
                modified_time=self.fingerprint.modified_time + 60.0,
            )
        )

    def test_unknown_stat_never_blocks(self) -> None:
        entry = self.cache.non_renderable_thumb(self.src)
        assert entry is not None
        self.assertFalse(
            non_renderable_blocks_auto_enqueue(entry, size_bytes=None, modified_time=None)
        )

    def test_clear_removes_entry(self) -> None:
        self.assertTrue(self.cache.clear_non_renderable_thumb(self.src))
        self.assertIsNone(self.cache.non_renderable_thumb(self.src))
        self.assertFalse(self.cache.clear_non_renderable_thumb(self.src))

    def test_batch_lookup_returns_recorded_rows(self) -> None:
        other = _write_binary_fbx(self.root / "other.fbx")
        entries = self.cache.non_renderable_thumbs_for_paths([self.src, other])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].path, str(self.src))

    def test_clear_all_wipes_negative_rows(self) -> None:
        self.cache.clear_all()
        self.assertEqual(self.cache.non_renderable_thumb_count(), 0)


def _window_stub(settings: SettingsService, cache: MetadataCache) -> MagicMock:
    """MainWindow stand-in with the collaborators the enqueue gate touches."""
    window = MagicMock()
    window._settings_service = settings
    window._metadata_cache = cache
    window._thumb_controller = MagicMock()
    window._thumb_controller.paint_diagnostics.return_value = ThumbPaintDiagnostics()
    window._lazy_thumb_health = MagicMock()
    window._native_thumb_queue = MagicMock()
    window._native_thumb_queue.in_flight_count.return_value = 0
    window._native_thumb_queue.try_enqueue_native.return_value = (
        True,
        "",
        NativeEnqueueReject.OK,
    )
    window._map_native_reject = MainWindow._map_native_reject
    window._bridge_queue = MagicMock()
    window._bridge_queue.try_enqueue_thumbnail.return_value = (True, "", BridgeEnqueueReject.OK)
    window._bridge_queue.in_flight_load.return_value = (0, 0)
    window._native_job_origins = {}
    window._native_renderer_health = healthy_native_health()
    window._native_degraded_footer_shown = True
    window._is_known_non_renderable_record = (
        lambda record, source: MainWindow._is_known_non_renderable_record(window, record, source)
    )
    window._forget_non_renderable_source = (
        lambda source: MainWindow._forget_non_renderable_source(window, source)
    )
    return window


class TestAutoEnqueueGate(unittest.TestCase):
    """Automatic requests skip Blender; manual requests still retry."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.settings = SettingsService(
            QSettings(str(self.root / "gate.ini"), QSettings.Format.IniFormat)
        )
        self.settings.set_thumbnail_renderer_preference(SettingsService.THUMBNAIL_RENDERER_AUTO)
        self.cache = MetadataCache(self.root / "metadata_cache.sqlite")
        self.src = _write_binary_fbx(self.root / "rig.fbx")
        self.record = _record_for(self.src)
        self.window = _window_stub(self.settings, self.cache)
        self._blender = patch(
            "meshcorral.services.thumbnails.thumbnail_routing_policy.find_blender_executable",
            return_value=Path("C:/Blender/blender.exe"),
        )
        self._blender.start()

    def tearDown(self) -> None:
        self._blender.stop()
        self.cache.close()
        self._tmp.cleanup()

    def _mark_known_non_renderable(
        self,
        *,
        size_bytes: int | None = None,
        modified_time: float | None = None,
    ) -> None:
        self.cache.record_non_renderable_thumb(
            path=self.src,
            reason=NonRenderableReason.NO_MESH_OBJECTS.value,
            detail="objects=1 types=[ARMATURE:1]",
            size_bytes=self.record.size_bytes if size_bytes is None else size_bytes,
            modified_time=(
                self.record.modified_time if modified_time is None else modified_time
            ),
        )

    def _auto_enqueue(self) -> tuple[bool, str, BridgeEnqueueReject]:
        return MainWindow._try_enqueue_thumbnail_record(
            self.window,
            self.record,
            origin=JobOrigin.BACKGROUND_AUTO,
            for_auto_enqueue=True,
        )

    def test_unknown_fbx_still_enqueues_to_blender(self) -> None:
        ok, _msg, reject = self._auto_enqueue()
        self.assertTrue(ok)
        self.assertEqual(reject, BridgeEnqueueReject.OK)
        self.window._bridge_queue.try_enqueue_thumbnail.assert_called_once()

    def test_unchanged_known_non_renderable_skips_background_enqueue(self) -> None:
        self._mark_known_non_renderable()
        ok, _msg, reject = self._auto_enqueue()
        self.assertFalse(ok)
        self.assertEqual(reject, BridgeEnqueueReject.NOT_ROUTED)
        self.window._bridge_queue.try_enqueue_thumbnail.assert_not_called()
        self.window._native_thumb_queue.try_enqueue_native.assert_not_called()
        self.window._thumb_controller.mark_non_renderable.assert_called_once_with(self.src)

    def test_changed_size_retries_and_drops_stale_entry(self) -> None:
        self._mark_known_non_renderable(size_bytes=self.record.size_bytes + 4096)
        ok, _msg, reject = self._auto_enqueue()
        self.assertTrue(ok)
        self.assertEqual(reject, BridgeEnqueueReject.OK)
        self.window._bridge_queue.try_enqueue_thumbnail.assert_called_once()
        self.assertIsNone(self.cache.non_renderable_thumb(self.src))

    def test_changed_mtime_retries(self) -> None:
        self._mark_known_non_renderable(modified_time=self.record.modified_time - 900.0)
        ok, _msg, _reject = self._auto_enqueue()
        self.assertTrue(ok)
        self.window._bridge_queue.try_enqueue_thumbnail.assert_called_once()

    def test_manual_regenerate_bypasses_negative_cache(self) -> None:
        self._mark_known_non_renderable()
        ok, _msg, reject = MainWindow._try_enqueue_thumbnail_record(
            self.window,
            self.record,
            origin=JobOrigin.MANUAL_SINGLE,
            manual_override=ThumbnailManualOverride.BLENDER,
        )
        self.assertTrue(ok)
        self.assertEqual(reject, BridgeEnqueueReject.OK)
        self.window._bridge_queue.try_enqueue_thumbnail.assert_called_once()
        self.assertIsNone(self.cache.non_renderable_thumb(self.src))
        self.window._thumb_controller.clear_non_renderable.assert_called_once_with(self.src)

    def test_non_fbx_row_never_queries_negative_cache(self) -> None:
        stl = self.root / "part.stl"
        stl.write_bytes(b"solid\n")
        record = _record_for(stl, ext=".stl")
        with patch.object(self.cache, "non_renderable_thumb") as lookup:
            MainWindow._try_enqueue_thumbnail_record(
                self.window,
                record,
                origin=JobOrigin.BACKGROUND_AUTO,
                for_auto_enqueue=True,
            )
        lookup.assert_not_called()


class TestPersistVerdictFromJobResult(unittest.TestCase):
    """Job completion persists permanent verdicts and nothing else."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.cache = MetadataCache(self.root / "metadata_cache.sqlite")
        self.window = MagicMock()
        self.window._metadata_cache = self.cache
        self.window._thumb_controller = MagicMock()
        self.window._lazy_thumb_health = MagicMock()

    def tearDown(self) -> None:
        self.cache.close()
        self._tmp.cleanup()

    def test_armature_only_failure_is_persisted(self) -> None:
        src = _write_binary_fbx(self.root / "rig.fbx")
        MainWindow._record_non_renderable_result(
            self.window,
            _failed_result(src, _ARMATURE_ONLY_ERROR),
        )
        entry = self.cache.non_renderable_thumb(src)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.reason_enum(), NonRenderableReason.NO_MESH_OBJECTS)
        self.assertEqual(entry.size_bytes, src.stat().st_size)
        self.window._thumb_controller.mark_non_renderable.assert_called_once_with(src)

    def test_ascii_fbx_failure_is_persisted(self) -> None:
        src = _write_ascii_fbx(self.root / "ascii.fbx")
        MainWindow._record_non_renderable_result(
            self.window,
            _failed_result(src, _ASCII_IMPORT_ERROR),
        )
        entry = self.cache.non_renderable_thumb(src)
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.reason_enum(), NonRenderableReason.ASCII_UNSUPPORTED)

    def test_transient_blender_crash_is_not_persisted(self) -> None:
        src = _write_binary_fbx(self.root / "crash.fbx")
        crash = "Blender exited with code -1073741819 and did not write result.json."
        MainWindow._record_non_renderable_result(self.window, _failed_result(src, crash))
        self.assertIsNone(self.cache.non_renderable_thumb(src))
        self.window._thumb_controller.mark_non_renderable.assert_not_called()

    def test_successful_job_is_not_persisted(self) -> None:
        src = _write_binary_fbx(self.root / "good.fbx")
        MainWindow._record_non_renderable_result(
            self.window,
            BridgeJobResult(
                job_id="ok",
                status=BridgeJobStatus.COMPLETE,
                job_type="generate_thumbnail",
                source_file=str(src),
                thumbnail_path=str(self.root / "thumbnail.png"),
            ),
        )
        self.assertIsNone(self.cache.non_renderable_thumb(src))

    def test_missing_source_file_is_not_persisted(self) -> None:
        src = self.root / "gone.fbx"
        MainWindow._record_non_renderable_result(
            self.window,
            _failed_result(src, _ARMATURE_ONLY_ERROR),
        )
        self.assertIsNone(self.cache.non_renderable_thumb(src))


class TestNonRenderableVisualState(unittest.TestCase):
    """Known non-renderable rows reuse the existing unsupported visual state."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.controller = ThumbnailViewController()
        self.src = _write_binary_fbx(self.root / "rig.fbx")
        self.record = _record_for(self.src)

    def tearDown(self) -> None:
        self.controller.request_shutdown(timeout_ms=10)
        self._tmp.cleanup()

    def test_marked_source_reports_unsupported(self) -> None:
        self.assertEqual(
            self.controller.resolve_thumb_health(self.record),
            ThumbHealth.MISSING_THUMBNAIL,
        )
        self.controller.mark_non_renderable(self.src)
        self.assertTrue(self.controller.is_known_non_renderable(self.record))
        self.assertEqual(
            self.controller.resolve_thumb_health(self.record),
            ThumbHealth.UNSUPPORTED,
        )
        self.assertEqual(
            self.controller.visual_state(self.record),
            ThumbVisualState.UNSUPPORTED,
        )

    def test_completed_job_clears_marker(self) -> None:
        thumb = self.root / "thumbnail.png"
        thumb.write_bytes(b"png")
        self.controller.mark_non_renderable(self.src)
        self.controller.on_job_result(
            BridgeJobResult(
                job_id="ok",
                status=BridgeJobStatus.COMPLETE,
                job_type="generate_thumbnail",
                source_file=str(self.src),
                output_dir=str(self.root),
                thumbnail_path=str(thumb),
            ),
            refresh_ui=False,
        )
        self.assertFalse(self.controller.is_known_non_renderable(self.record))
        self.assertEqual(
            self.controller.resolve_thumb_health(self.record),
            ThumbHealth.HAS_THUMBNAIL,
        )

    def test_set_keys_replaces_previous_markers(self) -> None:
        self.controller.mark_non_renderable(self.src)
        self.controller.set_non_renderable_keys(())
        self.assertFalse(self.controller.is_known_non_renderable(self.record))
        self.assertEqual(self.controller.non_renderable_count(), 0)


if __name__ == "__main__":
    unittest.main()
