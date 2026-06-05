"""
Prime v1.0 — Local Stability Sign-off (release gate while testing remotely).

Uses local paths only (e.g. C:\\MeshStager_Test_Data, E:\\MeshStager_Test, temp SSD trees).
Holocron/VPN folders are optional
stress tests, not the primary pass/fail signal.

Usage:
  .venv\\Scripts\\python.exe scripts/validate_prime_v10_local_stability_signoff.py

Optional real folders (skip auto-seed for that slot):
  ROUNDUP_LOCAL_SMALL      — 50–200 mixed files
  ROUNDUP_LOCAL_MEDIUM     — 1,000+ mixed files
  ROUNDUP_LOCAL_MESH       — STL/OBJ/FBX sample
  ROUNDUP_LOCAL_IMAGES     — JPG/PNG/PSD/TIF sample
  ROUNDUP_LOCAL_ARCHIVES   — ZIP-heavy sample

Manual UI pass: see QUICK_QA_CHECKLIST.md → Local Stability Sign-off.
"""

from __future__ import annotations

import csv
import logging
import os
import sys
import tempfile
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("local_stability_signoff")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_MINI_STL = (
    b"solid signoff\n"
    b"  facet normal 0 0 1\n    outer loop\n"
    b"      vertex 0 0 0\n      vertex 1 0 0\n      vertex 0 1 0\n"
    b"    endloop\n  endfacet\nendsolid signoff\n"
)


@dataclass(frozen=True)
class LocalFolders:
    """Paths for the five local sign-off folder profiles."""

    small: Path
    medium: Path
    mesh: Path
    images: Path
    archives: Path
    seeded: bool


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


def _wait_filter(window, app, *, timeout_s: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        _pump(app, 40)
        text = window._status_ready_label.text()
        if "Searching" not in text and "Filtering" not in text:
            if "match" in text.lower() or "Filtered" in text:
                return


def _wait_scan(window, app, *, timeout_s: float = 120.0) -> bool:
    deadline = time.monotonic() + timeout_s
    while window._is_scanning and time.monotonic() < deadline:
        _pump(app, 80)
    return not window._is_scanning


def _neutralize_filters(window) -> None:
    window._stop_filter_search_debounce()
    window._search_edit.clear()
    window.extension_combo.setCurrentText("All")
    window.folder_combo.setCurrentText("All Folders")
    window.category_combo.setCurrentText("All")
    window._thumb_filter_combo.setCurrentText("All")


def _touch(path: Path, *, nbytes: int = 0, payload: bytes = b"") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if nbytes > 0:
        with path.open("wb") as handle:
            if nbytes > 1:
                handle.seek(nbytes - 1)
            handle.write(payload or b"\0")
    else:
        path.write_bytes(payload)


def _seed_local_tree(root: Path) -> LocalFolders:
    """Build five local folder profiles under *root* (fast SSD/temp)."""
    small = root / "small_mixed"
    medium = root / "medium_mixed"
    mesh = root / "mesh_3d"
    images = root / "images_raster"
    archives = root / "archives_zip"

    exts_3d = [".stl", ".obj", ".fbx", ".ply", ".blend", ".mtl"]
    for i in range(150):
        ext = exts_3d[i % len(exts_3d)]
        _touch(small / f"batch_{i // 20}" / f"asset_{i:03d}{ext}")

    for i in range(1200):
        ext = exts_3d[i % len(exts_3d)]
        _touch(medium / f"shard_{i // 100}" / f"file_{i:04d}{ext}")
    # ~12 MB — fast local seed; manual sign-off may use size>100mb on a real library.
    _touch(medium / "heavy" / "big_mesh.stl", nbytes=12 * 1024 * 1024)

    _touch(mesh / "hero.stl", payload=_MINI_STL)
    _touch(mesh / "alt.obj", payload=b"# stub obj\n")
    _touch(mesh / "prop.fbx", payload=b"Kaydara FBX Binary")

    for name in ("cover.jpg", "thumb.png", "layer.psd", "scan.tif"):
        _touch(images / name, payload=b"\xff\xd8\xff" if name.endswith(".jpg") else b"stub")

    for i in range(12):
        inner = archives / f"pack_{i}"
        _touch(inner / "readme.txt", payload=f"pack {i}\n".encode())
        zpath = archives / f"bundle_{i:02d}.zip"
        zpath.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"inner_{i}.txt", f"zip member {i}")

    return LocalFolders(
        small=small,
        medium=medium,
        mesh=mesh,
        images=images,
        archives=archives,
        seeded=True,
    )


