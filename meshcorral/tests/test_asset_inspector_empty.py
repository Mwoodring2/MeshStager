"""Tests for asset inspector empty-state messaging."""

from __future__ import annotations

import unittest

from PySide6.QtWidgets import QApplication

from meshcorral.ui.asset_inspector import AssetInspectorPanel
from meshcorral.ui.empty_states import NO_SELECTION, READY_TO_SCAN, empty_state_spec


class TestAssetInspectorEmpty(unittest.TestCase):
    """Ensure empty inspector copy distinguishes no-scan vs no-selection."""

    @classmethod
    def setUpClass(cls) -> None:
        """Qt widgets require a QApplication."""
        inst = QApplication.instance()
        if inst is None:
            cls._app = QApplication([])
        else:
            cls._app = inst

    def test_show_empty_session_active_uses_selection_copy(self) -> None:
        """After a scan, the empty state should prompt for row selection."""
        panel = AssetInspectorPanel()
        panel.show_empty(session_active=True)
        self.assertEqual(
            panel._empty_detail_label.text(),
            empty_state_spec(NO_SELECTION).body,
        )

    def test_show_empty_no_session_uses_scan_first_copy(self) -> None:
        """Before any scan, the empty state should prompt to scan first."""
        panel = AssetInspectorPanel()
        panel.show_empty(session_active=False)
        self.assertEqual(
            panel._empty_detail_label.text(),
            empty_state_spec(READY_TO_SCAN).body,
        )


if __name__ == "__main__":
    unittest.main()
