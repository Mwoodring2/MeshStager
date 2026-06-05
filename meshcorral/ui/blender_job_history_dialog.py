"""Dialog: recent Blender Bridge jobs (read from output folders, no database)."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from meshcorral.app.bridge.job_history import BlenderJobHistoryItem, list_recent_blender_bridge_jobs
from meshcorral.ui.error_actions import open_file_with_default_app, open_folder_in_explorer
from meshcorral.ui.layout_constants import (
    BLENDER_JOB_HISTORY_DIALOG_MIN_HEIGHT,
    BLENDER_JOB_HISTORY_DIALOG_MIN_WIDTH,
)
from meshcorral.ui.responsive_dialog import ResponsiveModalDialog, create_pinned_button_row


class BlenderJobHistoryDialog(ResponsiveModalDialog):
    """Show a table of recent bridge jobs and actions to open outputs or thumbnails."""

    responsive_min_width = BLENDER_JOB_HISTORY_DIALOG_MIN_WIDTH
    responsive_min_height = BLENDER_JOB_HISTORY_DIALOG_MIN_HEIGHT

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Blender job history")
        self._button_box: QDialogButtonBox | None = None
        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels(
            [
                "Job ID",
                "Type",
                "Source file",
                "Status",
                "Open output",
                "Open log",
                "Output folder",
                "Error",
            ]
        )
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setWordWrap(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setAlternatingRowColors(True)
        self._rows: list[BlenderJobHistoryItem] = []

        self._detail = QLabel("")
        self._detail.setWordWrap(True)
        self._detail.setTextFormat(Qt.TextFormat.RichText)
        self._detail.setObjectName("MutedLabel")

        row2 = QHBoxLayout()
        self._open_folder_btn = QPushButton("Open output folder")
        self._open_folder_btn.setToolTip("Open the job output directory in the file manager.")
        self._open_folder_btn.clicked.connect(self._on_open_output_folder)
        self._open_thumb_btn = QPushButton("Open thumbnail")
        self._open_thumb_btn.setToolTip("Open thumbnail.png with the default viewer (if present).")
        self._open_thumb_btn.clicked.connect(self._on_open_thumbnail)
        self._open_log_btn = QPushButton("Open log.txt")
        self._open_log_btn.setToolTip("Open log.txt in the default text editor (if present).")
        self._open_log_btn.clicked.connect(self._on_open_log)
        row2.addWidget(self._open_folder_btn)
        row2.addWidget(self._open_thumb_btn)
        row2.addWidget(self._open_log_btn)
        row2.addStretch(1)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        row2.addWidget(refresh)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setText("Close")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        self._button_box = buttons

        self._empty_history_label = QLabel(
            "No job history yet. After Blender runs a job, it will appear here (read from output folders)."
        )
        self._empty_history_label.setObjectName("MutedLabel")
        self._empty_history_label.setWordWrap(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.addWidget(QLabel("Recent jobs (newest first). Data is read from bridge output folders."))
        root.addWidget(self._empty_history_label)
        root.addWidget(self._table, 1)
        root.addWidget(self._detail)
        root.addLayout(row2)
        root.addWidget(create_pinned_button_row(buttons))

        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._table.doubleClicked.connect(self._on_double_click)
        self.reload()
        self._update_buttons()

    @staticmethod
    def _status_display(status: str) -> str:
        """User-facing status wording (calm, friendly, and consistent)."""
        s = (status or "").strip().lower()
        if s == "pending":
            return "Queued (waiting)"
        if s == "running":
            return "Running"
        if s == "complete":
            return "Complete"
        if s == "cancelled":
            return "Cancelled (not run)"
        if s == "failed":
            return "Failed"
        return status or "—"

    @staticmethod
    def _make_open_output_button(
        item: BlenderJobHistoryItem, parent: QWidget
    ) -> QPushButton:
        btn = QPushButton("Output")
        btn.setToolTip("Open the output folder for this job.")
        btn.clicked.connect(
            lambda _checked=False, output=Path(item.output_dir): open_folder_in_explorer(
                output, parent, title="Open output folder"
            )
        )
        return btn

    @staticmethod
    def _make_open_log_button(item: BlenderJobHistoryItem, parent: QWidget) -> QPushButton:
        btn = QPushButton("Log")
        btn.setToolTip("Open log.txt for this job (if present).")
        enabled = bool(item.log_path and item.log_path.is_file())
        btn.setEnabled(enabled)
        if enabled:
            btn.clicked.connect(
                lambda _checked=False, lp=item.log_path: open_file_with_default_app(
                    lp, parent, title="Open log"
                )
            )
        return btn

    def _current_item(self) -> BlenderJobHistoryItem | None:
        r = self._table.currentRow()
        if r < 0 or r >= len(self._rows):
            return None
        return self._rows[r]

    def reload(self) -> None:
        self._rows = list_recent_blender_bridge_jobs(limit=100)
        self._table.setRowCount(len(self._rows))
        for i, item in enumerate(self._rows):
            self._table.setItem(i, 0, QTableWidgetItem(item.job_id))
            self._table.setItem(i, 1, QTableWidgetItem(item.job_type))
            self._table.setItem(i, 2, QTableWidgetItem(item.source_filename))
            status_item = QTableWidgetItem(self._status_display(item.status))
            if (item.status or "").strip().lower() == "failed":
                status_item.setForeground(Qt.GlobalColor.red)
            self._table.setItem(i, 3, status_item)

            self._table.setCellWidget(i, 4, self._make_open_output_button(item, self))
            self._table.setCellWidget(i, 5, self._make_open_log_button(item, self))

            self._table.setItem(i, 6, QTableWidgetItem(item.output_dir))
            err = item.error_message or ""
            if len(err) > 120:
                err = err[:117] + "…"
            self._table.setItem(i, 7, QTableWidgetItem(err))
        self._table.resizeColumnsToContents()
        self._empty_history_label.setVisible(len(self._rows) == 0)
        self._detail.setText("")
        self._update_buttons()

    def _on_selection_changed(self) -> None:
        item = self._current_item()
        if item is None:
            self._detail.setText("")
        else:
            lines = [
                f"<b>Job ID:</b> {item.job_id}",
                f"<b>Type:</b> {item.job_type}",
                f"<b>Source:</b> {item.source_filename}",
                f"<b>Status:</b> {item.status}",
                f"<b>Output:</b> {item.output_dir}",
            ]
            if item.error_message:
                lines.append(f"<b>Error:</b> {item.error_message}")
            self._detail.setText("<br/>".join(lines))
        self._update_buttons()

    def _update_buttons(self) -> None:
        item = self._current_item()
        self._open_folder_btn.setEnabled(item is not None)
        has_thumb = bool(
            item
            and item.thumbnail_path
            and Path(item.thumbnail_path).is_file()
        )
        self._open_thumb_btn.setEnabled(has_thumb)
        has_log = bool(item and item.log_path.is_file())
        self._open_log_btn.setEnabled(has_log)

    def _on_double_click(self) -> None:
        self._on_open_output_folder()

    def _on_open_output_folder(self) -> None:
        item = self._current_item()
        if item is None:
            return
        open_folder_in_explorer(Path(item.output_dir), self, title="Open output folder")

    def _on_open_thumbnail(self) -> None:
        item = self._current_item()
        if item is None or not item.thumbnail_path:
            return
        p = Path(item.thumbnail_path)
        if not p.is_file():
            QMessageBox.warning(self, "Open thumbnail", f"File not found:\n{p}")
            return
        ok = QDesktopServices.openUrl(QUrl.fromLocalFile(str(p.resolve())))
        if not ok:
            QMessageBox.warning(self, "Open thumbnail", "Could not open the file with the default app.")

    def _on_open_log(self) -> None:
        item = self._current_item()
        if item is None:
            return
        lp = item.log_path
        if lp is None or not lp.is_file():
            QMessageBox.warning(self, "Open log", "Log not found for this job.")
            return
        open_file_with_default_app(lp, self, title="Open log")