def _resolve_folders() -> tuple[LocalFolders, tempfile.TemporaryDirectory[str] | None]:
    env_keys = (
        ("ROUNDUP_LOCAL_SMALL", "small"),
        ("ROUNDUP_LOCAL_MEDIUM", "medium"),
        ("ROUNDUP_LOCAL_MESH", "mesh"),
        ("ROUNDUP_LOCAL_IMAGES", "images"),
        ("ROUNDUP_LOCAL_ARCHIVES", "archives"),
    )
    overrides: dict[str, Path] = {}
    for key, attr in env_keys:
        raw = (os.environ.get(key) or "").strip()
        if raw:
            overrides[attr] = Path(raw)

    if len(overrides) == 5:
        return (
            LocalFolders(
                small=overrides["small"],
                medium=overrides["medium"],
                mesh=overrides["mesh"],
                images=overrides["images"],
                archives=overrides["archives"],
                seeded=False,
            ),
            None,
        )

    base = Path(tempfile.mkdtemp(prefix="roundup_local_signoff_"))
    folders = _seed_local_tree(base)
    return folders, None


def _scan_folder(window, app, folder: Path, *, skip_thumbs: bool = True) -> tuple[int, int]:
    _neutralize_filters(window)
    window._apply_filters(refresh_inspector=False)
    _wait_filter(window, app, timeout_s=10.0)
    if skip_thumbs:
        window._scan_skip_auto_thumbnails_once = True
    window._selected_source_path = str(folder)
    window._run_scan(str(folder))
    if not _wait_scan(window, app, timeout_s=120.0):
        return -1, -1
    return len(window._all_records), len(window._view_records)


def _set_asset_mode(window, mode: str) -> None:
    from meshcorral.app.config import ASSET_MODE_3D, ASSET_MODE_IMAGES

    want = ASSET_MODE_IMAGES if mode == "images" else ASSET_MODE_3D
    for i in range(window._search_mode_combo.count()):
        if window._search_mode_combo.itemData(i) == want:
            window._search_mode_combo.setCurrentIndex(i)
            break


def _run_search(window, app, query: str) -> int:
    window._stop_filter_search_debounce()
    window._search_edit.setText(query)
    window._apply_filters(refresh_inspector=False)
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline:
        _pump(app, 40)
        text = window._status_ready_label.text()
        if "Searching" not in text and "Filtering" not in text:
            if "match" in text.lower() or (not query.strip() and "Filtered" in text):
                break
    return len(window._view_records)


