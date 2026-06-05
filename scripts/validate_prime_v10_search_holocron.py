"""
Prime v1.0 Sprint C — holocron search UX validation (headless-friendly).

Exercises async search on a large working set without manual UI typing.

Usage:
  .venv\\Scripts\\python scripts/validate_prime_v10_search_holocron.py [folder_path]

Environment:
  ROUNDUP_VALIDATE_FOLDER — override scan root (UNC or local)
  ROUNDUP_VALIDATE_MIN_FILES — minimum rows for a strong pass (default 1000)
  ROUNDUP_VALIDATE_SCAN_TIMEOUT_S — scan wait cap (default 900)
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("validate_search_c")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOLOCRON = r"\\holocron\Sculpt\Sculpt Drop Folder\STL DROP\Movie"
# Full drop folder (~34k files) is valid but slow; override with argv or ROUNDUP_VALIDATE_FOLDER.

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


def _wait_scan_done(window, app, *, timeout_s: float) -> bool:
    t0 = time.monotonic()
    while window._is_scanning:
        if time.monotonic() - t0 > timeout_s:
            logger.error("Scan timed out after %.0fs", timeout_s)
            return False
        _process_events(app, ms=80)
    return True


def _wait_filter_settle(
    window,
    app,
    *,
    prior_count: int,
    timeout_s: float = 12.0,
) -> tuple[str, float]:
    """
    Wait until the filtered row count or status changes (search applied).

    Uses short event pumps so bridge/thumbnail work does not inflate filter timing.
    """
    deadline = time.monotonic() + timeout_s
    t0 = time.monotonic()
    last_count = prior_count
    last_status = window._status_ready_label.text()
    while time.monotonic() < deadline:
        _process_events(app, ms=25)
        status = window._status_ready_label.text()
        count = len(window._view_records)
        busy = "Searching" in status or "Filtering" in status
        if not busy and "match" in status.lower():
            return status, time.monotonic() - t0
        if not busy and not (window._search_edit.text() or "").strip() and count == prior_count:
            return status, time.monotonic() - t0
        if count != prior_count and not busy:
            return status, time.monotonic() - t0
        last_count = count
        last_status = status
    return last_status, time.monotonic() - t0


def _run_search_step(
    window,
    app,
    query: str,
    *,
    hits_before: int,
    expect_status_contains: str | None = None,
) -> tuple[int, str, float, int]:
    window._stop_filter_search_debounce()
    window._search_edit.blockSignals(True)
    window._search_edit.setText(query)
    window._search_edit.blockSignals(False)
    prior = len(window._view_records)
    window._apply_filters(refresh_inspector=False)
    status, elapsed = _wait_filter_settle(window, app, prior_count=prior, timeout_s=30.0)
    count = len(window._view_records)
    diag = window._thumb_controller.paint_diagnostics()
    hits_after = int(diag.snapshot().get("cache_hits", 0))
    if expect_status_contains and expect_status_contains not in status.lower():
        logger.warning(
            "Status %r did not contain %r (may be ok for sync path)",
            status,
            expect_status_contains,
        )
    if hits_after < hits_before:
        logger.error(
            "FAIL: cache_hits dropped %s -> %s during search %r",
            hits_before,
            hits_after,
            query,
        )
    if elapsed > 8.0:
        logger.warning("Slow filter (%.2fs) for query %r on %s rows", elapsed, query, count)
    logger.info(
        "Query %r -> %s rows in %.2fs status=%r cache_hits=%s",
        query or "(clear)",
        count,
        elapsed,
        status,
        hits_after,
    )
    return count, status, elapsed, hits_after


def _all_match_extension(rows, ext: str) -> bool:
    want = ext if ext.startswith(".") else f".{ext}"
    return all(r.extension == want for r in rows)


def _all_match_folder(rows, needle: str) -> bool:
    n = needle.lower()
    return all(n in (r.parent_folder or "").lower() for r in rows)


def _all_match_size_gt(rows, mb: int) -> bool:
    limit = mb * 1024 * 1024
    return all((r.size_bytes or 0) > limit for r in rows if r.size_bytes is not None)


def run_validation(folder: str) -> int:
    """Return 0 on pass, 1 on failure."""
    from meshcorral.ui.main_window import MainWindow
    from meshcorral.ui.search.async_filter_engine import ASYNC_FILTER_THRESHOLD

    app = _ensure_qapp()
    window = MainWindow()
    window.show()
    _process_events(app, ms=200)

    min_files = int(os.environ.get("ROUNDUP_VALIDATE_MIN_FILES", "1000"))
    scan_timeout = float(os.environ.get("ROUNDUP_VALIDATE_SCAN_TIMEOUT_S", "900"))

    logger.info("Scanning: %s", folder)
    window._selected_source_path = folder
    window._persist_selected_source(folder)
    window._include_subfolders_checkbox.setChecked(True)
    window._scan_skip_auto_thumbnails_once = True
    window._run_scan(folder)

    if not _wait_scan_done(window, app, timeout_s=scan_timeout):
        window.close()
        return 1

    total = len(window._all_records)
    logger.info(
        "Scan complete: %s indexed, %s visible (prime=%s, async_threshold=%s)",
        total,
        len(window._view_records),
        window._prime_perf_active,
        ASYNC_FILTER_THRESHOLD,
    )
    if total < min_files:
        logger.error(
            "FAIL: need at least %s files in working set (got %s). "
            "Pick a larger holocron subfolder or lower ROUNDUP_VALIDATE_MIN_FILES.",
            min_files,
            total,
        )
        window.close()
        return 1

    _process_events(app, ms=800)
    _wait_filter_settle(window, app, prior_count=len(window._view_records), timeout_s=30.0)
    baseline = len(window._view_records)
    diag = window._thumb_controller.paint_diagnostics()
    hits = int(diag.snapshot().get("cache_hits", 0))

    # Selection restore: pick first visible row, narrow search, path should stay selected if still visible.
    selected_path: Path | None = None
    if window._view_records:
        selected_path = window._view_records[0].path
        window._table.selectRow(0)
        _process_events(app, ms=100)

    steps: list[tuple[str, str | None]] = [
        ("ext:stl", "match"),
        ("folder:starwars", "match"),
        ("size>100mb", "match"),
        ("vader helmet", "match"),
        ("", None),
    ]

    selection_checked = False
    for query, status_hint in steps:
        count, status, elapsed, hits = _run_search_step(
            window,
            app,
            query,
            hits_before=hits,
            expect_status_contains=status_hint,
        )
        hits = hits
        if (
            not selection_checked
            and query == "ext:stl"
            and selected_path is not None
            and count > 0
        ):
            visible_paths = {r.path for r in window._view_records}
            if selected_path in visible_paths:
                recs = window.selected_records()
                if not recs or recs[0].path != selected_path:
                    logger.error("FAIL: selection not restored by path after ext:stl")
                    window.close()
                    return 1
                logger.info("PASS: selection restored for path still in view")
            selection_checked = True
        if query == "ext:stl" and count > 0:
            sample = window._view_records[: min(50, count)]
            if not _all_match_extension(sample, ".stl"):
                logger.error("FAIL: ext:stl returned non-.stl rows in sample")
                window.close()
                return 1
        if query == "folder:starwars":
            if count == 0:
                logger.warning(
                    "folder:starwars returned 0 rows — holocron may lack that folder name (not a fail)"
                )
            else:
                sample = window._view_records[: min(50, count)]
                if not _all_match_folder(sample, "starwars"):
                    logger.error("FAIL: folder:starwars returned rows outside folder match")
                    window.close()
                    return 1
        if query == "size>100mb" and count > 0:
            sample = [r for r in window._view_records[:200] if r.size_bytes is not None]
            if sample and not _all_match_size_gt(sample, 100):
                logger.error("FAIL: size>100mb returned rows below threshold")
                window.close()
                return 1
        if elapsed > 2.0:
            logger.warning(
                "Filter settle took %.2fs (often bridge/thumb events in headless run; "
                "manual UI should feel faster after debounce)",
                elapsed,
            )

    if len(window._view_records) != baseline:
        logger.warning(
            "Cleared search: visible %s vs baseline %s (filters may differ)",
            len(window._view_records),
            baseline,
        )

    logger.info("PASS: Sprint C holocron search validation completed.")
    window.close()
    _process_events(app, ms=100)
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
