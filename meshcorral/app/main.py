"""Main application wiring for MeshStager."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from meshcorral.app.config import APP_NAME, APP_ORG_DOMAIN, APP_ORG_NAME
from meshcorral.app.icon_branding import application_icon, set_windows_app_user_model_id
from meshcorral.services.settings_service import SettingsService
from meshcorral.ui.main_window import MainWindow
from meshcorral.ui.theme import apply_theme_palette
from meshcorral.utils.logging_setup import configure_logging

def _window_minimized_flag() -> Qt.WindowState:
    """Return the WindowMinimized flag for the installed PySide6 build."""
    try:
        return Qt.WindowState.WindowMinimized
    except AttributeError:
        return Qt.WindowMinimized


def present_main_window(window: MainWindow) -> None:
    """Show the main window on the active desktop (not minimized or off-screen)."""
    minimized = _window_minimized_flag()
    state = window.windowState()
    if state & minimized:
        window.setWindowState(state & ~minimized)
    window.showNormal()
    window.show()
    window.raise_()
    window.activateWindow()


def main() -> int:
    """Run the MeshStager desktop application."""
    configure_logging()
    set_windows_app_user_model_id()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORG_NAME)
    app.setOrganizationDomain(APP_ORG_DOMAIN)
    icon = application_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    apply_theme_palette(app, SettingsService().theme_mode())

    window = MainWindow()
    if not icon.isNull():
        window.setWindowIcon(icon)
    present_main_window(window)
    return app.exec()


def run() -> int:
    """Backward-compatible alias."""
    return main()


if __name__ == "__main__":
    raise SystemExit(main())

