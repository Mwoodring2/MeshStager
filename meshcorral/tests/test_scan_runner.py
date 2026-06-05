"""Tests for :mod:`meshcorral.ui.scan_runner` staging constants."""

from __future__ import annotations

import unittest


class TestScanRunner(unittest.TestCase):
    """Sanity checks for background scan batch sizing."""

    def test_scan_ui_batch_size_in_sane_range(self) -> None:
        """Batch size should limit signal frequency without huge UI spikes."""
        from meshcorral.ui.scan_runner import SCAN_UI_BATCH_SIZE

        self.assertGreaterEqual(SCAN_UI_BATCH_SIZE, 50)
        self.assertLessEqual(SCAN_UI_BATCH_SIZE, 500)


if __name__ == "__main__":
    unittest.main()
