"""Official MeshStager application icon paths (taskbar, title bar, dialogs, PyInstaller)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog, QWidget

logger = logging.getLogger(__name__)

WINDOWS_APP_USER_MODEL_ID = "MeshStager.MeshStager.RC3"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ICON_DIR = _REPO_ROOT / "assets" / "icons"
_BRANDING_DIR = _REPO_ROOT / "assets" / "branding"
ICON_PNG = _ICON_DIR / "MeshStager_icon.png"
ICON_ICO = _ICON_DIR / "MeshStager_icon.ico"
ICON_TOOLBAR_PNG = _ICON_DIR / "MeshStager_icon_toolbar.png"
BRANDING_PRO_JPG = _BRANDING_DIR / "MeshStager_icon_pro.jpg"
# Legacy root copy kept for older docs/scripts that reference meshcorral.ico.
LEGACY_ICO = _REPO_ROOT / "meshcorral.ico"

_APP_ICON_CANDIDATES: tuple[Path, ...] = (
    ICON_ICO,
    ICON_PNG,
    LEGACY_ICO,
    _REPO_ROOT / "Mesh_Corral.png",
    _REPO_ROOT / "Mesh_corral_icon.png",
)


def set_windows_app_user_model_id(
    app_id: str = WINDOWS_APP_USER_MODEL_ID,
) -> bool:
    """
    Pin Windows taskbar grouping to MeshStager (not python/pythonw).

    Must run before ``QApplication`` is constructed. Logs failures; never raises.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        hr = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        if hr != 0:
            logger.warning(
                "SetCurrentProcessExplicitAppUserModelID failed for %s (HRESULT=0x%08X)",
                app_id,
                hr & 0xFFFFFFFF,
            )
            return False
        logger.debug("Windows AppUserModelID set to %s", app_id)
        return True
    except OSError as exc:
        logger.warning("SetCurrentProcessExplicitAppUserModelID unavailable: %s", exc)
        return False
    except Exception as exc:
        logger.warning("SetCurrentProcessExplicitAppUserModelID error: %s", exc)
        return False


def marketing_branding_image_path() -> Path | None:
    """Full wordmark artwork for README, handoff docs, and release (not taskbar)."""
    if BRANDING_PRO_JPG.is_file():
        return BRANDING_PRO_JPG
    return None


def icon_png_path() -> Path | None:
    """Return the official PNG branding asset when present."""
    if ICON_PNG.is_file():
        return ICON_PNG
    for path in (_REPO_ROOT / "Mesh_Corral.png", _REPO_ROOT / "Mesh_corral_icon.png"):
        if path.is_file():
            return path
    return None


def toolbar_icon_png_path() -> Path | None:
    """Return the toolbar/header-optimized PNG (tight crop, transparent background)."""
    if ICON_TOOLBAR_PNG.is_file():
        return ICON_TOOLBAR_PNG
    return None


def header_branding_icon_path() -> Path | None:
    """Return the in-app header strip icon (toolbar asset only; not taskbar/EXE)."""
    return toolbar_icon_png_path()


def icon_ico_path() -> Path | None:
    """Return the official Windows ICO when present."""
    if ICON_ICO.is_file():
        return ICON_ICO
    if LEGACY_ICO.is_file():
        return LEGACY_ICO
    return None


def application_icon() -> QIcon:
    """Taskbar / title-bar icon (``.ico`` preferred on Windows; icon-only assets)."""
    for path in _APP_ICON_CANDIDATES:
        if not path.is_file():
            continue
        icon = QIcon(str(path))
        if not icon.isNull():
            return icon
    return QIcon()


def apply_window_icon(widget: QWidget) -> None:
    """Set the MeshStager icon on a top-level widget or dialog."""
    parent = widget.parentWidget() if isinstance(widget, QDialog) else None
    if parent is not None:
        parent_icon = parent.windowIcon()
        if not parent_icon.isNull():
            widget.setWindowIcon(parent_icon)
            return
    app = QApplication.instance()
    if app is not None:
        app_icon = app.windowIcon()
        if not app_icon.isNull():
            widget.setWindowIcon(app_icon)
            return
    icon = application_icon()
    if not icon.isNull():
        widget.setWindowIcon(icon)
