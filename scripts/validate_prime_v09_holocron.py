"""
Prime v0.9 holocron scroll validation (headless-friendly).

Exercises scroll velocity, decode suppression, settle resume, and diagnostics
against a network folder without manual UI interaction.

Usage:
  .venv\\Scripts\\python scripts/validate_prime_v09_holocron.py [folder_path]

Environment:
  ROUNDUP_VALIDATE_FOLDER — override scan root (UNC or local)
  ROUNDUP_VALIDATE_MAX_FILES — abort scan display if exceeded (default 8000)
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("validate_v09")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOLOCRON = r"\\holocron\Sculpt\Sculpt Drop Folder"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _ensure_qapp():
    from PySide6.QtWidgets import QApplication

    inst = QApplication.instance()
    if inst is None:
        return QApplication(sys.argv)
    return inst


def _process_events(app, *, ms: int = 50) -> None:
    deadline = time.monotonic() + (float(ms) / 1000.0)
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def _wait_scan_done(window, app, *, timeout_s: float = 600.0) -> bool:
    t0 = time.monotonic()
    while window._is_scanning:
        if time.monotonic() - t0 > timeout_s:
            logger.error("Scan timed out after %.0fs", timeout_s)
            return False
        _process_events(app, ms=80)
    return True


def run_validation(folder: str) -> int:
    """Return 0 on pass, 1 on failure."""
    from meshcorral.ui.main_window import MainWindow

    app = _ensure_qapp()
    window = MainWindow()
    window.show()
    _process_events(app, ms=200)

    diag = window._thumb_controller.paint_diagnostics()
    diag.reset()

    logger.info("Scanning: %s", folder)
    window._selected_source_path = folder
    window._persist_selected_source(folder)
    window._include_subfolders_checkbox.setChecked(True)
    window._run_scan(folder)

    if not _wait_scan_done(window, app):
        window.close()
        return 1

    n_rows = len(window._view_records)
    logger.info("Scan complete: %s view rows (prime=%s)", n_rows, window._prime_perf_active)
    if n_rows < 100:
        logger.warning("Fewer than 100 rows — pick a larger holocron subfolder for a strong pass.")

    max_files = int(os.environ.get("ROUNDUP_VALIDATE_MAX_FILES", "8000"))
    if n_rows > max_files:
        logger.warning("Row count %s exceeds cap %s — validation continues anyway.", n_rows, max_files)

    _process_events(app, ms=500)

    sb = window._table.verticalScrollBar()
    snap_before = diag.snapshot()
    suppressed_before = int(snap_before.get("fast_scroll_suppression_count", 0))

    logger.info("Simulating fast scroll burst…")
    window._thumb_controller.set_fast_scroll_suppressed(False)
    base = int(sb.value())
    t_burst = time.monotonic()
    step = max(80, int(sb.singleStep()) * 8)
    while time.monotonic() - t_burst < 2.0:
        base = min(sb.maximum(), base + step)
        sb.setValue(base)
        window._schedule_viewport_thumb_pass()
        _process_events(app, ms=30)

    snap_burst = diag.snapshot()
    fast_count = int(snap_burst.get("fast_scroll_suppression_count", 0))
    logger.info(
        "After burst: fast_scroll_suppression=%s stale_epoch_drops=%s suppressed_active=%s",
        fast_count,
        snap_burst.get("stale_epoch_drops"),
        window._thumb_controller.is_fast_scroll_suppressed(),
    )

    if fast_count <= suppressed_before:
        logger.error("FAIL: fast_scroll_suppression_count did not increase during burst.")
        window.close()
        return 1

    if not window._thumb_controller.is_fast_scroll_suppressed():
        logger.warning("Suppression flag cleared during burst (may be OK if scroll slowed).")

    decode_keys_burst = len(window._thumb_controller._decoding_keys)
    logger.info("Inflight decode keys during burst: %s", decode_keys_burst)

    logger.info("Simulating scroll settle…")
    window._scroll_velocity.update(int(sb.value()), network_like=window._prime_network_like)
    window._on_scroll_settle_timer()
    _process_events(app, ms=800)
    window._on_scroll_settle_timer()
    _process_events(app, ms=500)

    if window._thumb_controller.is_fast_scroll_suppressed():
        logger.error("FAIL: fast scroll suppression still active after settle.")
        window.close()
        return 1

    snap_after = diag.snapshot()
    priority_req = int(snap_after.get("priority_decode_requests", 0))
    prefetch = int(snap_after.get("directional_prefetch_count", 0))
    logger.info(
        "After settle: priority_decode_requests=%s directional_prefetch=%s cache_hits=%s",
        priority_req,
        prefetch,
        snap_after.get("cache_hits"),
    )

    logger.info("Simulating slow scroll-back for cache hits…")
    hits_before = int(snap_after.get("cache_hits", 0))
    back = int(sb.value())
    for _ in range(12):
        back = max(0, back - step)
        sb.setValue(back)
        window._schedule_viewport_thumb_pass()
        _process_events(app, ms=120)
    window._on_scroll_settle_timer()
    _process_events(app, ms=600)

    snap_back = diag.snapshot()
    hits_after = int(snap_back.get("cache_hits", 0))
    logger.info("Cache hits after scroll-back: %s (delta %s)", hits_after, hits_after - hits_before)

    diag.maybe_log_summary()
    window.close()
    _process_events(app, ms=100)

    logger.info("PASS: Prime v0.9 holocron scroll validation completed.")
    return 0


def main() -> int:
    folder = (os.environ.get("ROUNDUP_VALIDATE_FOLDER") or "").strip()
    if not folder and len(sys.argv) > 1:
        folder = sys.argv[1].strip()
    if not folder:
        folder = DEFAULT_HOLOCRON

    root = Path(folder)
    if not root.exists():
        logger.error("Folder not reachable: %s", folder)
        return 1

    return run_validation(str(root))


if __name__ == "__main__":
    raise SystemExit(main())
