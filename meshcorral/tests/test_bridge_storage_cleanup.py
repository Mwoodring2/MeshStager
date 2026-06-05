"""Tests for bridge storage cleanup helpers (no GUI, no Blender)."""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from meshcorral.app.bridge.job_runner import RESULT_BASENAME, resolve_bridge_paths
from meshcorral.app.bridge.storage_cleanup import (
    BridgeCleanupManualMode,
    directory_tree_size_bytes,
    execute_cleanup,
    format_byte_size_human,
    passes_age_mtime,
    path_must_be_under_bridge_root,
    plan_manual_cleanup,
    plan_startup_retention,
)


class TestBridgeStorageCleanup(unittest.TestCase):
    def test_path_guard_rejects_outside_tree(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "bridge"
            root.mkdir()
            inside = root / "outputs" / "blender_bridge" / "abc"
            inside.mkdir(parents=True)
            outside = Path(td) / "escape"
            outside.mkdir()
            self.assertTrue(path_must_be_under_bridge_root(root, inside))
            self.assertFalse(path_must_be_under_bridge_root(root, outside))

    def test_passes_age_respects_cutoff(self) -> None:
        now = 1_000_000.0
        self.assertTrue(passes_age_mtime(now - 10_000.0, now, 3600.0))
        self.assertFalse(passes_age_mtime(now - 10.0, now, 3600.0))
        self.assertTrue(passes_age_mtime(now - 10.0, now, None))

    def test_format_byte_size_human(self) -> None:
        self.assertIn("MB", format_byte_size_human(3 * 1024 * 1024))
        self.assertIn("GB", format_byte_size_human(3 * 1024 * 1024 * 1024))

    def test_plan_and_execute_removes_only_bridge_root(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            old = os.environ.get("ROUNDUP_BRIDGE_ROOT")
            os.environ["ROUNDUP_BRIDGE_ROOT"] = td
            try:
                bp = resolve_bridge_paths()
                root = Path(td).resolve()
                out = bp.outputs_root / "job-old"
                out.mkdir(parents=True)
                (out / RESULT_BASENAME).write_text(
                    json.dumps(
                        {
                            "job_id": "job-old",
                            "job_type": "generate_thumbnail",
                            "status": "complete",
                            "source_file": "C:/mesh/x.stl",
                            "output_dir": str(out),
                            "thumbnail_path": None,
                            "error_message": None,
                        }
                    ),
                    encoding="utf-8",
                )
                old_stamp = time.time() - (10 * 86400)
                os.utime(out / RESULT_BASENAME, (old_stamp, old_stamp))

                summary = plan_manual_cleanup(
                    bp,
                    bridge_root=root,
                    mode=BridgeCleanupManualMode.COMPLETED_BRIDGE_JOBS_ONLY,
                    now_ts=time.time(),
                    min_age_seconds=float(3600.0),
                )
                self.assertGreaterEqual(len(summary.paths), 1)
                pre, _ = directory_tree_size_bytes(out)
                self.assertGreater(pre, 0)

                result = execute_cleanup(summary, bridge_root=root)
                self.assertGreaterEqual(result.deleted, 1)
                self.assertFalse(out.exists())
            finally:
                if old is None:
                    os.environ.pop("ROUNDUP_BRIDGE_ROOT", None)
                else:
                    os.environ["ROUNDUP_BRIDGE_ROOT"] = old

    def test_startup_retention_maps_days(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            old = os.environ.get("ROUNDUP_BRIDGE_ROOT")
            os.environ["ROUNDUP_BRIDGE_ROOT"] = td
            try:
                bp = resolve_bridge_paths()
                root = Path(td).resolve()
                stale = bp.outputs_root / "stale"
                stale.mkdir(parents=True)
                (stale / RESULT_BASENAME).write_text(
                    json.dumps(
                        {
                            "job_id": "stale",
                            "job_type": "generate_thumbnail",
                            "status": "complete",
                            "source_file": "C:/mesh/a.stl",
                            "output_dir": str(stale),
                            "thumbnail_path": None,
                            "error_message": None,
                        }
                    ),
                    encoding="utf-8",
                )
                ts = time.time() - (40 * 86400)
                os.utime(stale / RESULT_BASENAME, (ts, ts))

                summary = plan_startup_retention(
                    bp,
                    bridge_root=root,
                    retention_days=30,
                    now_ts=time.time(),
                )
                self.assertTrue(any(p.path == stale.resolve() for p in summary.paths))
            finally:
                if old is None:
                    os.environ.pop("ROUNDUP_BRIDGE_ROOT", None)
                else:
                    os.environ["ROUNDUP_BRIDGE_ROOT"] = old


if __name__ == "__main__":
    unittest.main()
