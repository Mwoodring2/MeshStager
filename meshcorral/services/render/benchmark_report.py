"""Aggregate benchmark results and bottleneck recommendations (RC2 diagnostics)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

from meshcorral.services.render.render_timing_profiler import RenderTimingRecord, format_benchmark_table

logger = logging.getLogger(__name__)

# Recommendation text keyed by aggregated bucket.
_REC_NETWORK = "Bottleneck appears to be network copy"
_REC_MESH_IMPORT = "Bottleneck appears to be mesh import"
_REC_HQ_RENDER = "Bottleneck appears to be HQ render"
_REC_CACHE_WRITE = "Bottleneck appears to be cache write"


@dataclass
class BenchmarkSummary:
    """RC2 benchmark rollup across measured file runs (excludes warm-up)."""

    cold_start_overhead_s: float = 0.0
    records: list[RenderTimingRecord] = field(default_factory=list)
    repeat_count: int = 1

    def measured_records(self) -> list[RenderTimingRecord]:
        """Runs included in averages (all non-warm-up records)."""
        return list(self.records)

    def uncached_records(self) -> list[RenderTimingRecord]:
        return [r for r in self.records if not r.used_cached_output]

    def cache_hit_count(self) -> int:
        return sum(1 for r in self.records if r.used_cached_output)

    def cache_hit_rate(self) -> float:
        total = len(self.records)
        if total == 0:
            return 0.0
        return float(self.cache_hit_count()) / float(total)

    def proxy_render_count(self) -> int:
        return sum(1 for r in self.records if r.render_mode == "proxy")

    def hq_render_count(self) -> int:
        return sum(1 for r in self.records if r.render_mode == "high")

    def average_total_local_s(self) -> float | None:
        local = [r for r in self.records if not r.is_network_path]
        if not local:
            return None
        return sum(r.total_s for r in local) / len(local)

    def average_total_network_s(self) -> float | None:
        remote = [r for r in self.records if r.is_network_path]
        if not remote:
            return None
        return sum(r.total_s for r in remote) / len(remote)

    def stage_totals_uncached(self) -> dict[str, float]:
        """Sum stage seconds for uncached runs only (real work)."""
        totals = {
            "stage_copy": 0.0,
            "load_import": 0.0,
            "geometry_metadata": 0.0,
            "preview_proxy": 0.0,
            "render_hq": 0.0,
            "write_cache": 0.0,
        }
        for rec in self.uncached_records():
            for name, value in rec.stage_rows():
                totals[name] = totals.get(name, 0.0) + value
        return totals

    def slowest_stage_overall(self) -> tuple[str, float]:
        totals = self.stage_totals_uncached()
        if not totals or max(totals.values()) <= 0.0:
            return ("none", 0.0)
        name, value = max(totals.items(), key=lambda item: item[1])
        return name, value


def aggregate_stage_buckets(totals: dict[str, float]) -> dict[str, float]:
    """Map raw stages into recommendation buckets."""
    return {
        "network_copy": totals.get("stage_copy", 0.0),
        "mesh_import": (
            totals.get("load_import", 0.0)
            + totals.get("geometry_metadata", 0.0)
            + totals.get("preview_proxy", 0.0)
        ),
        "hq_render": totals.get("render_hq", 0.0),
        "cache_write": totals.get("write_cache", 0.0),
    }


def recommend_bottleneck(
    summary: BenchmarkSummary,
    *,
    cold_start_overhead_s: float | None = None,
) -> str:
    """
    Pick a one-line recommendation from the slowest real-work bucket.

    Uses uncached runs only so cache hits do not skew stage totals.
    Cold-start overhead is reported separately and does not select mesh import alone
    unless it dominates uncached import time.
    """
    cold = cold_start_overhead_s
    if cold is None:
        cold = summary.cold_start_overhead_s

    totals = summary.stage_totals_uncached()
    buckets = aggregate_stage_buckets(totals)
    if not buckets or max(buckets.values()) <= 0.0:
        if cold > 0.0:
            return _REC_MESH_IMPORT
        return _REC_MESH_IMPORT

    # Cold start is import/setup tax — call out when it dominates measured import time.
    mesh_bucket = buckets.get("mesh_import", 0.0)
    if cold > 0.0 and cold >= mesh_bucket and cold >= buckets.get("network_copy", 0.0):
        return _REC_MESH_IMPORT

    name = max(buckets.items(), key=lambda item: item[1])[0]
    if name == "network_copy":
        return _REC_NETWORK
    if name == "mesh_import":
        return _REC_MESH_IMPORT
    if name == "hq_render":
        return _REC_HQ_RENDER
    if name == "cache_write":
        return _REC_CACHE_WRITE
    return _REC_MESH_IMPORT


def format_rc2_summary(summary: BenchmarkSummary) -> str:
    """Human-readable RC2 benchmark report sections."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("RC2 Performance Summary")
    lines.append("=" * 60)
    from meshcorral.services.render.benchmark_warmup import WARMUP_NOTE

    lines.append(f"Cold start overhead:     {summary.cold_start_overhead_s:10.3f} s")
    lines.append(f"  ({WARMUP_NOTE})")
    lines.append(f"Measured runs:           {len(summary.records):10d}  (repeat={summary.repeat_count})")

    local_avg = summary.average_total_local_s()
    if local_avg is not None:
        lines.append(f"Average local file time: {local_avg:10.3f} s")
    else:
        lines.append("Average local file time:        n/a")

    net_avg = summary.average_total_network_s()
    if net_avg is not None:
        lines.append(f"Average network time:    {net_avg:10.3f} s")
    else:
        lines.append("Average network time:           n/a")

    stage_name, stage_sec = summary.slowest_stage_overall()
    lines.append(f"Slowest stage overall:   {stage_name} ({stage_sec:.3f} s total, uncached)")

    hits = summary.cache_hit_count()
    total = len(summary.records)
    rate_pct = summary.cache_hit_rate() * 100.0
    lines.append(f"Cache hit rate:          {hits}/{total} ({rate_pct:.1f}%)")

    lines.append(
        f"Proxy vs HQ renders:     proxy={summary.proxy_render_count()}  "
        f"hq={summary.hq_render_count()}"
    )
    lines.append("")
    lines.append(format_benchmark_table(summary.uncached_records() or summary.records))
    lines.append("")
    lines.append(f"Recommendation: {recommend_bottleneck(summary)}")
    lines.append("=" * 60)
    return "\n".join(lines)


def run_warm_up(
    pipeline: object,
    sample_path: Path,
    *,
    high_quality: bool,
    for_auto_enqueue: bool,
) -> float:
    """
    One throwaway render to load trimesh/numpy/render modules.

    Returns elapsed seconds (cold start overhead). Not included in measured records.
    """
    from meshcorral.services.render.benchmark_warmup import WARMUP_NOTE

    logger.info("Warm-up render: %s — %s", sample_path, WARMUP_NOTE)
    t0 = time.perf_counter()
    try:
        pipeline.render_png_bytes(  # type: ignore[attr-defined]
            sample_path,
            max_px=256,
            high_quality=high_quality,
            for_auto_enqueue=for_auto_enqueue,
            write_timing_log=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Warm-up render failed (continuing): %s", exc)
    return time.perf_counter() - t0