def run() -> int:
    from meshcorral.services.export_service import export_records_to_csv
    from meshcorral.services.metadata.geometry_metadata import is_mesh_geometry_extension
    from meshcorral.ui.file_columns import export_headers
    from meshcorral.ui.main_window import MainWindow

    folders, temp_holder = _resolve_folders()
    fails: list[str] = []

    for label, path in (
        ("small", folders.small),
        ("medium", folders.medium),
        ("mesh", folders.mesh),
        ("images", folders.images),
        ("archives", folders.archives),
    ):
        if not path.exists():
            fails.append(f"{label} folder missing: {path}")
    if fails:
        for item in fails:
            logger.error("FAIL: %s", item)
        return 1

    bridge_root = Path(tempfile.gettempdir()) / "roundup_local_signoff_bridge"
    os.environ.setdefault("ROUNDUP_BRIDGE_ROOT", str(bridge_root))

    app = _ensure_qapp()
    logger.info("Local Stability Sign-off (seeded=%s)", folders.seeded)
    logger.info("  small=%s", folders.small)
    logger.info("  medium=%s", folders.medium)
    logger.info("  mesh=%s", folders.mesh)

    # --- Launch ---
    logger.info("1. Launch cleanly")
    window = MainWindow()
    window.show()
    _pump(app, 300)
    window._settings_service.set_auto_thumbnail_after_scan(False)
    _neutralize_filters(window)
    window._apply_filters(refresh_inspector=False)
    _wait_filter(window, app, timeout_s=10.0)

    # --- Scan small ---
    logger.info("2. Scan local small folder")
    n_small, v_small = _scan_folder(window, app, folders.small)
    logger.info("   indexed=%s visible=%s", n_small, v_small)
    if n_small < 50 or v_small < 1:
        fails.append(f"small scan weak: indexed={n_small} visible={v_small}")

    # --- Scan medium ---
    logger.info("3. Scan local medium folder (1k+)")
    n_med, v_med = _scan_folder(window, app, folders.medium)
    logger.info("   indexed=%s visible=%s", n_med, v_med)
    if n_med < 1000 or v_med < 1:
        fails.append(f"medium scan weak: indexed={n_med} visible={v_med}")

    # --- Asset mode switch + rescan ---
    logger.info("4. Switch Asset Mode and rescan same source")
    source = window._selected_source_path
    _set_asset_mode(window, "images")
    if window._all_records:
        fails.append("asset mode switch should clear rows before rescan")
    n_img, _ = _scan_folder(window, app, folders.images)
    logger.info("   images scan indexed=%s", n_img)
    if n_img < 2:
        fails.append(f"images mode scan weak: {n_img}")
    _set_asset_mode(window, "3d")
    window._selected_source_path = source or str(folders.medium)
    n_re, v_re = _scan_folder(window, app, folders.medium)
    if n_re < 1000:
        fails.append(f"3D rescan after mode switch weak: {n_re}")

    # --- Metadata on mesh STL ---
    logger.info("5. Select mesh + background metadata")
    n_mesh, v_mesh = _scan_folder(window, app, folders.mesh)
    stl_rows = [r for r in window._view_records if r.extension == ".stl"]
    if not stl_rows:
        fails.append("no STL in mesh folder")
    else:
        rec = stl_rows[0]
        for row, r in enumerate(window._view_records):
            if r.path == rec.path:
                window._table.selectRow(row)
                window._update_asset_inspector()
                break
        _pump(app, 800)
        summary = window._metadata_registry.get(rec.path)
        if summary is None:
            window._metadata_summary_for_record(rec)
            summary = window._metadata_registry.get(rec.path)
        if summary is None:
            fails.append("metadata summary missing after select")
        else:
            deadline = time.monotonic() + 15.0
            while time.monotonic() < deadline:
                _pump(app, 100)
                summary = window._metadata_registry.get(rec.path)
                if summary and summary.face_count is not None:
                    break
            logger.info(
                "   %s faces=%s source=%s",
                rec.name,
                summary.face_count if summary else None,
                summary.metadata_source if summary else None,
            )

    # --- Search (after metadata warm) ---
    logger.info("6. Search ext:stl / size>100mb / faces>10000")
    window._selected_source_path = str(folders.medium)
    _scan_folder(window, app, folders.medium)
    total = len(window._all_records)
    ext_n = _run_search(window, app, "ext:stl")
    logger.info("   ext:stl -> %s (total=%s)", ext_n, total)
    if ext_n < 1 or ext_n > total:
        fails.append(f"ext:stl unexpected count {ext_n}/{total}")
    size_n = _run_search(window, app, "size>10mb")
    logger.info("   size>10mb -> %s (auto-seed; manual QA may use size>100mb)", size_n)
    if size_n < 1 and folders.seeded:
        fails.append("size>10mb found 0 rows (expected seeded big_mesh.stl)")
    faces_n = _run_search(window, app, "faces>10000")
    logger.info("   faces>10000 -> %s (metadata may be sparse until inspect)", faces_n)

    # --- Export ---
    logger.info("7. Export CSV (15 columns)")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "local_signoff.csv"
        export_records_to_csv(
            window._view_records[:30],
            out,
            metadata_registry=window._metadata_registry,
        )
        with out.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        if len(rows[0]) != 15:
            fails.append(f"export columns {len(rows[0])}, expected 15")
        else:
            logger.info("   export OK: %s", export_headers())

    # --- Layout preset + session ---
    logger.info("8. Layout preset + quit/relaunch restore")
    if not window._layout_manager.apply_builtin_preset(window, "Review"):
        fails.append("Review preset failed")
    window._main_splitter.setSizes([360, 820, 400])
    window._persist_workspace_layout()
    sizes_saved = list(window._main_splitter.sizes())
    window.close()
    _pump(app, 200)

    window2 = MainWindow()
    window2.show()
    _pump(app, 300)
    window2._layout_manager.restore_session_to_window(window2)
    sizes2 = list(window2._main_splitter.sizes())
    logger.info("   splitter saved=%s restored=%s", sizes_saved, sizes2)
    if sizes_saved[0] > 300 and sizes2[0] < 280:
        fails.append("splitter sizes not restored")
    window2.close()
    _pump(app, 200)

    # --- Shutdown idle + active-ish ---
    logger.info("9. Close idle + after filter activity")
    window3 = MainWindow()
    window3.show()
    _pump(app, 200)
    window3._all_records = stl_rows[: min(200, len(stl_rows))] if stl_rows else []
    window3._view_records = list(window3._all_records)
    window3._model.set_rows(window3._view_records)
    window3._search_edit.setText("ext:stl")
    window3._apply_filters(refresh_inspector=False)
    _wait_filter(window3, app)
    window3._shutdown_app(reason="local_signoff")
    window3.close()
    _pump(app, 200)
    logger.info("   shutdown OK")

    if temp_holder is not None:
        try:
            temp_holder.cleanup()
        except OSError:
            pass

    if fails:
        for item in fails:
            logger.error("FAIL: %s", item)
        return 1

    logger.info("PASS: Local Stability Sign-off (automated local gate)")
    logger.info("Complete manual steps in QUICK_QA_CHECKLIST.md (thumbnails, N/R, archives).")
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
