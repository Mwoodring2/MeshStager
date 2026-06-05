"""
Benchmark mesh render pipeline stages for files under a folder (RC2 diagnostics).

Usage (repo root)::

    python scripts/benchmark_render_pipeline.py "path\\to\\test_folder"
    python scripts/benchmark_render_pipeline.py "path\\to\\test_folder" --repeat 2
    python scripts/benchmark_render_pipeline.py "path" --clear-render-cache --clear-staging-cache

Warm-up runs once on an **internal mini STL** (under ``%LOCALAPPDATA%\\MeshStager\\benchmark\\``)
so trimesh/Python import cost is reported as **cold start overhead**, not conflated with
a large file from the test folder. Use ``--warm-up-user-file`` only for debugging.

Logs each measured run to ``%LOCALAPPDATA%\\MeshStager\\logs\\render_timing.log``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from meshcorral.services.render.benchmark_report import (
    BenchmarkSummary,
    format_rc2_summary,
    run_warm_up,
)
from meshcorral.services.render.benchmark_warmup import WARMUP_NOTE, resolve_warmup_mesh_path
from meshcorral.services.render.mesh_render_pipeline import MeshRenderPipeline
from meshcorral.services.render.render_cache import clear_render_cache
from meshcorral.services.render.render_staging_cache import clear_staging_cache
from meshcorral.services.thumbnails.native_thumbnail_backend import NativeThumbnailBackend

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("benchmark_render_pipeline")

_MESH_EXTS = NativeThumbnailBackend._EXTS


def _iter_mesh_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in _MESH_EXTS else []
    files: list[Path] = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() in _MESH_EXTS:
            files.append(path)
    return sorted(files)


def run_measured_pass(
    pipeline: MeshRenderPipeline,
    paths: list[Path],
    *,
    high_quality: bool,
    for_auto_enqueue: bool,
    repeat: int,
) -> list:
    """Run benchmark files; return timing records (warm-up excluded)."""
    from meshcorral.services.render.render_timing_profiler import RenderTimingRecord

    records: list[RenderTimingRecord] = []
    print(f"{'File':<40} {'MB':>8} {'Net':>5} {'Mode':>8} {'Total(s)':>9} {'Slowest':>18} {'Run':>4}")
    print("-" * 102)

    for run_idx in range(1, max(1, int(repeat)) + 1):
        for path in paths:
            try:
                size_mb = path.stat().st_size / (1024.0 * 1024.0)
            except OSError:
                size_mb = 0.0
            try:
                _png, record, _geom = pipeline.render_png_bytes(
                    path,
                    max_px=512,
                    high_quality=high_quality,
                    for_auto_enqueue=for_auto_enqueue,
                )
                records.append(record)
                stage, sec = record.slowest_stage()
                net = "yes" if record.is_network_path else "no"
                cache = "cache" if record.used_cached_output else ""
                name = path.name[:38]
                print(
                    f"{name:<40} {size_mb:8.2f} {net:>5} {record.render_mode:>8} "
                    f"{record.total_s:9.3f} {stage}({sec:.3f}s) {run_idx:>4} {cache}"
                )
            except Exception as exc:  # noqa: BLE001
                logger.error("Failed %s (run %s): %s", path, run_idx, exc)
                print(
                    f"{path.name[:38]:<40} {'—':>8} {'—':>5} {'fail':>8} "
                    f"{'—':>9} {'—':>18} {run_idx:>4}"
                )
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark MeshStager mesh render pipeline (RC2)")
    parser.add_argument("folder", type=str, help="Folder or single mesh file to benchmark")
    parser.add_argument(
        "--high-quality",
        action="store_true",
        help="Force high-quality render mode (default: proxy policy for large/network)",
    )
    parser.add_argument(
        "--max-files",
        type=int,
        default=20,
        help="Maximum number of mesh files to process (default 20)",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        metavar="N",
        help="Repeat the same file set N times (default 1; use 2+ to verify cache)",
    )
    parser.add_argument(
        "--no-warm-up",
        action="store_true",
        help="Skip warm-up pass (cold start will affect first file timings)",
    )
    parser.add_argument(
        "--warm-up-user-file",
        action="store_true",
        help="Use first benchmark file for warm-up (not recommended; inflates cold-start time)",
    )
    parser.add_argument(
        "--clear-render-cache",
        action="store_true",
        help="Clear render output cache before benchmarking",
    )
    parser.add_argument(
        "--clear-staging-cache",
        action="store_true",
        help="Clear network staging cache before benchmarking",
    )
    args = parser.parse_args(argv)

    if int(args.repeat) < 1:
        logger.error("--repeat must be at least 1")
        return 1

    if args.clear_render_cache:
        n = clear_render_cache()
        logger.info("Cleared %d render cache file(s)", n)
    if args.clear_staging_cache:
        n = clear_staging_cache()
        logger.info("Cleared %d staging cache file(s)", n)

    root = Path(args.folder)
    if not root.exists():
        logger.error("Path does not exist: %s", root)
        return 1

    paths = _iter_mesh_files(root)[: max(0, int(args.max_files))]
    if not paths:
        logger.error("No mesh files (%s) under %s", ", ".join(sorted(_MESH_EXTS)), root)
        return 1

    pipeline = MeshRenderPipeline()
    high_quality = bool(args.high_quality)
    for_auto_enqueue = not high_quality

    cold_start_s = 0.0
    if not args.no_warm_up:
        user_warm = paths[0] if paths and args.warm_up_user_file else None
        sample = resolve_warmup_mesh_path(
            user_mesh=user_warm,
            allow_user_mesh=bool(args.warm_up_user_file),
        )
        cold_start_s = run_warm_up(
            pipeline,
            sample,
            high_quality=high_quality,
            for_auto_enqueue=for_auto_enqueue,
        )
        print(f"\nWarm-up complete: {cold_start_s:.3f}s cold start overhead")
        print(f"  {WARMUP_NOTE}\n")

    records = run_measured_pass(
        pipeline,
        paths,
        high_quality=high_quality,
        for_auto_enqueue=for_auto_enqueue,
        repeat=int(args.repeat),
    )

    print()
    if not records:
        logger.error("No successful benchmark runs")
        return 1

    summary = BenchmarkSummary(
        cold_start_overhead_s=cold_start_s,
        records=records,
        repeat_count=int(args.repeat),
    )
    print(format_rc2_summary(summary))
    print()
    print(f"Processed {len(records)} measured run(s) across {len(paths)} file(s).")
    print("See render_timing.log for JSON lines (warm-up excluded).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
