"""Prime Performance Pass v0.10 — Blender Bridge backpressure and viewport queueing."""

from __future__ import annotations

import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings

from meshcorral.app.bridge.bridge_backpressure import (
    MAX_PENDING_BRIDGE_JOBS_LOCAL,
    MAX_PENDING_BRIDGE_JOBS_REMOTE,
    BridgeEnqueueReject,
    bridge_idle_fill_allowed,
    bridge_records_by_tier,
    enqueue_tiered_bridge_thumbnails,
    max_pending_bridge_jobs,
)
from meshcorral.app.bridge.queue_manager import BridgeQueueManager
from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.models.file_record import FileRecord
from meshcorral.services.settings_service import SettingsService
from meshcorral.ui.thumb_paint_diagnostics import ThumbPaintDiagnostics


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


class TestBridgeBackpressureConstants(unittest.TestCase):
    def test_local_cap_greater_than_remote(self) -> None:
        self.assertGreater(
            max_pending_bridge_jobs(network_like=False),
            max_pending_bridge_jobs(network_like=True),
        )
        self.assertEqual(max_pending_bridge_jobs(network_like=False), MAX_PENDING_BRIDGE_JOBS_LOCAL)
        self.assertEqual(max_pending_bridge_jobs(network_like=True), MAX_PENDING_BRIDGE_JOBS_REMOTE)


class TestBridgeTierOrdering(unittest.TestCase):
    def test_selected_before_visible_before_preload(self) -> None:
        records = [_rec(f"C:/m/{i}.stl") for i in range(20)]
        visible = [5, 6, 7]
        prefetch = [5, 6, 7, 8, 9, 10, 11]
        tiers = bridge_records_by_tier(
            records,
            visible_row_indices=visible,
            prefetch_row_indices=prefetch,
            selected_row=12,
        )
        self.assertEqual(tiers["selected"][0].name, "12.stl")
        visible_names = [r.name for r in tiers["visible"]]
        self.assertEqual(visible_names, ["5.stl", "6.stl", "7.stl"])
        preload_names = [r.name for r in tiers["directional_preload"]]
        self.assertIn("8.stl", preload_names)
        self.assertNotIn("5.stl", preload_names)

    def test_idle_background_excludes_viewport_tiers(self) -> None:
        records = [_rec(f"C:/m/{i}.stl") for i in range(8)]
        tiers = bridge_records_by_tier(
            records,
            visible_row_indices=[2],
            prefetch_row_indices=[2, 3],
            selected_row=1,
            idle_background_row_indices=list(range(8)),
        )
        idle_names = {r.name for r in tiers["idle_background"]}
        self.assertNotIn("1.stl", idle_names)
        self.assertNotIn("2.stl", idle_names)
        self.assertIn("0.stl", idle_names)


class TestTieredEnqueueHelper(unittest.TestCase):
    def test_stops_on_cap_and_counts_duplicate(self) -> None:
        records = [_rec(f"C:/x/{i}.stl") for i in range(5)]
        tiers = {
            "selected": [],
            "visible": records[:2],
            "directional_preload": records[2:],
            "idle_background": [],
        }
        calls: list[str] = []

        def _try_enqueue(record: FileRecord) -> tuple[bool, str, BridgeEnqueueReject]:
            calls.append(record.name)
            if len(calls) == 1:
                return True, "", BridgeEnqueueReject.OK
            if len(calls) == 2:
                return False, "dup", BridgeEnqueueReject.DUPLICATE
            return False, "full", BridgeEnqueueReject.CAP

        stats = enqueue_tiered_bridge_thumbnails(
            _try_enqueue,
            tiers,
            has_thumbnail=lambda _r: False,
        )
        self.assertEqual(stats.enqueued, 1)
        self.assertEqual(stats.duplicate_skips, 1)
        self.assertEqual(stats.suppressed_cap, 1)
        self.assertEqual(calls[0], "0.stl")


class TestBridgeIdleFillGating(unittest.TestCase):
    def test_requires_scroll_settle_decode_quiet_ui_idle(self) -> None:
        self.assertFalse(
            bridge_idle_fill_allowed(
                scroll_idle_ms=50.0,
                scroll_settle_ms=160,
                decode_inflight=0,
                ui_idle_ms=3000.0,
            )
        )
        self.assertFalse(
            bridge_idle_fill_allowed(
                scroll_idle_ms=500.0,
                scroll_settle_ms=160,
                decode_inflight=2,
                ui_idle_ms=3000.0,
            )
        )
        self.assertFalse(
            bridge_idle_fill_allowed(
                scroll_idle_ms=500.0,
                scroll_settle_ms=160,
                decode_inflight=0,
                ui_idle_ms=500.0,
            )
        )
        self.assertTrue(
            bridge_idle_fill_allowed(
                scroll_idle_ms=500.0,
                scroll_settle_ms=160,
                decode_inflight=0,
                ui_idle_ms=2500.0,
            )
        )


