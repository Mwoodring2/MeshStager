"""Large-folder / server-folder warning before heavy scans (MeshStager)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from meshcorral.app.icon_branding import apply_window_icon
from meshcorral.ui.layout_constants import (
    LARGE_FOLDER_DIALOG_MIN_HEIGHT,
    LARGE_FOLDER_DIALOG_MIN_WIDTH,
)
from meshcorral.ui.responsive_dialog import (
    ResponsiveModalDialog,
    create_content_scroll_area,
    create_pinned_button_row,
)
from meshcorral.services.large_folder_scan_assessment import (
    ARCHIVE_HEAVY_ZIP_THRESHOLD,
    DEEP_DIRECTORY_DEPTH_THRESHOLD,
    LargeFolderAssessment,
    recommended_dialog_defaults,
)


class LargeFolderWarningAction(str, Enum):
    """User choice from the large-folder warning."""

    CONTINUE = "continue"
    CANCEL = "cancel"
    SCAN_WITHOUT_THUMBNAILS = "scan_without_thumbnails"


@dataclass(frozen=True, slots=True)
class LargeFolderWarningResult:
    """Outcome of :meth:`LargeFolderWarningDialog.run_dialog`."""

    action: LargeFolderWarningAction
    skip_future_warnings: bool
    skip_future_remote_only: bool
    visible_thumbnails_only: bool
    lightweight_scan: bool
    background_metadata: bool


class LargeFolderWarningDialog(ResponsiveModalDialog):
    """
    Calm, production-style warning before large or server-folder scans.

    Does not block scanning permanently; Cancel aborts only the pending scan.
    """

    responsive_min_width = LARGE_FOLDER_DIALOG_MIN_WIDTH
    responsive_min_height = LARGE_FOLDER_DIALOG_MIN_HEIGHT

    def __init__(
        self,
        assessment: LargeFolderAssessment,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent=parent)
        self.setWindowTitle("Large Folder / Server Scan Detected")
        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.WindowModal)

        self._assessment = assessment
        self._content_scroll: QScrollArea | None = None
        self._action_row: QWidget | None = None
        vis_default, light_default, meta_default = recommended_dialog_defaults(assessment)

        title = QLabel("Large Folder / Server Scan Detected")
        title.setObjectName("DialogTitle")
        title_font = title.font()
        title_font.setPointSize(title_font.pointSize() + 2)
        title_font.setBold(True)
        title.setFont(title_font)

        intro = QLabel(
            "MeshStager can browse very large asset libraries, but scans on server folders, "
            "archive-heavy directories, or folders containing thousands of assets may take "
            "additional time."
        )
        intro.setWordWrap(True)

        bullets = QLabel(
            "During large scans you may notice:\n"
            "• slower thumbnail generation\n"
            "• delayed metadata enrichment\n"
            "• temporary placeholders while thumbnails load\n"
            "• reduced responsiveness on network storage\n"
            "• unsupported or failed thumbnails for some assets\n\n"
            "MeshStager will prioritize visible items first and continue loading data in the "
            "background."
        )
        bullets.setWordWrap(True)

        rec_label = QLabel("Recommended options:")
        rec_label.setStyleSheet("font-weight: 600;")

        self._visible_thumbs_check = QCheckBox("Visible thumbnails only")
        self._visible_thumbs_check.setChecked(vis_default)
        self._lightweight_check = QCheckBox("Lightweight scan mode")
        self._lightweight_check.setChecked(light_default or assessment.would_use_lightweight)
        self._background_meta_check = QCheckBox("Background metadata enrichment")
        self._background_meta_check.setChecked(meta_default)
        self._background_meta_check.setEnabled(False)
        self._background_meta_check.setToolTip(
            "Metadata enrichment continues in the background during large scans."
        )

        self._skip_check = QCheckBox("Don't show this warning again for large folders")
        self._skip_remote_check = QCheckBox(
            "Don't show again for server / network folders only"
        )

        self._advanced_toggle = QToolButton()
        self._advanced_toggle.setText("Advanced details")
        self._advanced_toggle.setCheckable(True)
        self._advanced_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self._advanced_toggle.toggled.connect(self._on_advanced_toggled)

        self._advanced_panel = QGroupBox("Detected conditions")
        adv_layout = QVBoxLayout(self._advanced_panel)
        adv_layout.addWidget(self._detail_row("Network/server path", assessment.network_like))
        adv_layout.addWidget(
            self._detail_row(
                "Estimated file count",
                self._format_file_count(assessment),
            )
        )
        adv_layout.addWidget(
            self._detail_row(
                "Auto-thumbnails enabled",
                assessment.auto_thumbnails_enabled,
            )
        )
        adv_layout.addWidget(
            self._detail_row(
                "Archive (.zip) count",
                f"{assessment.estimate.archive_zip_count} "
                f"(heavy ≥ {ARCHIVE_HEAVY_ZIP_THRESHOLD})",
            )
        )
        adv_layout.addWidget(
            self._detail_row("Current thumbnail mode", assessment.thumbnail_mode_label)
        )
        adv_layout.addWidget(
            self._detail_row("Current cache mode", assessment.cache_mode_label)
        )
        adv_layout.addWidget(
            self._detail_row(
                "Directory depth",
                f"{assessment.estimate.max_directory_depth} "
                f"(deep ≥ {DEEP_DIRECTORY_DEPTH_THRESHOLD})",
            )
        )
        self._advanced_panel.setVisible(False)

        btn_row = QHBoxLayout()
        self._continue_btn = QPushButton("Continue Scan")
        self._continue_btn.setDefault(True)
        self._continue_btn.setAutoDefault(True)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setToolTip("Cancel this scan (Esc).")
        self._no_thumbs_btn = QPushButton("Scan Without Thumbnails")
        esc_hint = QLabel("Press Esc to cancel")
        esc_hint.setObjectName("MutedLabel")
        btn_row.addWidget(self._continue_btn)
        btn_row.addWidget(self._no_thumbs_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self._cancel_btn)

        self._continue_btn.clicked.connect(self._accept_continue)
        self._no_thumbs_btn.clicked.connect(self._accept_no_thumbs)
        self._cancel_btn.clicked.connect(self.reject)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(10)

        self._content_scroll, _scroll_content, scroll_layout = create_content_scroll_area(
            self,
            object_name="LargeFolderScrollArea",
        )
        scroll_layout.addWidget(title)
        scroll_layout.addWidget(intro)
        scroll_layout.addWidget(bullets)
        scroll_layout.addWidget(rec_label)
        scroll_layout.addWidget(self._visible_thumbs_check)
        scroll_layout.addWidget(self._lightweight_check)
        scroll_layout.addWidget(self._background_meta_check)
        scroll_layout.addSpacing(8)
        scroll_layout.addWidget(self._advanced_toggle)
        scroll_layout.addWidget(self._advanced_panel)
        scroll_layout.addWidget(self._skip_check)
        scroll_layout.addWidget(self._skip_remote_check)
        root.addWidget(self._content_scroll, 1)

        action_container = QWidget(self)
        action_container.setObjectName("LargeFolderActionRow")
        action_layout = QVBoxLayout(action_container)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(8)
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        action_layout.addWidget(line)
        action_layout.addLayout(btn_row)
        action_layout.addWidget(esc_hint)
        self._action_row = create_pinned_button_row(action_container, object_name="LargeFolderButtonRow")
        root.addWidget(self._action_row, 0)
        self.setLayout(root)

        self._esc_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._esc_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._esc_shortcut.activated.connect(self.reject)

        self._result_action = LargeFolderWarningAction.CANCEL
        apply_window_icon(self)

    @staticmethod
    def _detail_row(label: str, value: object) -> QLabel:
        text = f"{label}: {value}"
        row = QLabel(text)
        row.setWordWrap(True)
        return row

    @staticmethod
    def _format_file_count(assessment: LargeFolderAssessment) -> str:
        est = assessment.estimate
        n = est.matching_file_count
        if est.preflight_truncated or est.exceeds_file_threshold:
            return f"{n:,}+ (threshold {assessment.file_count_threshold:,})"
        return f"{n:,} (threshold {assessment.file_count_threshold:,})"

    def _on_advanced_toggled(self, expanded: bool) -> None:
        self._advanced_panel.setVisible(expanded)
        self._advanced_toggle.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow
        )

    def _accept_continue(self) -> None:
        self._result_action = LargeFolderWarningAction.CONTINUE
        self.accept()

    def _accept_no_thumbs(self) -> None:
        self._result_action = LargeFolderWarningAction.SCAN_WITHOUT_THUMBNAILS
        self.accept()

    def result_value(self) -> LargeFolderWarningResult:
        """Return choices after ``exec()`` returns Accepted."""
        skip_all = self._skip_check.isChecked()
        skip_remote = self._skip_remote_check.isChecked() and not skip_all
        return LargeFolderWarningResult(
            action=self._result_action,
            skip_future_warnings=skip_all,
            skip_future_remote_only=skip_remote,
            visible_thumbnails_only=self._visible_thumbs_check.isChecked(),
            lightweight_scan=self._lightweight_check.isChecked(),
            background_metadata=self._background_meta_check.isChecked(),
        )

    @classmethod
    def run_dialog(
        cls,
        assessment: LargeFolderAssessment,
        *,
        parent: QWidget | None = None,
    ) -> LargeFolderWarningResult | None:
        """
        Show the dialog modally (blocking; tests and legacy callers).

        Returns None when the user cancels or closes the dialog.
        """
        dlg = cls(assessment, parent=parent)
        code = dlg.exec()
        if code != int(QDialog.DialogCode.Accepted):
            return None
        return dlg.result_value()

    @classmethod
    def open_dialog(
        cls,
        assessment: LargeFolderAssessment,
        *,
        parent: QWidget | None = None,
        on_finished: object | None = None,
    ) -> "LargeFolderWarningDialog":
        """
        Show the dialog without blocking the parent window event loop.

        *on_finished* receives ``(result: LargeFolderWarningResult | None)``.
        """
        dlg = cls(assessment, parent=parent)

        def _emit(code: int) -> None:
            if on_finished is None:
                return
            if code != int(QDialog.DialogCode.Accepted):
                on_finished(None)
                return
            on_finished(dlg.result_value())

        dlg.finished.connect(_emit)
        dlg.open()
        return dlg
