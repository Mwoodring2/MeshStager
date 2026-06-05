"""
Prime v1.0 RC — programmatic DPI layout probe (100% / 125% / 150%).

Run: python scripts/dpi_validation_probe.py [scale]
Scale via QT_SCALE_FACTOR (default 1.0). Parent process may invoke once per scale.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Repo root on path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _scale() -> float:
    raw = os.environ.get("QT_SCALE_FACTOR", "1.0").strip()
    try:
        return float(raw)
    except ValueError:
        return 1.0


def _ensure_qapp():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    inst = QApplication.instance()
    if inst is None:
        return QApplication([])
    return inst


def _check(ok: bool, name: str, detail: str = "") -> dict[str, object]:
    return {"name": name, "pass": ok, "detail": detail}


def probe() -> dict[str, object]:
    from PySide6.QtCore import QSettings, Qt
    from PySide6.QtWidgets import QLabel, QStatusBar, QWidget

    from meshcorral.services.large_folder_scan_assessment import (
        FolderScopeEstimate,
        LargeFolderAssessment,
    )
    from meshcorral.services.settings_service import SettingsService
    from meshcorral.ui.footer_status import (
        format_bridge_footer,
        format_counts_strip,
        format_scan_footer,
        format_thumbnail_footer,
        FooterCounts,
    )
    from meshcorral.ui.inspector.diagnostics_panel import DiagnosticsPanel
    from meshcorral.ui.inspector.inspector_tabs import InspectorTabbedPanel
    from meshcorral.ui.large_folder_warning_dialog import LargeFolderWarningDialog
    from meshcorral.ui.layout_constants import (
        LARGE_FOLDER_DIALOG_MIN_WIDTH,
        MIN_RIGHT_PANEL_WIDTH,
        SETTINGS_DIALOG_MIN_HEIGHT,
        SETTINGS_DIALOG_MIN_WIDTH,
    )
    from meshcorral.ui.settings_dialog import SettingsDialog
    from meshcorral.ui.theme import build_app_stylesheet

    scale = _scale()
    app = _ensure_qapp()
    app.setStyleSheet(build_app_stylesheet(theme_mode="dark"))

    checks: list[dict[str, object]] = []

    # --- Settings dialog ---
    ini = str(_ROOT / ".dpi_probe_settings.ini")
    qs = QSettings(ini, QSettings.Format.IniFormat)
    qs.clear()
    dlg = SettingsDialog(SettingsService(qs), None)
    dlg.show()
    app.processEvents()
    min_w, min_h = dlg.minimumWidth(), dlg.minimumHeight()
    hint = dlg.sizeHint()
    checks.append(
        _check(
            min_w >= SETTINGS_DIALOG_MIN_WIDTH and min_h >= SETTINGS_DIALOG_MIN_HEIGHT,
            "settings_min_size",
            f"min={min_w}x{min_h} hint={hint.width()}x{hint.height()}",
        )
    )
    from PySide6.QtWidgets import QSizePolicy

    vert_policy = dlg.sizePolicy().verticalPolicy()
    resizable = vert_policy in (
        QSizePolicy.Policy.Preferred,
        QSizePolicy.Policy.Minimum,
        QSizePolicy.Policy.Expanding,
        QSizePolicy.Policy.Ignored,
    )
    checks.append(
        _check(
            resizable and hint.height() > min_h,
            "settings_vertically_resizable",
            f"hint_h={hint.height()} min_h={min_h} policy={vert_policy}",
        )
    )
    dlg.close()

    # --- Large-folder warning ---
    assessment = LargeFolderAssessment(
        source_path="\\\\server\\share\\assets",
        network_like=True,
        estimate=FolderScopeEstimate(
            matching_file_count=50_000,
            exceeds_file_threshold=True,
            archive_zip_count=12,
            max_directory_depth=8,
            preflight_truncated=True,
        ),
        prior_slow_folder=False,
        auto_thumbnails_enabled=True,
        prior_cached_count=0,
        would_use_lightweight=True,
        file_count_threshold=5000,
        thumbnail_mode_label="Auto recommended",
        cache_mode_label="Standard",
    )
    warn = LargeFolderWarningDialog(assessment, parent=None)
    warn.show()
    app.processEvents()
    btn_w = (
        warn._continue_btn.sizeHint().width()
        + warn._no_thumbs_btn.sizeHint().width()
        + warn._cancel_btn.sizeHint().width()
        + 48
    )
    checks.append(
        _check(
            warn.width() >= LARGE_FOLDER_DIALOG_MIN_WIDTH and btn_w <= warn.width(),
            "large_folder_buttons_fit",
            f"dialog_w={warn.width()} buttons~={btn_w} min={LARGE_FOLDER_DIALOG_MIN_WIDTH}",
        )
    )
    wrapped_labels = [
        w
        for w in warn.findChildren(QLabel)
        if w.wordWrap() and w.text().strip()
    ]
    checks.append(
        _check(
            len(wrapped_labels) >= 2,
            "large_folder_word_wrap_labels",
            f"wrapped_label_count={len(wrapped_labels)}",
        )
    )
    warn.close()

    # --- Inspector tabs @ narrow right panel ---
    from PySide6.QtWidgets import QVBoxLayout

    host = QWidget()
    host.setFixedWidth(MIN_RIGHT_PANEL_WIDTH)
    host_layout = QVBoxLayout(host)
    host_layout.setContentsMargins(0, 0, 0, 0)
    insp = InspectorTabbedPanel(host)
    host_layout.addWidget(insp)
    host.show()
    app.processEvents()
    tab_bar = insp._tabs.tabBar()
    tab_total = sum(tab_bar.tabRect(i).width() for i in range(tab_bar.count()))
    scroll_ok = insp._tabs.usesScrollButtons()
    checks.append(
        _check(
            scroll_ok or tab_total <= MIN_RIGHT_PANEL_WIDTH + 8,
            "inspector_tab_overflow",
            f"tab_total_w={tab_total} panel={MIN_RIGHT_PANEL_WIDTH} scroll_btns={scroll_ok}",
        )
    )
    checks.append(
        _check(tab_bar.minimumHeight() >= 24, "inspector_tab_min_height", str(tab_bar.minimumHeight()))
    )

    # --- Diagnostics + Metadata tabs (scroll + wrap) ---
    diag = DiagnosticsPanel()
    long_reason = "Deferred: " + ("x" * 120)
    diag.apply(
        thumb_status="Deferred",
        renderer_profile="Standard",
        mesh_health="Watertight · 125,000 faces",
        archive_member_count="—",
        unsupported_reason="",
        cache_status="READY",
        deferred_reason=long_reason,
        thumbnail_state_display="Deferred",
    )
    diag.show()
    app.processEvents()
    deferred_h = diag._deferred_reason.heightForWidth(diag._deferred_reason.width() or 200)
    checks.append(
        _check(
            deferred_h > 20 or diag._deferred_reason.wordWrap(),
            "diagnostics_deferred_wraps",
            f"deferred_h={deferred_h} wrap={diag._deferred_reason.wordWrap()}",
        )
    )
    diag.close()

    # --- Footer / status bar ---
    status_host = QWidget()
    status_host.resize(1280, 40)
    bar = QStatusBar(status_host)
    ready = QLabel(format_scan_footer(files_found=125_000, esc_hint=True))
    ready.setObjectName("BrandSubtitle")
    counts = QLabel(
        format_counts_strip(
            FooterCounts(125_000, 98_500, 12),
            prime_mode="Prime Server",
            prime_hint="Visible thumbnails load first",
            failed_thumbnails=3,
        )
    )
    counts.setObjectName("BrandSubtitle")
    thumbs = QLabel(format_thumbnail_footer(generating=4, queued=12))
    thumbs.setObjectName("BrandSubtitle")
    bridge = QLabel(format_bridge_footer(readiness="Ready · C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"))
    bridge.setObjectName("BrandSubtitle")
    version = QLabel("MeshStager v1.0.0-rc")
    version.setObjectName("BrandSubtitle")
    bar.addWidget(ready)
    bar.addWidget(counts, 1)
    bar.addPermanentWidget(thumbs)
    bar.addPermanentWidget(bridge)
    bar.addPermanentWidget(version)
    status_host.show()
    app.processEvents()
    total_perm = thumbs.sizeHint().width() + bridge.sizeHint().width() + version.sizeHint().width()
    checks.append(
        _check(
            total_perm < 1100,
            "footer_permanent_widgets_width",
            f"perm_total_hint={total_perm} (host=1280)",
        )
    )
    checks.append(
        _check(ready.sizeHint().width() < 900, "footer_scan_line_width", str(ready.sizeHint().width()))
    )
    status_host.close()
    host.close()

    passed = sum(1 for c in checks if c["pass"])
    failed = [c for c in checks if not c["pass"]]
    return {
        "scale_factor": scale,
        "device_pixel_ratio": app.devicePixelRatio(),
        "passed": passed,
        "total": len(checks),
        "all_pass": len(failed) == 0,
        "checks": checks,
        "failures": failed,
    }


def main() -> int:
    if len(sys.argv) > 1:
        os.environ["QT_SCALE_FACTOR"] = sys.argv[1]
    result = probe()
    print(json.dumps(result, indent=2))
    return 0 if result["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
