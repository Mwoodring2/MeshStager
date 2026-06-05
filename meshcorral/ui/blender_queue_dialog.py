"""Dialog listing pending Blender Bridge jobs (in-memory queue + disk ``pending/``)."""

from __future__ import annotations

from PySide6.QtCore import Qt
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

from meshcorral.app.bridge.queue_manager import BridgeQueueManager, QueuedJobInfo
from meshcorral.ui.layout_constants import (
    BLENDER_QUEUE_DIALOG_MIN_HEIGHT,
    BLENDER_QUEUE_DIALOG_MIN_WIDTH,
)
from meshcorral.ui.responsive_dialog import ResponsiveModalDialog, create_pinned_button_row


class BlenderQueueDialog(ResponsiveModalDialog):
    """Show jobs waiting in the bridge queue; cancel individual or all (not the running job)."""

    responsive_min_width = BLENDER_QUEUE_DIALOG_MIN_WIDTH
    responsive_min_height = BLENDER_QUEUE_DIALOG_MIN_HEIGHT

    def __init__(self, manager: BridgeQueueManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._manager = manager
        self.setWindowTitle("Blender queue")
        self._button_box: QDialogButtonBox | None = None
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Job ID", "Type", "Source file", "Status"])
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._rows: list[QueuedJobInfo] = []
        self._rows_by_index: list[str] = []

        row_btns = QHBoxLayout()
        self._cancel_one_btn = QPushButton("Cancel selected")
        self._cancel_one_btn.setToolTip("Remove the selected row from the queue (if still pending).")
        self._cancel_one_btn.clicked.connect(self._on_cancel_selected)
        self._cancel_all_btn = QPushButton("Cancel all pending")
        self._cancel_all_btn.setToolTip(
            "Remove every job waiting in the queue. Does not stop the job currently in Blender."
        )
        self._cancel_all_btn.clicked.connect(self._on_cancel_all)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._refresh)
        row_btns.addWidget(self._cancel_one_btn)
        row_btns.addWidget(self._cancel_all_btn)
        row_btns.addStretch(1)
        row_btns.addWidget(refresh)

        help_lbl = QLabel(
            "Jobs run one at a time in the background. You can remove jobs that are still waiting "
            "in the queue. A job that has already started in Blender cannot be cancelled here."
        )
        help_lbl.setObjectName("MutedLabel")
        help_lbl.setWordWrap(True)

        self._empty_queue_label = QLabel(
            "No jobs are waiting right now. Thumbnail jobs you queue appear here while they wait to run."
        )
        self._empty_queue_label.setObjectName("MutedLabel")
        self._empty_queue_label.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_btn = buttons.button(QDialogButtonBox.StandardButton.Close)
        if close_btn is not None:
            close_btn.setText("Close")
        buttons.rejected.connect(self.reject)
        self._button_box = buttons

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.addWidget(help_lbl)
        root.addWidget(self._empty_queue_label)
        root.addWidget(self._table, 1)
        root.addLayout(row_btns)
        root.addWidget(create_pinned_button_row(buttons))
        self._refresh()

    def _refresh(self) -> None:
        self._rows = self._manager.pending_jobs()
        self._table.setRowCount(len(self._rows))
        self._rows_by_index = [r.job_id for r in self._rows]
        for i, r in enumerate(self._rows):
            self._table.setItem(i, 0, QTableWidgetItem(r.job_id))
            self._table.setItem(i, 1, QTableWidgetItem(r.job_type))
            self._table.setItem(i, 2, QTableWidgetItem(r.source_filename))
            item = QTableWidgetItem("Queued (waiting)")
            item.setData(Qt.ItemDataRole.UserRole, r.job_id)
            self._table.setItem(i, 3, item)
        self._table.resizeColumnsToContents()
        has_rows = self._rows
        self._empty_queue_label.setVisible(len(self._rows) == 0)
        self._cancel_one_btn.setEnabled(bool(has_rows))
        self._cancel_all_btn.setEnabled(self._manager.queue_length() > 0)

    def _on_cancel_selected(self) -> None:
        row = self._table.currentRow()
        if row < 0 or row >= len(self._rows_by_index):
            QMessageBox.information(
                self,
                "Cancel",
                "Select a row in the table first.",
            )
            return
        jid = self._rows_by_index[row]
        if not self._manager.cancel_queued_job_id(jid):
            QMessageBox.warning(
                self,
                "Cancel",
                "Could not cancel that job. It may have already started, finished, or been removed.",
            )
        self._refresh()

    def _on_cancel_all(self) -> None:
        n = self._manager.cancel_all_queued()
        if n:
            self._refresh()
        else:
            QMessageBox.information(self, "Cancel all", "There is nothing in the queue to cancel.")
