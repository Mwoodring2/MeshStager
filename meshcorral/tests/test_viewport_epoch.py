"""Tests for Prime v0.7 viewport epoch cancellation in the thumbnail controller."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QCoreApplication

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.models.file_record import FileRecord
from meshcorral.ui.thumbnail_controller import (
    _LoadRunnable,
    _RasterReadyRunnable,
    ThumbnailViewController,
)


def _png_rec(tmp: Path, name: str = "a.png") -> FileRecord:
    p = tmp / name
    p.write_bytes(b"x")
    return FileRecord(
        path=p,
        name=p.name,
        extension=".png",
        parent_folder=tmp.name,
    )


class _SinkSignals:
    """Capture emits from `_ImageLoadSignals` in a Qt-free way."""

    def __init__(self) -> None:
        self.ready_calls: list[tuple[str, str, str, object]] = []
        self.stale_calls: list[tuple[str, str, int]] = []
        self.image_ready = type("Sig", (), {"emit": lambda *a: self.ready_calls.append(a[1:])})()
        self.image_stale = type("Sig", (), {"emit": lambda *a: self.stale_calls.append(a[1:])})()


class TestRunnableEpochGuards(unittest.TestCase):
    def test_load_runnable_emits_stale_when_epoch_advances(self) -> None:
        sink = _SinkSignals()
        epoch_value = [5]

        runnable = _LoadRunnable(
            purpose="gallery",
            key="k1",
            abs_thumb="C:/missing.png",
            px=96,
            sigs=sink,  # type: ignore[arg-type]
            epoch=3,
            current_epoch_fn=lambda: epoch_value[0],
        )
        runnable.run()

        self.assertEqual(len(sink.stale_calls), 1)
        self.assertEqual(sink.stale_calls[0], ("gallery", "k1", 96))
        self.assertEqual(sink.ready_calls, [])

    def test_load_runnable_no_stale_when_epoch_matches(self) -> None:
        sink = _SinkSignals()
        epoch_value = [3]

        runnable = _LoadRunnable(
            purpose="gallery",
            key="k1",
            abs_thumb="C:/does-not-exist.png",
            px=96,
            sigs=sink,  # type: ignore[arg-type]
            epoch=3,
            current_epoch_fn=lambda: epoch_value[0],
        )
        self.assertFalse(runnable._is_stale())

    def test_raster_ready_runnable_skips_when_stale(self) -> None:
        emits: list[object] = []
        sink = type(
            "RasterSink",
            (),
            {"paths_ready": type("Sig", (), {"emit": lambda *a: emits.append(a[1:])})()},
        )()
        with tempfile.TemporaryDirectory() as td:
            rec = _png_rec(Path(td))
            runnable = _RasterReadyRunnable(
                [rec],
                sink,  # type: ignore[arg-type]
                epoch=1,
                current_epoch_fn=lambda: 4,
            )
            runnable.run()
        self.assertEqual(emits, [])


class TestControllerEpoch(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_set_epoch_callback_threads_value(self) -> None:
        ctrl = ThumbnailViewController()
        epoch = [7]
        ctrl.set_epoch_callback(lambda: epoch[0])
        self.assertEqual(ctrl.current_epoch(), 7)
        epoch[0] = 12
        self.assertEqual(ctrl.current_epoch(), 12)

    def test_on_image_stale_clears_inflight(self) -> None:
        ctrl = ThumbnailViewController()
        key = _norm_path_key(Path("C:/missing.png"))
        cache_key = ctrl._pixmap_cache_key(key, 96)
        ctrl._decoding_keys.add(cache_key)
        before = ctrl.stale_drop_count()
        ctrl._on_image_stale("gallery", key, 96)
        self.assertEqual(ctrl.stale_drop_count(), before + 1)
        self.assertNotIn(cache_key, ctrl._decoding_keys)

    def test_remote_mode_caps_decode_pool_to_one(self) -> None:
        ctrl = ThumbnailViewController()
        ctrl.set_prime_perf_mode(True, network_like=True)
        self.assertEqual(ctrl._pool.maxThreadCount(), 1)
        self.assertTrue(ctrl.throttle_profile().network_like)

    def test_local_prime_mode_keeps_two_workers(self) -> None:
        ctrl = ThumbnailViewController()
        ctrl.set_prime_perf_mode(True, network_like=False)
        self.assertEqual(ctrl._pool.maxThreadCount(), 2)


if __name__ == "__main__":
    unittest.main()
