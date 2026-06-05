"""RC2 benchmark reporting and repeat/cache behavior tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from meshcorral.services.render.benchmark_report import (
    BenchmarkSummary,
    _REC_CACHE_WRITE,
    _REC_HQ_RENDER,
    _REC_MESH_IMPORT,
    _REC_NETWORK,
    recommend_bottleneck,
)
from meshcorral.services.render.render_cache import clear_render_cache, read_cached_png, write_cached_png
from meshcorral.services.render.render_timing_profiler import RenderTimingRecord


def _record(
    *,
    network: bool = False,
    cached: bool = False,
    mode: str = "standard",
    stage_copy: float = 0.0,
    load_import: float = 0.0,
    geometry: float = 0.0,
    proxy: float = 0.0,
    hq: float = 0.0,
    write_cache: float = 0.0,
    total: float = 1.0,
) -> RenderTimingRecord:
    return RenderTimingRecord(
        source_path="C:/test.stl" if not network else r"\\srv\share\test.stl",
        file_size_mb=1.0,
        extension=".stl",
        is_network_path=network,
        stage_copy_s=stage_copy,
        load_import_s=load_import,
        geometry_metadata_s=geometry,
        preview_proxy_s=proxy,
        render_hq_s=hq,
        write_cache_s=write_cache,
        total_s=total,
        render_mode=mode,
        used_cached_output=cached,
    )


class TestBenchmarkSummary(unittest.TestCase):
    def test_cache_hit_rate_on_repeat(self) -> None:
        first = _record(cached=False, load_import=1.0, total=1.0)
        second = _record(cached=True, total=0.01)
        summary = BenchmarkSummary(records=[first, second], repeat_count=2)
        self.assertEqual(summary.cache_hit_count(), 1)
        self.assertAlmostEqual(summary.cache_hit_rate(), 0.5, places=3)

    def test_warm_up_not_in_measured_records(self) -> None:
        """Cold start is tracked separately; only file runs appear in records."""
        measured = [_record(load_import=0.2)]
        summary = BenchmarkSummary(cold_start_overhead_s=4.0, records=measured, repeat_count=1)
        self.assertEqual(len(summary.measured_records()), 1)
        self.assertAlmostEqual(summary.cold_start_overhead_s, 4.0, places=3)
        uncached = summary.uncached_records()
        if len(uncached) != 1:
            self.fail(f"expected 1 uncached record, got {len(uncached)}")
        if uncached[0].load_import_s != 0.2:
            self.fail(f"unexpected load_import_s: {uncached[0].load_import_s}")

    def test_repeat_mode_record_count(self) -> None:
        paths_count = 2
        repeat = 3
        records = [_record() for _ in range(paths_count * repeat)]
        summary = BenchmarkSummary(records=records, repeat_count=repeat)
        expected = paths_count * repeat
        if len(summary.records) != expected:
            self.fail(f"expected {expected} records, got {len(summary.records)}")

    def test_proxy_vs_hq_counts(self) -> None:
        summary = BenchmarkSummary(
            records=[
                _record(mode="proxy"),
                _record(mode="proxy"),
                _record(mode="high"),
            ]
        )
        self.assertEqual(summary.proxy_render_count(), 2)
        self.assertEqual(summary.hq_render_count(), 1)


class TestRecommendBottleneck(unittest.TestCase):
    def test_network_copy_recommendation(self) -> None:
        summary = BenchmarkSummary(
            records=[_record(network=True, stage_copy=5.0, load_import=0.1)]
        )
        text = recommend_bottleneck(summary, cold_start_overhead_s=0.0)
        if text != _REC_NETWORK:
            self.fail(f"expected network recommendation, got {text!r}")

    def test_mesh_import_recommendation(self) -> None:
        summary = BenchmarkSummary(
            records=[_record(load_import=3.0, geometry=1.0, proxy=0.5)]
        )
        text = recommend_bottleneck(summary, cold_start_overhead_s=0.0)
        if text != _REC_MESH_IMPORT:
            self.fail(f"expected mesh import recommendation, got {text!r}")

    def test_hq_render_recommendation(self) -> None:
        summary = BenchmarkSummary(
            records=[_record(hq=4.0, load_import=0.1)]
        )
        text = recommend_bottleneck(summary, cold_start_overhead_s=0.0)
        if text != _REC_HQ_RENDER:
            self.fail(f"expected HQ recommendation, got {text!r}")

    def test_cache_write_recommendation(self) -> None:
        summary = BenchmarkSummary(
            records=[_record(write_cache=5.0, load_import=0.1)]
        )
        text = recommend_bottleneck(summary, cold_start_overhead_s=0.0)
        if text != _REC_CACHE_WRITE:
            self.fail(f"expected cache write recommendation, got {text!r}")

    def test_cached_runs_excluded_from_slowest_stage(self) -> None:
        """Cache hits should not dominate stage totals."""
        summary = BenchmarkSummary(
            records=[
                _record(cached=True, stage_copy=99.0, load_import=99.0),
                _record(cached=False, load_import=2.0, stage_copy=0.1),
            ]
        )
        name, _sec = summary.slowest_stage_overall()
        if name != "load_import":
            self.fail(f"expected load_import slowest, got {name}")

    def test_cold_start_does_not_inflate_file_load_in_summary(self) -> None:
        """Cold start lives on summary only; per-file load_import stays small."""
        summary = BenchmarkSummary(
            cold_start_overhead_s=10.0,
            records=[_record(load_import=0.05)],
        )
        measured_load = summary.uncached_records()[0].load_import_s
        if measured_load != 0.05:
            self.fail(f"per-file load_import should be 0.05, got {measured_load}")
        if summary.cold_start_overhead_s != 10.0:
            self.fail("cold start overhead should remain on summary, not in records")


class TestBenchmarkWarmUpIntegration(unittest.TestCase):
    def test_warm_up_uses_write_timing_log_false(self) -> None:
        from meshcorral.services.render.benchmark_report import run_warm_up

        pipeline = mock.MagicMock()
        sample = Path("C:/warm.stl")
        run_warm_up(pipeline, sample, high_quality=False, for_auto_enqueue=True)
        pipeline.render_png_bytes.assert_called_once()
        kwargs = pipeline.render_png_bytes.call_args.kwargs
        if kwargs.get("write_timing_log") is not False:
            self.fail("warm-up must pass write_timing_log=False")

    def test_resolve_warmup_defaults_to_internal_not_user_archive(self) -> None:
        from meshcorral.services.render.benchmark_warmup import (
            INTERNAL_WARMUP_FILENAME,
            resolve_warmup_mesh_path,
        )

        huge_user = Path("O:/Backup/puck/Chr_Puck_HighHand_001.obj")
        with tempfile.TemporaryDirectory() as tmp:
            bench_dir = Path(tmp) / "benchmark"
            with mock.patch(
                "meshcorral.services.render.benchmark_warmup.INTERNAL_WARMUP_DIR",
                bench_dir,
            ):
                path = resolve_warmup_mesh_path(user_mesh=huge_user, allow_user_mesh=False)
            if path.name != INTERNAL_WARMUP_FILENAME:
                self.fail(f"expected internal warm-up STL, got {path}")
            if "Backup" in str(path) or "puck" in str(path):
                self.fail("warm-up path must not point at user archive")
            if not path.is_file():
                self.fail("internal warm-up STL was not created")

    def test_resolve_warmup_user_file_only_when_allowed(self) -> None:
        from meshcorral.services.render.benchmark_warmup import resolve_warmup_mesh_path

        with tempfile.TemporaryDirectory() as tmp:
            user_stl = Path(tmp) / "user.stl"
            user_stl.write_bytes(b"solid x\nendsolid x\n")
            bench_dir = Path(tmp) / "bench"
            with mock.patch(
                "meshcorral.services.render.benchmark_warmup.INTERNAL_WARMUP_DIR",
                bench_dir,
            ):
                internal = resolve_warmup_mesh_path(user_mesh=user_stl, allow_user_mesh=False)
                explicit = resolve_warmup_mesh_path(user_mesh=user_stl, allow_user_mesh=True)
            if internal.resolve() == user_stl.resolve():
                self.fail("default warm-up must not use user file")
            if explicit.resolve() != user_stl.resolve():
                self.fail("allow_user_mesh=True should use user file")


class TestCacheSecondRun(unittest.TestCase):
    def test_cache_hit_on_second_read(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "bench.stl"
            src.write_bytes(b"solid x\nendsolid x\n")
            st = src.stat()
            cache_dir = Path(tmp) / "render_cache"
            with mock.patch(
                "meshcorral.services.render.render_cache.RENDER_CACHE_DIR",
                cache_dir,
            ):
                write_cached_png(
                    src,
                    size_bytes=st.st_size,
                    mtime=st.st_mtime,
                    max_px=512,
                    render_mode="standard",
                    png_bytes=b"\x89PNG\r\n\x1a\n",
                )
                first = read_cached_png(
                    src,
                    size_bytes=st.st_size,
                    mtime=st.st_mtime,
                    max_px=512,
                    render_mode="standard",
                )
                second = read_cached_png(
                    src,
                    size_bytes=st.st_size,
                    mtime=st.st_mtime,
                    max_px=512,
                    render_mode="standard",
                )
            if first is None or second is None:
                self.fail("expected cache hits on first and second read")
            if first != second:
                self.fail("cache bytes should match on repeat read")


class TestClearCaches(unittest.TestCase):
    def test_clear_render_cache_removes_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "rcache"
            cache_dir.mkdir()
            (cache_dir / "abc.png").write_bytes(b"x")
            with mock.patch(
                "meshcorral.services.render.render_cache.RENDER_CACHE_DIR",
                cache_dir,
            ):
                removed = clear_render_cache()
            if removed != 1:
                self.fail(f"expected 1 removed, got {removed}")
            if any(cache_dir.iterdir()):
                self.fail("cache dir should be empty")


if __name__ == "__main__":
    unittest.main()
