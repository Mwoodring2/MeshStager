"""Simple add-tag dialog (Tier 2.1)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
)

from meshcorral.ui.layout_constants import TAG_DIALOG_MIN_HEIGHT, TAG_DIALOG_MIN_WIDTH
from meshcorral.ui.responsive_dialog import (
    ResponsiveModalDialog,
    create_content_scroll_area,
    create_pinned_button_row,
)
from meshcorral.services.tagging.tag_validation import parse_tags_from_dialog


class TagDialog(ResponsiveModalDialog):
    """
    Multiline tag entry — one tag per line (commas also accepted).

    Example input::

        helmet
        approved
        print-ready
    """

    responsive_min_width = TAG_DIALOG_MIN_WIDTH
    responsive_min_height = TAG_DIALOG_MIN_HEIGHT

    def __init__(self, parent=None, *, title: str = "Add Tag") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self._content_scroll = None
        self._button_box = None

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(10)

        scroll, _content, scroll_layout = create_content_scroll_area(
            self,
            object_name="TagDialogScrollArea",
        )
        self._content_scroll = scroll

        hint = QLabel(
            "Enter one tag per line. You can also separate tags with commas."
        )
        hint.setWordWrap(True)
        hint.setObjectName("MutedLabel")
        scroll_layout.addWidget(hint)

        self._input = QPlainTextEdit()
        self._input.setPlaceholderText("helmet\napproved\nprint-ready")
        self._input.setMinimumHeight(120)
        scroll_layout.addWidget(self._input)

        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        save_btn = buttons.button(QDialogButtonBox.StandardButton.Save)
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if save_btn is not None:
            save_btn.setText("Save")
        if cancel_btn is not None:
            cancel_btn.setText("Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._button_box = buttons
        root.addWidget(create_pinned_button_row(buttons), 0)

    def input_text(self) -> str:
        """Raw dialog text."""
        return self._input.toPlainText()

    def parsed_tags(self) -> list[str]:
        """Normalized unique tags from the dialog text."""
        return parse_tags_from_dialog(self.input_text())
