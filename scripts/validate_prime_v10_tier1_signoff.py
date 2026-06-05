"""
Prime v1.0 Tier 1 sign-off validation (Holocron / remote stress test).

Primary release gate while working remotely: scripts/validate_prime_v10_local_stability_signoff.py

Usage:
  .venv\\Scripts\\python.exe scripts/validate_prime_v10_tier1_signoff.py [folder]

Environment:
  ROUNDUP_VALIDATE_FOLDER — scan root (default: holocron Movie subfolder ~1k files)
"""

from __future__ import annotations

import csv
import logging
import sys
import tempfile
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("tier1_signoff")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FOLDER = r"\\holocron\Sculpt\Sculpt Drop Folder\STL DROP\Movie"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _ensure_qapp():
    from PySide6.QtWidgets import QApplication

    inst = QApplication.instance()
    if inst is None:
        return QApplication(sys.argv)
    return inst


def _pump(app, ms: int = 60) -> None:
    deadline = time.monotonic() + ms / 1000.0
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def _wait_filter(window, app, *, timeout_s: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        _pump(app, 40)
        text = window._status_ready_label.text()
        if "Searching" not in text and "Filtering" not in text:
            if "match" in text.lower() or "Filtered" in text:
                return


def run(folder: str) -> int:
    from PySide6.QtCore import QSettings

    from meshcorral.models.file_record import FileRecord
    from meshcorral.services.export_service import export_records_to_csv
    from meshcorral.services.metadata.geometry_metadata import is_mesh_geometry_extension
    from meshcorral.ui.file_columns import export_headers
    from meshcorral.ui.layouts.layout_manager import LayoutManager
    from meshcorral.ui.main_window import MainWindow

    root = Path(folder)
    if not root.exists():
        logger.error("FAIL: folder not reachable: %s", folder)
        return 1

    app = _ensure_qapp()
    fails: list[str] = []

    # --- 1. Scan Holocron folder ---
    logger.info("1. Scan Holocron folder: %s", folder)
    window = MainWindow()
    window.show()
    _pump(app, 300)
    # Neutralize persisted session/filters so scan results are visible.
    window._search_edit.clear()
    window.extension_combo.setCurrentText("All")
    window.folder_combo.setCurrentText("All Folders")
    window.category_combo.setCurrentText("All")
    window._thumb_filter_combo.setCurrentText("All")
    window._apply_filters(refresh_inspector=False)
    _wait_filter(window, app, timeout_s=10.0)
    window._scan_skip_auto_thumbnails_once = True
    window._selected_source_path = str(root)
    window._run_scan(str(root))
    deadline = time.monotonic() + 600.0
    while window._is_scanning and time.monotonic() < deadline:
        _pump(app, 80)
    if window._is_scanning:
        fails.append("scan timed out (600s)")
    else:
        n = len(window._all_records)
        v = len(window._view_records)
        logger.info("   Scan complete: %s indexed, %s visible", n, v)
        if n < 500:
            fails.append(f"scan yielded only {n} rows (expected 500+ for sign-off)")
        if v < 1:
            window._apply_filters(refresh_inspector=False)
            _wait_filter(window, app, timeout_s=15.0)
            v = len(window._view_records)
            if v < 1:
                fails.append(f"no visible rows after scan (filters={window._search_edit.text()!r})")

    # --- 2. Search tokens ---
    logger.info("2. Search ext:stl / faces>10000 / watertight:true")
    total = len(window._all_records)
    for query, min_expected, max_expected in (
        ("ext:stl", 1, total),
        ("faces>10000", 0, total),
        ("watertight:true", 0, max(0, total // 2)),
    ):
        window._stop_filter_search_debounce()
        window._search_edit.setText(query)
        window._apply_filters(refresh_inspector=False)
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            _pump(app, 40)
            text = window._status_ready_label.text()
            count = len(window._view_records)
            if "Searching" not in text and "Filtering" not in text:
                if "match" in text.lower() or (not query.strip() and "Filtered" in text):
                    break
        count = len(window._view_records)
        logger.info("   %r -> %s rows (status=%r)", query, count, window._status_ready_label.text())
        if query == "ext:stl" and count < min_expected:
            fails.append(f"ext:stl returned {count} rows (expected mesh subset)")
        if query == "watertight:true" and count > max_expected and count == total:
            fails.append(
                f"watertight:true returned all {count} rows (metadata predicate should narrow)"
            )
        if query.startswith("faces") and count > 0:
            sample = window._view_records[: min(20, count)]
            missing_meta = 0
            for rec in sample:
                s = window._metadata_registry.get(rec.path)
                if s is None or s.face_count is None:
                    missing_meta += 1
            if missing_meta == len(sample):
                logger.warning(
                    "   faces> query: no face_count in registry yet (inspect meshes first)"
                )

    # --- 3. STL metadata ---
    logger.info("3. Select STL and confirm metadata")
    stl_rows = [r for r in window._view_records if r.extension == ".stl"]
    if not stl_rows:
        fails.append("no STL rows to test metadata")
    else:
        window._model.set_rows(window._view_records)
        window._update_asset_inspector()
        for rec in stl_rows[:5]:
            if window._table.selectionModel():
                for row, r in enumerate(window._view_records):
                    if r.path == rec.path:
                        window._table.selectRow(row)
                        window._update_asset_inspector()
                        break
            _pump(app, 500)
            _pump(app, 300)
            summary = window._metadata_registry.get(rec.path)
            if summary is None:
                window._metadata_summary_for_record(rec)
                summary = window._metadata_registry.get(rec.path)
            if summary is None:
                fails.append("metadata summary missing after select")
                break
            logger.info(
                "   %s faces=%s dims=%s source=%s",
                rec.name,
                summary.face_count,
                summary.dimensions_mm,
                summary.metadata_source,
            )
            if is_mesh_geometry_extension(rec.extension):
                deadline = time.monotonic() + 12.0
                while time.monotonic() < deadline:
                    _pump(app, 100)
                    summary = window._metadata_registry.get(rec.path)
                    if summary and summary.face_count is not None:
                        break
                if summary and summary.face_count is None and summary.metadata_source != "deferred":
                    logger.warning("   geometry still pending for %s (trimesh/defer?)", rec.name)
            break

    # --- 4. Export CSV 15 columns ---
    logger.info("4. Export CSV columns")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "signoff.csv"
        export_records_to_csv(
            window._view_records[:50],
            out,
            metadata_registry=window._metadata_registry,
        )
        with out.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        headers = export_headers()
        if len(rows[0]) != 15:
            fails.append(f"export has {len(rows[0])} columns, expected 15")
        else:
            logger.info("   Export headers: %s columns OK", len(rows[0]))
        base = ["Name", "Ext", "Type", "Folder", "Path", "Size", "Modified"]
        if rows[0][:7] != base:
            fails.append("export base columns changed")

    # --- 5. Layout preset ---
    logger.info("5. Switch layout preset Review")
    before = window._view_stack.currentIndex()
    if not window._layout_manager.apply_builtin_preset(window, "Review"):
        fails.append("Review preset failed")
    else:
        after = window._view_stack.currentIndex()
        logger.info("   view index %s -> %s (gallery=1)", before, after)
        if after != 1:
            fails.append("Review preset did not switch to gallery")

    # --- 6. Quit/relaunch layout restore ---
    logger.info("6. Session layout save/restore")
    window._main_splitter.setSizes([400, 700, 420])
    window._persist_workspace_layout()
    sizes_saved = list(window._main_splitter.sizes())
    window.close()
    _pump(app, 200)

    window2 = MainWindow()
    window2.show()
    _pump(app, 300)
    restored = window2._layout_manager.restore_session_to_window(window2)
    sizes2 = list(window2._main_splitter.sizes())
    logger.info("   splitter before close %s after reopen %s", sizes_saved, sizes2)
    if restored and sizes_saved[0] > 300 and sizes2[0] < 280:
        fails.append("splitter sizes not restored after relaunch")
    window2.close()
    _pump(app, 200)

    # --- 7. Clean shutdown (idle + light activity) ---
    logger.info("7. Close during idle and after filter activity")
    window3 = MainWindow()
    window3.show()
    _pump(app, 200)
    window3._all_records = stl_rows[:200] if stl_rows else []
    window3._view_records = list(window3._all_records)
    window3._model.set_rows(window3._view_records)
    window3._search_edit.setText("ext:stl")
    window3._apply_filters(refresh_inspector=False)
    _wait_filter(window3, app, timeout_s=20.0)
    window3._shutdown_app(reason="signoff_idle")
    logger.info("   shutdown after filter: OK")
    window3.close()
    _pump(app, 200)

    if fails:
        for item in fails:
            logger.error("FAIL: %s", item)
        return 1

    logger.info("PASS: Prime v1.0 Tier 1 sign-off (7 checks)")
    return 0


def main() -> int:
    import os

    folder = (os.environ.get("ROUNDUP_VALIDATE_FOLDER") or "").strip()
    if not folder and len(sys.argv) > 1:
        folder = sys.argv[1].strip()
    if not folder:
        folder = DEFAULT_FOLDER
    return run(folder)


if __name__ == "__main__":
    raise SystemExit(main())
