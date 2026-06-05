"""Prime Performance Pass v0.9 — scroll velocity and viewport priority tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QCoreApplication

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.models.file_record import FileRecord
from meshcorral.ui.scroll_velocity import (
    FAST_SCROLL_PX_PER_SECOND_LOCAL,
    FAST_SCROLL_PX_PER_SECOND_REMOTE,
    SCROLL_SETTLE_MS_LOCAL,
    SCROLL_SETTLE_MS_REMOTE,
    ScrollVelocityTracker,
)
from meshcorral.ui.thumbnail_controller import ThumbnailViewController
from meshcorral.ui.viewport_priority import (
    directional_prefetch_row_indices,
    prioritize_viewport_records,
)


def _rec(path: str, ext: str = ".stl") -> FileRecord:
    p = Path(path)
    return FileRecord(
        path=p,
        name=p.name,
        extension=ext,
        parent_folder="f",
        size_bytes=1,
        modified_time=0.0,
    )


class TestScrollVelocityTracker(unittest.TestCase):
    def test_detects_fast_scrolling_local(self) -> None:
        tracker = ScrollVelocityTracker(network_like=False)
        t0 = 1000.0
        tracker.update(0, timestamp=t0)
        state = tracker.update(5000, timestamp=t0 + 1.0)
        self.assertGreaterEqual(state.px_per_second, FAST_SCROLL_PX_PER_SECOND_LOCAL)
        self.assertTrue(state.is_fast_scrolling)
        self.assertTrue(tracker.is_fast_scrolling())

    def test_remote_threshold_lower_than_local(self) -> None:
        self.assertLess(
            FAST_SCROLL_PX_PER_SECOND_REMOTE,
            FAST_SCROLL_PX_PER_SECOND_LOCAL,
        )
        tracker = ScrollVelocityTracker(network_like=True)
        t0 = 2000.0
        tracker.update(0, timestamp=t0)
        state = tracker.update(1200, timestamp=t0 + 1.0)
        self.assertGreaterEqual(state.px_per_second, FAST_SCROLL_PX_PER_SECOND_REMOTE)
        self.assertTrue(state.is_fast_scrolling)

    def test_slow_scroll_not_fast(self) -> None:
        tracker = ScrollVelocityTracker(network_like=False)
        t0 = 3000.0
        tracker.update(0, timestamp=t0)
        state = tracker.update(100, timestamp=t0 + 1.0)
        self.assertFalse(state.is_fast_scrolling)
        self.assertEqual(state.direction, "down")

    def test_direction_up_and_idle(self) -> None:
        tracker = ScrollVelocityTracker()
        t0 = 4000.0
        tracker.update(100, timestamp=t0)
        tracker.update(50, timestamp=t0 + 0.5)
        self.assertEqual(tracker.direction(), "up")
        idle_ms = tracker.time_since_scroll_ms()
        self.assertGreaterEqual(idle_ms, 0)

    def test_settle_delay_remote_longer(self) -> None:
        local = ScrollVelocityTracker(network_like=False)
        remote = ScrollVelocityTracker(network_like=True)
        self.assertEqual(local.settle_delay_ms(), SCROLL_SETTLE_MS_LOCAL)
        self.assertEqual(remote.settle_delay_ms(), SCROLL_SETTLE_MS_REMOTE)
        self.assertGreater(remote.settle_delay_ms(), local.settle_delay_ms())


class TestViewportPriority(unittest.TestCase):
    def test_prioritize_selected_then_visible(self) -> None:
        records = [_rec(f"C:/a/{i}.stl") for i in range(10)]
        rows = [2, 3, 4]
        ordered = prioritize_viewport_records(records, rows, selected_row=7)
        self.assertEqual(ordered[0].name, "7.stl")
        names = [r.name for r in ordered]
        self.assertIn("2.stl", names)
        self.assertIn("3.stl", names)

    def test_downward_prefetch_below_first(self) -> None:
        total = 100
        visible = [10, 11, 12]
        rows = directional_prefetch_row_indices(
            visible,
            total,
            direction="down",
            network_like=False,
        )
        self.assertEqual(rows[:3], [10, 11, 12])
        if len(rows) > 3:
            self.assertGreater(rows[3], 12)

    def test_upward_prefetch_above_first(self) -> None:
        total = 100
        visible = [50, 51, 52]
        rows = directional_prefetch_row_indices(
            visible,
            total,
            direction="up",
            network_like=False,
        )
        self.assertEqual(rows[:3], [50, 51, 52])
        if len(rows) > 3:
            self.assertLess(rows[3], 50)

    def test_remote_smaller_prefetch_span(self) -> None:
        visible = [20, 21, 22, 23, 24]
        local_rows = directional_prefetch_row_indices(
            visible, 200, direction="down", network_like=False
        )
        remote_rows = directional_prefetch_row_indices(
            visible, 200, direction="down", network_like=True
        )
        self.assertLessEqual(len(remote_rows), len(local_rows))


class TestFastScrollDecodeSuppression(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication

        inst = QApplication.instance()
        cls._app = inst if inst is not None else QApplication([])

    def test_fast_scroll_suppresses_decode_enqueue(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "a.png"
            p.write_bytes(
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
                b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
                b"\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc``\x00\x00\x00\x02\x00\x01"
                b"\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            rec = _rec(str(p), ".png")
            ctrl = ThumbnailViewController()
            ctrl.set_prime_perf_mode(True)
            ctrl.ready_cache().mark_ready_raster(rec.path)
            ctrl.set_fast_scroll_suppressed(True)
            ctrl._pool.start = lambda _r: None  # type: ignore[method-assign]
            before = len(ctrl._decoding_keys)
            _ = ctrl.decoration_for(rec)
            self.assertEqual(len(ctrl._decoding_keys), before)

    def test_decode_resumes_after_suppression_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "b.png"
            p.write_bytes(b"x")
            rec = _rec(str(p), ".png")
            ctrl = ThumbnailViewController()
            ctrl.set_prime_perf_mode(True)
            ctrl.ready_cache().mark_ready_raster(rec.path)
            ctrl.set_record_visible_fn(lambda _r: True)
            ctrl.set_fast_scroll_suppressed(True)
            self.assertFalse(ctrl._should_start_decode(rec, px=96))
            ctrl.set_fast_scroll_suppressed(False)
            self.assertTrue(ctrl._should_start_decode(rec, px=96))

    def test_no_duplicate_decode_keys_during_rapid_scroll(self) -> None:
        ctrl = ThumbnailViewController()
        ctrl.set_fast_scroll_suppressed(False)
        key = _norm_path_key("C:/a/x.png")
        cache_key = ctrl._pixmap_cache_key(key, 96)
        ctrl._pool.start = lambda _r: None  # type: ignore[method-assign]
        ctrl._start_decode(key, str(Path("C:/a/x.png")), px=96, purpose="gallery")
        ctrl._start_decode(key, str(Path("C:/a/x.png")), px=96, purpose="gallery")
        self.assertEqual(len(ctrl._decoding_keys), 1)
        self.assertIn(cache_key, ctrl._decoding_keys)

    def test_stale_epoch_increments_diagnostic(self) -> None:
        ctrl = ThumbnailViewController()
        ctrl.set_prime_perf_mode(True)
        ctrl._pool.start = lambda _r: None  # type: ignore[method-assign]
        epoch = [1]

        def _epoch() -> int:
            return epoch[0]

        ctrl.set_epoch_callback(_epoch)
        ctrl._start_decode("k", "C:/x.png", px=96, purpose="gallery")
        epoch[0] = 2
        ctrl._on_image_stale("gallery", "k", 96)
        snap = ctrl.paint_diagnostics().snapshot()
        self.assertGreaterEqual(int(snap["stale_epoch_drops"]), 1)


class TestMainWindowScrollSettle(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        inst = QCoreApplication.instance()
        if inst is None:
            from PySide6.QtWidgets import QApplication

            cls._app = QApplication([])
        else:
            cls._app = inst

    def test_schedule_fast_scroll_defers_viewport_timer(self) -> None:
        from meshcorral.ui.main_window import MainWindow

        window = MainWindow()
        window._view_records = [_rec("C:/a/1.stl")]
        window._prime_perf_active = True
        window._prime_network_like = False
        with mock.patch.object(window, "_browse_scroll_value", return_value=0), mock.patch.object(
            window._scroll_velocity,
            "update",
        ) as mock_update:
            from meshcorral.ui.scroll_velocity import ScrollVelocityState

            mock_update.return_value = ScrollVelocityState(
                value=0,
                px_per_second=5000.0,
                rows_per_second=100.0,
                is_fast_scrolling=True,
                direction="down",
                time_since_scroll_ms=0,
                network_like=False,
            )
            window._schedule_viewport_thumb_pass()
        self.assertFalse(window._viewport_thumb_timer.isActive())
        self.assertTrue(window._scroll_settle_timer.isActive())
        self.assertTrue(window._thumb_controller.is_fast_scroll_suppressed())

    def test_settle_timer_runs_viewport_pass(self) -> None:
        from meshcorral.ui.main_window import MainWindow

        window = MainWindow()
        window._view_records = [_rec("C:/a/1.stl")]
        window._prime_perf_active = True
        ran: list[bool] = []

        def _capture() -> None:
            ran.append(True)

        with mock.patch.object(
            window._scroll_velocity, "is_fast_scrolling", return_value=False
        ), mock.patch.object(
            window._scroll_velocity, "time_since_scroll_ms", return_value=500
        ), mock.patch.object(window, "_run_viewport_thumb_pass", side_effect=_capture):
            window._thumb_controller.set_fast_scroll_suppressed(True)
            window._on_scroll_settle_timer()
        self.assertTrue(ran)
        self.assertFalse(window._thumb_controller.is_fast_scroll_suppressed())


if __name__ == "__main__":
    unittest.main()
