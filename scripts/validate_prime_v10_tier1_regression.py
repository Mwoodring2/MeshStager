"""
Prime v1.0 Tier 1 regression (layout + search + inspector, no scan pipeline changes).

Usage:
  .venv\\Scripts\\python.exe scripts/validate_prime_v10_tier1_regression.py
"""

from __future__ import annotations

import logging
import sys
import tempfile
import time
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("tier1_regression")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _ensure_qapp():
    from PySide6.QtWidgets import QApplication

    inst = QApplication.instance()
    if inst is None:
        return QApplication(sys.argv)
    return inst


def _pump(app, ms: int = 80) -> None:
    deadline = time.monotonic() + ms / 1000.0
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def _wait_search_status(window, app, *, timeout_s: float = 8.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        _pump(app, 40)
        text = window._status_ready_label.text()
        if "Searching" not in text and "Filtering" not in text:
            if "match" in text.lower() or "Filtered" in text:
                return
        if window._search_edit.text().strip() and len(window._view_records) >= 0:
            if "match" in text.lower():
                return


def run() -> int:
    from PySide6.QtCore import QSettings

    from meshcorral.app.config import ASSET_MODE_3D
    from meshcorral.services.settings_service import SettingsService
    from meshcorral.ui.layouts.layout_manager import LayoutManager
    from meshcorral.ui.layouts.workspace_state import WorkspaceState
    from meshcorral.ui.main_window import MainWindow

    app = _ensure_qapp()
    fails: list[str] = []

    # Isolated QSettings for session round-trip.
    with tempfile.TemporaryDirectory() as tmp:
        ini = Path(tmp) / "tier1.ini"
        settings = QSettings(str(ini), QSettings.Format.IniFormat)
        mgr = LayoutManager(settings)

        window = MainWindow()
        window.show()
        _pump(app, 200)

        # Seed synthetic working set (no scan).
        from meshcorral.models.file_record import FileRecord

        rows = [
            FileRecord(
                path=Path(f"C:/demo/starwars/helmet_{i}.stl"),
                name=f"helmet_{i}.stl",
                extension=".stl",
                parent_folder="starwars",
                size_bytes=150_000_000,
                modified_time=0.0,
            )
            for i in range(450)
        ] + [
            FileRecord(
                path=Path("C:/demo/misc/readme.txt"),
                name="readme.txt",
                extension=".txt",
                parent_folder="misc",
                size_bytes=10,
                modified_time=0.0,
            )
        ]
        window._all_records = list(rows)
        window._view_records = list(rows)
        window._model.set_rows(window._view_records)
        window._gallery_model.set_records(window._view_records)
        window._selected_source_path = r"C:\demo"
        window._current_source = r"C:\demo"
        source_before = window._selected_source_path

        # 1–3 Layout capture / session / named / preset
        window._main_splitter.setSizes([360, 800, 380])
        window._set_browse_view_mode(SettingsService.VIEW_MODE_GALLERY)
        window._asset_inspector.set_inspector_tab_index(2)
        captured = mgr.capture_from_window(window)
        if captured.main_splitter_sizes[0] < 300:
            fails.append("splitter capture: left size too small")
        if captured.inspector_tab_index != 2:
            fails.append("inspector tab capture")
        mgr.save_session(captured)
        mgr.save_named("Tier1Test", captured)

        mgr.apply_builtin_preset(window, "Review")
        _pump(app, 100)
        if window._view_stack.currentIndex() != 1:
            fails.append("preset Review: expected gallery")
        if window._asset_inspector.inspector_tab_index() != 0:
            fails.append("preset Review: inspector tab reset to Preview")

        loaded = mgr.load_named("Tier1Test")
        if loaded is None:
            fails.append("named layout load failed")
        else:
            mgr.apply_to_window(window, loaded, apply_search=False)
            _pump(app, 100)
            sizes = window._main_splitter.sizes()
            if sizes[0] < 300:
                fails.append("named layout: splitter not restored")
            if window._asset_inspector.inspector_tab_index() != 2:
                fails.append("named layout: inspector tab not restored")

        window2 = MainWindow()
        window2.show()
        _pump(app, 100)
        if not mgr.restore_session_to_window(window2):
            fails.append("session restore on relaunch")
        else:
            if window2._main_splitter.sizes()[0] < 300:
                fails.append("session restore: splitter")
        window2.close()

        # 4 Search after preset
        mgr.apply_builtin_preset(window, "Scanning")
        window._search_edit.setText("ext:stl")
        window._apply_filters(refresh_inspector=False)
        _wait_search_status(window, app)
        stl_count = len(window._view_records)
        if stl_count != 450:
            fails.append(f"search after preset: expected 450 stl got {stl_count}")
        if not all(r.extension == ".stl" for r in window._view_records[:20]):
            fails.append("search after preset: non-stl in sample")

        # 6 Asset mode does not clear source
        if window._selected_source_path != source_before:
            fails.append("source path lost after layout apply")
        if window._current_source != source_before:
            fails.append("current source lost after layout apply")

        # 5 Inspector tab after explicit restore
        window._asset_inspector.set_inspector_tab_index(3)
        snap = mgr.capture_from_window(window)
        mgr.apply_to_window(window, snap, apply_search=False)
        if window._asset_inspector.inspector_tab_index() != 3:
            fails.append("inspector tab restore via apply")

        window.close()

    # 7 Scan/thumb/cache modules untouched by layouts package (static check logged)
    layout_py = REPO_ROOT / "meshcorral" / "ui" / "layouts"
    forbidden = ("scan_folder", "refresh_index", "ThumbnailViewController")
    for py in layout_py.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                fails.append(f"layouts package references {token} in {py.name}")

    if fails:
        for item in fails:
            logger.error("FAIL: %s", item)
        return 1

    logger.info("PASS: Prime v1.0 Tier 1 regression (7 checks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
