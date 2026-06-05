"""Safe cleanup of Blender Bridge runtime artifacts under the bridge root only."""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from meshcorral.app.bridge.job_runner import (
    RESULT_BASENAME,
    BridgePaths,
    bridge_runtime_root,
)

logger = logging.getLogger(__name__)


def queue_job_descriptor_path(paths: BridgePaths, job_id: str) -> dict[str, Path]:
    """Per-queue candidate paths keyed by logical queue name."""
    name = _queue_job_filename(job_id)
    return {
        "complete": paths.jobs_complete / name,
        "failed": paths.jobs_failed / name,
        "cancelled": paths.jobs_cancelled / name,
    }


def _queue_job_filename(job_id: str) -> str:
    return f"{job_id}.job.json"


def job_id_from_descriptor_path(path: Path) -> str | None:
    """Parse ``<job_id>.job.json`` from a queue descriptor filename."""
    if not path.is_file():
        return None
    n = path.name
    suf = ".job.json"
    if len(n) <= len(suf) or not n.endswith(suf):
        return None
    return n[: -len(suf)]


def path_must_be_under_bridge_root(bridge_root: Path, candidate: Path) -> bool:
    """Return True only if *candidate* resolves strictly under *bridge_root*."""
    try:
        br = bridge_root.resolve()
        cand = candidate.resolve()
    except OSError:
        return False
    try:
        cand.relative_to(br)
        return cand != br
    except ValueError:
        return False


def directory_tree_size_bytes(path: Path) -> tuple[int, int]:
    """Return ``(total_bytes, skipped_files_count)`` while walking directories."""
    total = 0
    skipped = 0
    try:
        for root, _, files in os.walk(path, followlinks=False):
            for name in files:
                fp = Path(root) / name
                try:
                    total += int(fp.stat().st_size)
                except OSError:
                    skipped += 1
    except OSError:
        skipped += 1
    return total, skipped


def file_or_dir_size_bytes(path: Path) -> tuple[int, int]:
    """Return size bytes for files; recursive sum for dirs (best-effort)."""
    try:
        if path.is_symlink():
            return 0, 0
        if path.is_file():
            try:
                return int(path.stat().st_size), 0
            except OSError:
                return 0, 1
        if path.is_dir():
            return directory_tree_size_bytes(path)
    except OSError:
        return 0, 1
    return 0, 0


def format_byte_size_human(num_bytes: int) -> str:
    """Short English size hint for dialogs (MB/GB thresholds)."""
    n = float(max(0, int(num_bytes)))
    if n >= 1073741824.0:
        return f"{n / 1073741824:.2f} GB"
    if n >= 1048576.0:
        return f"{n / 1048576:.1f} MB"
    if n >= 1024.0:
        return f"{n / 1024:.1f} KB"
    return f"{int(n)} bytes"


AGE_ALL = object()


def min_age_seconds_for_ui_choice(kind: object) -> float | None:
    """
    Translate UI picker values to bridge retention seconds.

    - ``AGE_ALL`` means **no minimum age**: everything matching the manual mode is eligible.

    Accepted string-like keys include ``\"7\"``, ``\"30\"``, ``\"90\"`` (defaults to ``30``
    days on unknown inputs for safety — callers should constrain via combo.)
    """
    if kind is AGE_ALL:
        return None
    k = str(kind).strip().lower()
    if k == "all":
        return None
    mapping = {"7": 7 * 86400, "30": 30 * 86400, "90": 90 * 86400}
    secs = mapping.get(k)
    if secs is None:
        return float(30 * 86400)
    return float(secs)


def passes_age_mtime(mtime: float, now_ts: float, min_age_seconds: float | None) -> bool:
    """Include items whose last activity is at least ``min_age_seconds`` old."""
    if min_age_seconds is None:
        return True
    cutoff = now_ts - float(min_age_seconds)
    return float(mtime) <= cutoff


class BridgeCleanupManualMode(str, Enum):
    """Manual cleanup presets."""

    CLEAN_OLD_BRIDGE_OUTPUT_JOBS = "clean_old_jobs"
    FAILED_BRIDGE_JOBS_ONLY = "failed_only"
    COMPLETED_BRIDGE_JOBS_ONLY = "complete_only"


