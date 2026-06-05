"""Prime v1.0 RC — empty-state copy and widgets."""

from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from meshcorral.ui.empty_states import (
    FRESH_LAUNCH,
    MULTI_SELECTION,
    NO_MATCHING_RESULTS,
    NO_SELECTION,
    READY_TO_SCAN,
    SCAN_CANCELED,
    SOURCE_UNAVAILABLE,
    empty_state_hint_lines,
    empty_state_spec,
    make_empty_state_widget,
    update_empty_state_widget,
)
from meshcorral.ui.theme import build_app_stylesheet


def _qapp() -> QApplication:
    inst = QApplication.instance()
    if inst is None:
        return QApplication([])
    return inst


class TestEmptyStateSpecs(unittest.TestCase):
    def test_canonical_titles(self) -> None:
        self.assertEqual(empty_state_spec(NO_SELECTION).title, "Select an asset")
        self.assertEqual(empty_state_spec(READY_TO_SCAN).title, "Ready to scan")
        self.assertEqual(empty_state_spec(NO_MATCHING_RESULTS).title, "No matching results")
        self.assertEqual(empty_state_spec(SOURCE_UNAVAILABLE).title, "Source unavailable")
        self.assertEqual(empty_state_spec(SCAN_CANCELED).title, "Scan canceled")

    def test_fresh_launch_body(self) -> None:
        body = empty_state_spec(FRESH_LAUNCH).body
        self.assertIn("source folder", body.lower())

    def test_hint_lines_include_title_and_body(self) -> None:
        text = empty_state_hint_lines(empty_state_spec(MULTI_SELECTION))
        self.assertIn("Multiple assets selected", text)
        self.assertIn("Batch actions", text)


class TestEmptyStateWidget(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _qapp()

    def test_widget_has_title_and_body_labels(self) -> None:
        host = make_empty_state_widget(empty_state_spec(NO_SELECTION))
        title = host.findChild(QLabel, "EmptyStateTitle")
        body = host.findChild(QLabel, "EmptyStateBody")
        self.assertIsNotNone(title)
        self.assertIsNotNone(body)
        self.assertEqual(title.text(), "Select an asset")

    def test_update_empty_state_widget(self) -> None:
        host = make_empty_state_widget(empty_state_spec(NO_SELECTION))
        update_empty_state_widget(host, empty_state_spec(READY_TO_SCAN))
        body = host.findChild(QLabel, "EmptyStateBody")
        self.assertIsNotNone(body)
        self.assertIn("Scan the selected source", body.text())

    def test_widget_does_not_add_vertical_stretch(self) -> None:
        parent = QWidget()
        lay = QVBoxLayout(parent)
        host = make_empty_state_widget(empty_state_spec(NO_SELECTION), parent=parent)
        lay.addWidget(host)
        stretch_items = [
            lay.itemAt(i).spacerItem()
            for i in range(lay.count())
            if lay.itemAt(i).spacerItem() is not None
        ]
        self.assertEqual(stretch_items, [])


class TestEmptyStateTheme(unittest.TestCase):
    def test_stylesheet_includes_empty_state_tokens(self) -> None:
        css = build_app_stylesheet("dark")
        self.assertIn("QLabel#EmptyStateTitle", css)
        self.assertIn("QLabel#EmptyStateBody", css)


if __name__ == "__main__":
    unittest.main()
