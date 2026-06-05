"""Centralized, user-friendly helper actions for error recovery.

Patch 4 goals:
- Keep error UX calm and actionable.
- Make logs/output folders one click away.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ErrorActionTargets:
    """Optional paths/text tied to a failure."""

    output_dir: Path | None = None
    log_path: Path | None = None
    error_message: str | None = None


def copy_to_clipboard(text: str) -> None:
    """Copy *text* to the clipboard if possible."""
    app = QApplication.instance()
    if app is None:
        return
    cb = app.clipboard()
    if cb is None:
        return
    cb.setText(text)


def open_file_with_default_app(path: Path, parent: QWidget | None, *, title: str) -> bool:
    """Open a file using the OS default handler; show a friendly message on failure."""
    p = Path(path).expanduser()
    try:
        resolved = p.resolve()
    except OSError:
        resolved = p
    if not resolved.is_file():
        QMessageBox.warning(parent, title, f"File not found:\n{resolved}")
        return False
    try:
        ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved)))
    except Exception as exc:
        logger.warning("Could not open file %s: %s", resolved, exc)
        QMessageBox.warning(parent, title, f"Could not open the file.\n\n{exc}")
        return False
    if not ok:
        QMessageBox.warning(parent, title, "Could not open the file with the default application.")
        return False
    return True


def open_folder_in_explorer(folder: Path, parent: QWidget | None, *, title: str) -> bool:
    """Open a folder in the OS file manager; show a friendly message on failure."""
    f = Path(folder).expanduser()
    try:
        resolved = f.resolve()
    except OSError:
        resolved = f
    if not resolved.is_dir():
        QMessageBox.warning(parent, title, f"Folder not found:\n{resolved}")
        return False
    try:
        if os.name == "nt":
            os.startfile(str(resolved))  # type: ignore[attr-defined]
            return True
        ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(resolved)))
        if not ok:
            QMessageBox.warning(parent, title, "Could not open the folder.")
            return False
        return True
    except OSError as exc:
        logger.warning("Could not open folder %s: %s", resolved, exc)
        QMessageBox.warning(parent, title, str(exc))
        return False