def read_output_root_status_mtime(output_dir: Path) -> tuple[str, float]:
    """Return canonical status string (``unknown`` if missing) plus ref mtime for age checks."""
    result = output_dir / RESULT_BASENAME
    if result.is_file():
        try:
            data = json.loads(result.read_text(encoding="utf-8"))
            status = str(data.get("status", "")).strip().lower()
            if not status:
                status = "unknown"
            return status, float(result.stat().st_mtime)
        except (OSError, UnicodeError, json.JSONDecodeError):
            try:
                return "unknown", float(result.stat().st_mtime)
            except OSError:
                pass
    try:
        return "unknown", float(output_dir.stat().st_mtime)
    except OSError:
        return "unknown", 0.0


def _manual_mode_matches(mode: BridgeCleanupManualMode, status_norm: str) -> bool:
    st = status_norm.strip().lower()
    if mode is BridgeCleanupManualMode.CLEAN_OLD_BRIDGE_OUTPUT_JOBS:
        return st in {"complete", "failed", "cancelled", "unknown"}
    if mode is BridgeCleanupManualMode.FAILED_BRIDGE_JOBS_ONLY:
        return st == "failed"
    if mode is BridgeCleanupManualMode.COMPLETED_BRIDGE_JOBS_ONLY:
        return st == "complete"
    return False


@dataclass(frozen=True)
class PlannedPath:
    """One deletion candidate under the verified bridge root."""

    path: Path
    size_bytes: int
    skipped_measurement_files: int
    purpose: str


@dataclass(frozen=True)
class CleanupPlanSummary:
    """Pre-flight summary surfaced in confirmation dialogs."""

    bridge_root: Path
    outputs_root: Path
    paths: tuple[PlannedPath, ...]
    estimated_bytes: int
    skipped_measurement_files: int
    job_ids_distinct_count: int


def plan_manual_cleanup(
    bp: BridgePaths,
    *,
    bridge_root: Path,
    mode: BridgeCleanupManualMode,
    now_ts: float,
    min_age_seconds: float | None,
) -> CleanupPlanSummary:
    """
    Collect safe-to-delete filesystem nodes.

    Targets:
        - ``outputs/blender_bridge/<job_id>/`` when status/mtime matches filters
        - ``data/jobs/{complete|failed|cancelled}/<job_id>.job.json`` for matching job IDs

    Never traverses folders outside ``bridge_root``.
    """
    root = bridge_root.resolve()
    out_root = bp.outputs_root

    planned: dict[str, PlannedPath] = {}
    job_ids_seen: set[str] = set()
    skipped_measurement = 0

    try:
        if out_root.is_dir():
            for child in out_root.iterdir():
                if not child.is_dir():
                    continue
                job_id = child.name.strip()
                if not job_id:
                    continue
                if not path_must_be_under_bridge_root(root, child):
                    continue
                status, mt = read_output_root_status_mtime(child)
                if not _manual_mode_matches(mode, status):
                    continue
                if not passes_age_mtime(mt, now_ts, min_age_seconds):
                    continue

                sz, sk = file_or_dir_size_bytes(child)
                skipped_measurement += sk
                planned[str(child.resolve())] = PlannedPath(
                    path=child.resolve(),
                    size_bytes=int(sz),
                    skipped_measurement_files=int(sk),
                    purpose="bridge_output_folder",
                )
                job_ids_seen.add(job_id)

                for qp in queue_job_descriptor_path(bp, job_id).values():
                    if not qp.is_file():
                        continue
                    if not path_must_be_under_bridge_root(root, qp):
                        continue
                    qs, qsk = file_or_dir_size_bytes(qp)
                    skipped_measurement += qsk
                    planned[str(qp.resolve())] = PlannedPath(
                        path=qp.resolve(),
                        size_bytes=int(qs),
                        skipped_measurement_files=int(qsk),
                        purpose="queue_descriptor",
                    )

        orphan_dirs = (
            bp.jobs_complete,
            bp.jobs_failed,
            bp.jobs_cancelled,
        )
        for od in orphan_dirs:
            if not od.is_dir():
                continue
            try:
                for jf in od.iterdir():
                    if not jf.is_file():
                        continue
                    jid = job_id_from_descriptor_path(jf)
                    if not jid:
                        continue
                    if (out_root / jid).exists():
                        continue
                    if not path_must_be_under_bridge_root(root, jf):
                        continue
                    try:
                        jmt = float(jf.stat().st_mtime)
                    except OSError:
                        continue
                    if not passes_age_mtime(jmt, now_ts, min_age_seconds):
                        continue
                    status_in_file = ""
                    try:
                        data = json.loads(jf.read_text(encoding="utf-8"))
                        status_in_file = str(data.get("status", "")).strip().lower()
                    except (OSError, UnicodeError, json.JSONDecodeError):
                        status_in_file = "unknown"

                    eligible = False
                    if mode is BridgeCleanupManualMode.CLEAN_OLD_BRIDGE_OUTPUT_JOBS:
                        eligible = status_in_file in {"complete", "failed", "cancelled", "unknown"}
                    elif mode is BridgeCleanupManualMode.FAILED_BRIDGE_JOBS_ONLY:
                        eligible = status_in_file == "failed"
                    elif mode is BridgeCleanupManualMode.COMPLETED_BRIDGE_JOBS_ONLY:
                        eligible = status_in_file == "complete"

                    if not eligible:
                        continue

                    sz2, sk2 = file_or_dir_size_bytes(jf)
                    skipped_measurement += sk2
                    planned[str(jf.resolve())] = PlannedPath(
                        path=jf.resolve(),
                        size_bytes=int(sz2),
                        skipped_measurement_files=int(sk2),
                        purpose="orphan_queue_descriptor",
                    )
                    job_ids_seen.add(jid)
            except OSError:
                continue
    except OSError as exc:
        logger.warning("Plan cleanup scan failed under %s: %s", out_root, exc)

    ordered_paths = tuple(sorted(planned.values(), key=lambda item: str(item.path).lower()))
    est = int(sum(max(0, p.size_bytes) for p in ordered_paths))
    distinct_jobs = int(len(job_ids_seen))
    return CleanupPlanSummary(
        bridge_root=root,
        outputs_root=out_root,
        paths=ordered_paths,
        estimated_bytes=est,
        skipped_measurement_files=int(skipped_measurement),
        job_ids_distinct_count=distinct_jobs,
    )