class TestBridgeQueueCapAndDuplicates(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._ini = str(Path(self._tmp.name) / "t.ini")
        self._qs = QSettings(self._ini, QSettings.Format.IniFormat)
        self._qs.clear()
        self._svc = SettingsService(self._qs)
        self._prev_bridge_root = os.environ.get("ROUNDUP_BRIDGE_ROOT")
        os.environ["ROUNDUP_BRIDGE_ROOT"] = str(Path(self._tmp.name) / "bridge")
        self._fake_blender = Path(self._tmp.name) / "blender.exe"
        self._fake_blender.write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        if self._prev_bridge_root is None:
            os.environ.pop("ROUNDUP_BRIDGE_ROOT", None)
        else:
            os.environ["ROUNDUP_BRIDGE_ROOT"] = self._prev_bridge_root
        self._qs.clear()
        self._tmp.cleanup()

    def test_duplicate_suppression(self) -> None:
        mesh = Path(self._tmp.name) / "mesh.fbx"
        mesh.write_text("x", encoding="utf-8")
        with patch(
            "meshcorral.app.bridge.queue_manager.find_blender_executable",
            return_value=self._fake_blender,
        ):
            mgr = BridgeQueueManager(self._svc)
            mgr.configure_backpressure(network_like=False)
            mgr.shutdown(timeout=0.05, close_enqueue=False)
            try:
                ok1, _, r1 = mgr.try_enqueue_thumbnail(mesh)
                ok2, _, r2 = mgr.try_enqueue_thumbnail(mesh)
            finally:
                mgr.shutdown(timeout=0.2, close_enqueue=False)
        self.assertTrue(ok1)
        self.assertEqual(r1, BridgeEnqueueReject.OK)
        self.assertFalse(ok2)
        self.assertEqual(r2, BridgeEnqueueReject.DUPLICATE)

    def test_queue_cap_enforcement(self) -> None:
        hold = threading.Event()

        def _block_run(*_args: object, **_kwargs: object) -> object:
            hold.wait(timeout=5.0)
            from meshcorral.app.bridge.job_models import BridgeJobResult, BridgeJobStatus

            return BridgeJobResult(
                job_id="blocked",
                status=BridgeJobStatus.CANCELLED,
                output_dir=str(Path(self._tmp.name)),
            )

        with patch(
            "meshcorral.app.bridge.queue_manager.find_blender_executable",
            return_value=self._fake_blender,
        ):
            with patch(
                "meshcorral.app.bridge.queue_manager.job_runner.run_job_now",
                side_effect=_block_run,
            ):
                mgr = BridgeQueueManager(self._svc)
                mgr.configure_backpressure(network_like=True)
                cap = mgr.max_pending_cap()
                self.assertEqual(cap, MAX_PENDING_BRIDGE_JOBS_REMOTE)
                try:
                    meshes = []
                    for i in range(cap + 3):
                        p = Path(self._tmp.name) / f"m{i}.fbx"
                        p.write_text("x", encoding="utf-8")
                        meshes.append(p)
                    cap_hits = 0
                    for p in meshes:
                        _ok, _msg, reject = mgr.try_enqueue_thumbnail(p)
                        if reject == BridgeEnqueueReject.CAP:
                            cap_hits += 1
                            self.assertEqual(mgr.bridge_load(), cap)
                finally:
                    hold.set()
                    mgr.shutdown(timeout=0.5, close_enqueue=False)
        self.assertGreaterEqual(cap_hits, 1)

    def test_local_cap_higher_than_remote(self) -> None:
        with patch(
            "meshcorral.app.bridge.queue_manager.find_blender_executable",
            return_value=self._fake_blender,
        ):
            local_mgr = BridgeQueueManager(self._svc)
            remote_mgr = BridgeQueueManager(self._svc)
            local_mgr.configure_backpressure(network_like=False)
            remote_mgr.configure_backpressure(network_like=True)
            try:
                self.assertEqual(local_mgr.max_pending_cap(), MAX_PENDING_BRIDGE_JOBS_LOCAL)
                self.assertEqual(remote_mgr.max_pending_cap(), MAX_PENDING_BRIDGE_JOBS_REMOTE)
            finally:
                local_mgr.shutdown(timeout=0.2, close_enqueue=False)
                remote_mgr.shutdown(timeout=0.2, close_enqueue=False)


class TestBridgeDiagnostics(unittest.TestCase):
    def test_suppression_and_queue_stats_in_snapshot(self) -> None:
        diag = ThumbPaintDiagnostics()
        diag.note_bridge_suppressed(3)
        diag.note_bridge_duplicate_skip(2)
        diag.note_bridge_idle_enqueue(4)
        diag.sync_bridge_queue_stats(5, 1)
        snap = diag.snapshot()
        self.assertEqual(snap["bridge_jobs_suppressed"], 3)
        self.assertEqual(snap["bridge_duplicate_skips"], 2)
        self.assertEqual(snap["bridge_idle_enqueues"], 4)
        self.assertEqual(snap["bridge_jobs_pending"], 5)
        self.assertEqual(snap["bridge_jobs_running"], 1)

    def test_visible_only_tier_skips_non_mesh(self) -> None:
        records = [
            _rec("C:/a/mesh.stl"),
            _rec("C:/a/photo.png", ext=".png"),
            _rec("C:/a/other.obj"),
        ]
        tiers = bridge_records_by_tier(
            records,
            visible_row_indices=[0, 1, 2],
            prefetch_row_indices=[0, 1, 2],
            selected_row=None,
        )
        names = [r.name for r in tiers["visible"]]
        self.assertEqual(names, ["mesh.stl", "other.obj"])
        key = _norm_path_key(records[0].path)
        self.assertTrue(key)


if __name__ == "__main__":
    unittest.main()
