"""Tests for render timing profiler and cache fingerprinting."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from meshcorral.services.render.render_cache import build_fingerprint, read_cached_png, write_cached_png
from meshcorral.services.render.render_pipeline_policy import resolve_render_mode
from meshcorral.services.render.render_timing_profiler import RenderTimingProfiler


class TestRenderTimingProfiler(unittest.TestCase):
    def test_finish_writes_json_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "render_timing.log"
            with mock.patch(
                "meshcorral.services.render.render_timing_profiler.TIMING_LOG_PATH",
                log_path,
            ):
                profiler = RenderTimingProfiler(
                    Path("C:/sample.stl"),
                    file_size_mb=1.5,
                    extension=".stl",
                    is_network_path=False,
                )
                profiler.add_stage_seconds("load_import", 0.12)
                record = profiler.finish(error_message=None)
            self.assertIsNone(record.error_message)
            self.assertGreater(record.total_s, 0.0)
            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            payload = json.loads(lines[0])
            self.assertEqual(payload["extension"], ".stl")
            self.assertAlmostEqual(payload["load_import_s"], 0.12, places=3)

    def test_slowest_stage_picks_max(self) -> None:
        profiler = RenderTimingProfiler(
            Path("O:/mesh.obj"),
            file_size_mb=10.0,
            extension=".obj",
            is_network_path=True,
        )
        profiler.add_stage_seconds("stage_copy", 2.0)
        profiler.add_stage_seconds("load_import", 0.5)
        record = profiler.finish()
        name, sec = record.slowest_stage()
        self.assertEqual(name, "stage_copy")
        self.assertAlmostEqual(sec, 2.0, places=3)


class TestRenderCache(unittest.TestCase):
    def test_fingerprint_cache_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "cube.stl"
            src.write_bytes(b"solid x\nendsolid x\n")
            st = src.stat()
            with mock.patch(
                "meshcorral.services.render.render_cache.RENDER_CACHE_DIR",
                Path(tmp) / "cache",
            ):
                write_cached_png(
                    src,
                    size_bytes=st.st_size,
                    mtime=st.st_mtime,
                    max_px=256,
                    render_mode="proxy",
                    png_bytes=b"\x89PNG\r\n",
                )
                hit = read_cached_png(
                    src,
                    size_bytes=st.st_size,
                    mtime=st.st_mtime,
                    max_px=256,
                    render_mode="proxy",
                )
            self.assertEqual(hit, b"\x89PNG\r\n")

    def test_fingerprint_changes_when_mtime_changes(self) -> None:
        a = build_fingerprint(
            Path("C:/a.stl"),
            size_bytes=100,
            mtime=1.0,
            max_px=256,
            render_mode="balanced",
        )
        b = build_fingerprint(
            Path("C:/a.stl"),
            size_bytes=100,
            mtime=2.0,
            max_px=256,
            render_mode="balanced",
        )
        self.assertNotEqual(a, b)


class TestRenderPipelinePolicy(unittest.TestCase):
    def test_large_file_uses_proxy_when_not_hq(self) -> None:
        big = 60 * 1024 * 1024
        mode = resolve_render_mode(
            Path("C:/big.stl"),
            size_bytes=big,
            high_quality=False,
            for_auto_enqueue=False,
        )
        self.assertEqual(mode, "proxy")

    def test_manual_hq_mode(self) -> None:
        mode = resolve_render_mode(
            Path("C:/big.stl"),
            size_bytes=60 * 1024 * 1024,
            high_quality=True,
            for_auto_enqueue=False,
        )
        self.assertEqual(mode, "high")

    def test_small_local_uses_balanced(self) -> None:
        mode = resolve_render_mode(
            Path("C:/small.stl"),
            size_bytes=1024 * 1024,
            high_quality=False,
            for_auto_enqueue=False,
        )
        self.assertEqual(mode, "balanced")


if __name__ == "__main__":
    unittest.main()
