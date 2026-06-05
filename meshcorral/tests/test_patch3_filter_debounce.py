"""Regression tests for Patch 3 search debounce constant (main window)."""

from __future__ import annotations

import unittest

from meshcorral.ui.main_window import (
    FILTER_SEARCH_DEBOUNCE_MS,
    filter_search_debounce_milliseconds,
)


class TestFilterSearchDebounce(unittest.TestCase):
    """Pin debounce delay for large working sets (reduces UI churn while typing)."""

    def test_debounce_ms_in_required_band(self) -> None:
        """Typing pause before filter apply stays within the product band."""
        ms = filter_search_debounce_milliseconds()
        self.assertGreaterEqual(ms, 350)
        self.assertLessEqual(ms, 550)

    def test_debounce_matches_module_constant(self) -> None:
        """Accessor matches the named constant (single source of truth)."""
        self.assertEqual(filter_search_debounce_milliseconds(), FILTER_SEARCH_DEBOUNCE_MS)


if __name__ == "__main__":
    unittest.main()
