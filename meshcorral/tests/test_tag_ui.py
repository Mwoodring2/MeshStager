"""UI tests for Tier 2.1 tag widgets."""

from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from meshcorral.ui.tags.tag_dialog import TagDialog
from meshcorral.ui.tags.tag_editor_widget import TagEditorWidget


def _qapp() -> QApplication:
    inst = QApplication.instance()
    if inst is None:
        return QApplication([])
    return inst  # type: ignore[return-value]


class TestTagDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _qapp()

    def test_parsed_tags_from_multiline(self) -> None:
        dialog = TagDialog()
        dialog._input.setPlainText("helmet\napproved\nprint-ready")
        self.assertEqual(dialog.parsed_tags(), ["helmet", "approved", "print-ready"])


class TestTagEditorWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _qapp()

    def test_single_selection_summary(self) -> None:
        widget = TagEditorWidget()
        widget.set_selection(
            paths=[Path("C:/a.stl")],
            tags=["helmet", "approved"],
            multi=False,
        )
        self.assertIn("helmet", widget._summary.text())

    def test_multi_selection_button_label(self) -> None:
        widget = TagEditorWidget()
        widget.set_selection(
            paths=[Path("C:/a.stl"), Path("C:/b.stl")],
            tags=[],
            multi=True,
        )
        self.assertEqual(widget._add_btn.text(), "+ Add Tag to 2 Assets")


if __name__ == "__main__":
    unittest.main()
