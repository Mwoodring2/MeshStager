"""Dialogs used by MeshStager."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from meshcorral.app.config import APP_NAME, APP_VERSION
from meshcorral.app.icon_branding import apply_window_icon
from meshcorral.models.move_plan import MovePlan
from meshcorral.ui.layout_constants import (
    ABOUT_DIALOG_MIN_HEIGHT,
    ABOUT_DIALOG_MIN_WIDTH,
    DIALOG_MIN_WIDTH,
    MOVE_PREVIEW_DIALOG_MIN_HEIGHT,
    MOVE_PREVIEW_DIALOG_MIN_WIDTH,
    SCAN_OPTIONS_DIALOG_MIN_HEIGHT,
)
from meshcorral.ui.responsive_dialog import (
    ResponsiveModalDialog,
    create_pinned_button_row,
)


@dataclass(frozen=True, slots=True)
class ScanOptions:
    """User choices for a folder scan (v1: extension set is fixed in config)."""

    folder: Path
    recursive: bool


class ScanOptionsDialog(ResponsiveModalDialog):
    """Dialog for selecting a scan folder and recursive option."""

    responsive_min_width = DIALOG_MIN_WIDTH
    responsive_min_height = SCAN_OPTIONS_DIALOG_MIN_HEIGHT

    def __init__(self, *, parent: QWidget | None, default_recursive: bool) -> None:
        super().__init__(parent=parent)
        self.setWindowTitle("Scan folder")
        self.setModal(True)
        apply_window_icon(self)

        self._folder_edit = QLineEdit()
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self._folder_edit, 1)
        folder_row.addWidget(browse_btn)

        self._recursive = QCheckBox("Recursive scan (include subfolders)")
        self._recursive.setChecked(bool(default_recursive))

        form = QFormLayout()
        form.addRow("Folder", folder_row)
        form.addRow("", self._recursive)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok is not None:
            ok.setText("Scan")
            ok.setDefault(True)
            ok.setAutoDefault(True)
        cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel is not None:
            cancel.setText("Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.addLayout(form)
        layout.addWidget(create_pinned_button_row(buttons))
        self._button_box = buttons

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select folder to scan")
        if folder:
            self._folder_edit.setText(folder)

    def value(self) -> ScanOptions:
        text = (self._folder_edit.text() or "").strip()
        if not text:
            raise ValueError("Scan folder is required.")
        return ScanOptions(
            folder=Path(text),
            recursive=bool(self._recursive.isChecked()),
        )


class MovePreviewDialog(ResponsiveModalDialog):
    """Dry-run move or copy preview dialog."""

    responsive_min_width = MOVE_PREVIEW_DIALOG_MIN_WIDTH
    responsive_min_height = MOVE_PREVIEW_DIALOG_MIN_HEIGHT

    def __init__(
        self,
        *,
        parent: QWidget | None,
        plan: list[MovePlan],
        is_copy: bool = False,
    ) -> None:
        super().__init__(parent=parent)
        self.setWindowTitle("Copy preview (dry-run)" if is_copy else "Move preview (dry-run)")
        self.setModal(True)
        apply_window_icon(self)
        self._button_box: QDialogButtonBox | None = None

        summary = self._build_summary(plan)
        summary_label = QLabel(summary)
        summary_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

        execution_note = QLabel(
            "What you confirm is what runs: only OK rows are written to disk. "
            "Blocked and Error rows are skipped."
        )
        execution_note.setWordWrap(True)

        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Status", "Source", "Destination", "Message"])
        table.setRowCount(len(plan))
        table.setSortingEnabled(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setSelectionMode(QTableWidget.ExtendedSelection)

        for row, item in enumerate(plan):
            table.setItem(row, 0, QTableWidgetItem(item.status))
            table.setItem(row, 1, QTableWidgetItem(str(item.source_path)))
            table.setItem(row, 2, QTableWidgetItem(str(item.destination_path)))
            table.setItem(row, 3, QTableWidgetItem(item.message))

        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)

        trust_note = QLabel(
            "Existing destination files are never overwritten. "
            "If counts change after this dialog, run preview again before confirming."
        )
        trust_note.setWordWrap(True)

        button_box = QDialogButtonBox(self)
        self._button_box = button_box
        action = "Copy" if is_copy else "Move"
        accept_btn = button_box.addButton(
            action,
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        button_box.addButton("Cancel", QDialogButtonBox.ButtonRole.RejectRole)
        if isinstance(accept_btn, QPushButton):
            accept_btn.setDefault(True)
            accept_btn.setAutoDefault(True)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.addWidget(summary_label)
        layout.addWidget(execution_note)
        layout.addWidget(table, 1)
        layout.addWidget(trust_note)
        layout.addWidget(create_pinned_button_row(button_box))

    @staticmethod
    def _build_summary(plan: list[MovePlan]) -> str:
        total = len(plan)
        ok_count = sum(1 for p in plan if p.status == "OK")
        blocked = sum(1 for p in plan if p.status == "BLOCKED")
        errors = sum(1 for p in plan if p.status == "ERROR")
        return f"Total: {total}   OK: {ok_count}   Blocked: {blocked}   Errors: {errors}"


class AboutDialog(ResponsiveModalDialog):
    """A minimal About dialog."""

    responsive_min_width = ABOUT_DIALOG_MIN_WIDTH
    responsive_min_height = ABOUT_DIALOG_MIN_HEIGHT

    def __init__(self, *, parent: QWidget | None) -> None:
        super().__init__(parent=parent)
        self.setWindowTitle(f"About {APP_NAME}")
        self.setModal(True)
        apply_window_icon(self)

        text = QLabel(
            f"{APP_NAME} v{APP_VERSION}\n\n"
            "Find and organize your files safely.\n\n"
            "Part of The Yard tool suite."
        )
        text.setTextInteractionFlags(Qt.TextSelectableByMouse)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setText("Close")
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.addWidget(text)
        layout.addWidget(create_pinned_button_row(buttons))
        self._button_box = buttons
