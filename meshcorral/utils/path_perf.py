"""Path performance hints for large and network-like folders (Prime Performance Pass)."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Prime Performance Pass v0.3 — Phase 1 caps (auto-queue after scan).
AUTO_QUEUE_CAP_LOCAL: int = 50
AUTO_QUEUE_CAP_NETWORK: int = 25

# Phase 2: async thumbnail decode workers (never scale to CPU count on shares).
PRIME_PERF_MAX_DECODE_WORKERS: int = 2

# Treat scans as "large folder" when at least this many files were indexed.
LARGE_FOLDER_RECORD_COUNT: int = 200

# Slow scan threshold (seconds) — network disks or deep trees.
SLOW_SCAN_ELAPSED_SECONDS: float = 8.0

# Prime Performance v0.7 — remote-mode throttle defaults.
PRIME_PERF_REMOTE_MAX_DECODE_WORKERS: int = 1
PRIME_PERF_REMOTE_PRIMER_BATCH_SIZE: int = 16
PRIME_PERF_LOCAL_PRIMER_BATCH_SIZE: int = 64
PRIME_PERF_REMOTE_VIEWPORT_DEBOUNCE_MS: int = 240
PRIME_PERF_LOCAL_VIEWPORT_DEBOUNCE_MS: int = 120
PRIME_PERF_REMOTE_ENRICHMENT_BATCH: int = 32
PRIME_PERF_LOCAL_ENRICHMENT_BATCH: int = 96
PRIME_PERF_REMOTE_ENRICHMENT_SLEEP_S: float = 0.02
PRIME_PERF_LOCAL_ENRICHMENT_SLEEP_S: float = 0.0


@dataclass(frozen=True, slots=True)
class RemoteThrottleProfile:
    """
    Per-scan throttle settings used by the UI to back off on UNC / mapped shares.

    Returned by :func:`remote_throttle_profile`; values match the local defaults
    when *network_like* is False so callers can apply uniformly.
    """

    network_like: bool
    decode_workers: int
    primer_batch_size: int
    viewport_debounce_ms: int
    enrichment_batch_size: int
    enrichment_sleep_s: float


def remote_throttle_profile(network_like: bool) -> RemoteThrottleProfile:
    """Return the throttle profile for the current scan target."""
    if network_like:
        return RemoteThrottleProfile(
            network_like=True,
            decode_workers=PRIME_PERF_REMOTE_MAX_DECODE_WORKERS,
            primer_batch_size=PRIME_PERF_REMOTE_PRIMER_BATCH_SIZE,
            viewport_debounce_ms=PRIME_PERF_REMOTE_VIEWPORT_DEBOUNCE_MS,
            enrichment_batch_size=PRIME_PERF_REMOTE_ENRICHMENT_BATCH,
            enrichment_sleep_s=PRIME_PERF_REMOTE_ENRICHMENT_SLEEP_S,
        )
    return RemoteThrottleProfile(
        network_like=False,
        decode_workers=PRIME_PERF_MAX_DECODE_WORKERS,
        primer_batch_size=PRIME_PERF_LOCAL_PRIMER_BATCH_SIZE,
        viewport_debounce_ms=PRIME_PERF_LOCAL_VIEWPORT_DEBOUNCE_MS,
        enrichment_batch_size=PRIME_PERF_LOCAL_ENRICHMENT_BATCH,
        enrichment_sleep_s=PRIME_PERF_LOCAL_ENRICHMENT_SLEEP_S,
    )

# Win32 GetDriveTypeW: remote / webdav-style targets.
_WIN32_DRIVE_REMOTE: int = 4


def is_unc_path(path: Path) -> bool:
    """Return True for UNC paths (``\\\\server\\share\\...``)."""
    raw = str(path)
    if raw.startswith("\\\\"):
        return True
    return path.drive.startswith("\\\\")


def _windows_drive_root(path: Path) -> str | None:
    """Return ``'C:\\\\'`` for a path on a drive letter, else None."""
    drive = path.drive
    if not drive or drive.startswith("\\\\"):
        return None
    return f"{drive}\\"


def _windows_drive_is_remote(drive_root: str) -> bool:
    """Best-effort mapped/network drive detection on Windows."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        dtype = int(kernel32.GetDriveTypeW(drive_root))
        return dtype == _WIN32_DRIVE_REMOTE
    except (AttributeError, OSError, TypeError, ValueError):
        return False


def is_network_like_path(path: Path) -> bool:
    """
    Return True when *path* is likely on a server or high-latency share.

    Heuristics: UNC prefix, or Windows drive type ``DRIVE_REMOTE``.
    """
    try:
        p = path.expanduser()
    except (OSError, RuntimeError):
        p = path
    if is_unc_path(p):
        return True
    root = _windows_drive_root(p)
    if root is not None and _windows_drive_is_remote(root):
        return True
    # Fallback: explicit UNC in original string before resolve.
    return str(path).startswith("\\\\")


def is_slow_scan_elapsed(scan_elapsed_s: float | None, threshold: float = SLOW_SCAN_ELAPSED_SECONDS) -> bool:
    """Return True when a completed scan took at least *threshold* seconds."""
    if scan_elapsed_s is None:
        return False
    try:
        return float(scan_elapsed_s) >= float(threshold)
    except (TypeError, ValueError):
        return False


def is_large_folder_scan(record_count: int, *, threshold: int = LARGE_FOLDER_RECORD_COUNT) -> bool:
    """Return True when the working set exceeds the large-folder threshold."""
    return int(record_count) >= int(threshold)


def is_prime_perf_scan(
    scan_root: Path,
    record_count: int,
    scan_elapsed_s: float | None,
) -> bool:
    """
    Return True when Prime Performance Pass lazy/visible-first behavior should apply.

    Active for network-like roots, large working sets, or slow scans.
    """
    if is_network_like_path(scan_root):
        return True
    if is_large_folder_scan(record_count):
        return True
    if is_slow_scan_elapsed(scan_elapsed_s):
        return True
    return False


def effective_auto_thumbnail_cap(
    scan_root: Path,
    record_count: int,
    scan_elapsed_s: float | None,
    settings_cap: int,
    *,
    unlimited_cap: int,
) -> int:
    """
    Cap for auto-queued thumbnail jobs after a scan.

    Network-like scans use :data:`AUTO_QUEUE_CAP_NETWORK`; other prime-perf scans
    use :data:`AUTO_QUEUE_CAP_LOCAL`. Small fast local scans keep the user setting.
    """
    if not is_prime_perf_scan(scan_root, record_count, scan_elapsed_s):
        if settings_cap == unlimited_cap:
            return unlimited_cap
        return max(0, int(settings_cap))

    perf_cap = (
        AUTO_QUEUE_CAP_NETWORK
        if is_network_like_path(scan_root)
        else AUTO_QUEUE_CAP_LOCAL
    )
    if settings_cap == unlimited_cap:
        return perf_cap
    return min(max(0, int(settings_cap)), perf_cap)


def perf_status_message(
    scan_root: Path,
    record_count: int,
    scan_elapsed_s: float | None,
) -> str | None:
    """User-facing hint for large/server folder mode, or None when not applicable."""
    if not is_prime_perf_scan(scan_root, record_count, scan_elapsed_s):
        return None
    if is_network_like_path(scan_root):
        return "Server folder detected: visible thumbnails load first."
    return "Large folder mode: thumbnails load as you browse."
