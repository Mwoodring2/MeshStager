"""Unit tests for main-window action button disabled-reason helpers."""

from __future__ import annotations

import unittest

from meshcorral.ui.main_window import (
    _reason_export_disabled,
    _reason_file_actions_disabled,
    _reason_transfer_buttons_disabled,
)


class TestActionButtonTooltips(unittest.TestCase):
    """Cover ordering of disabled reasons for transfer, export, and file actions."""

    def test_transfer_reason_scan_first(self) -> None:
        """Without a source, Move/Copy should ask for a scan first."""
        msg = _reason_transfer_buttons_disabled(
            has_source=False,
            has_visible=True,
            has_selection=True,
            has_destination=True,
        )
        self.assertIn("Scan", msg)

    def test_transfer_reason_empty_string_when_ready(self) -> None:
        """When all flags are true, no disabled-reason string is returned."""
        msg = _reason_transfer_buttons_disabled(
            has_source=True,
            has_visible=True,
            has_selection=True,
            has_destination=True,
        )
        self.assertEqual(msg, "")

    def test_export_reason_needs_visible_rows(self) -> None:
        """Export explains empty view after a scan exists."""
        msg = _reason_export_disabled(has_source=True, has_visible=False)
        self.assertIn("view", msg.lower())

    def test_file_actions_need_selection(self) -> None:
        """Reveal / copy path ask for row selection when source exists."""
        msg = _reason_file_actions_disabled(has_source=True, has_selection=False)
        self.assertIn("Select", msg)


if __name__ == "__main__":
    unittest.main()