def plan_startup_retention(
    bp: BridgePaths,
    *,
    bridge_root: Path,
    retention_days: int,
    now_ts: float | None = None,
) -> CleanupPlanSummary:
    """Auto retention at startup uses the conservative broad manual mode."""
    secs = float(max(1, retention_days)) * 86400.0
    now = time.time() if now_ts is None else float(now_ts)
    return plan_manual_cleanup(
        bp,
        bridge_root=bridge_root,
        mode=BridgeCleanupManualMode.CLEAN_OLD_BRIDGE_OUTPUT_JOBS,
        now_ts=now,
        min_age_seconds=secs,
    )


@dataclass(frozen=True)
class CleanupExecuted:
    """Post-delete bookkeeping."""

    attempted: int
    deleted: int
    errors: int
    freed_bytes_logged: int


def execute_cleanup(summary: CleanupPlanSummary, *, bridge_root: Path) -> CleanupExecuted:
    """Apply the plan; skips locked/unwritable entries and continues."""

    root = bridge_root.resolve()
    attempted = 0
    deleted = 0
    errors = 0
    freed_logged = 0

    items = sorted(summary.paths, key=lambda p: (p.path.is_dir(), str(p.path).lower()))

    for item in items:
        attempted += 1
        tgt = item.path
        if not path_must_be_under_bridge_root(root, tgt):
            logger.warning("Refusing deletion outside bridge root: %s", tgt)
            errors += 1
            continue

        freed_logged += int(max(0, item.size_bytes))

        try:
            if tgt.is_symlink():
                tgt.unlink(missing_ok=True)
                deleted += 1
                continue
            if tgt.is_file():
                try:
                    tgt.unlink()
                    deleted += 1
                except OSError:
                    errors += 1
                continue
            if tgt.is_dir():
                shutil.rmtree(tgt, ignore_errors=False)
                deleted += 1
                continue
        except OSError as exc:
            logger.warning("Deletion failed for %s: %s", tgt, exc)
            errors += 1

    return CleanupExecuted(
        attempted=int(attempted),
        deleted=int(deleted),
        errors=int(errors),
        freed_bytes_logged=int(freed_logged),
    )
