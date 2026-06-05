"""Regression tests for Patch 4 error UX helpers."""

from __future__ import annotations

import unittest
from pathlib import Path

from meshcorral.models.move_plan import MovePlan
from meshcorral.services.move_service import MoveService
from meshcorral.ui.blender_job_history_dialog import BlenderJobHistoryDialog
from meshcorral.ui.main_window import _transfer_counts


class TestPatch4ErrorUx(unittest.TestCase):
    def test_transfer_counts(self) -> None:
        items = [
            MovePlan(Path("a.txt"), Path("b.txt"), MoveService.STATUS_MOVED, "ok"),
            MovePlan(Path("c.txt"), Path("d.txt"), MoveService.STATUS_COPIED, "ok"),
            MovePlan(Path("e.txt"), Path("f.txt"), MoveService.STATUS_BLOCKED, "skip"),
            MovePlan(Path("g.txt"), Path("h.txt"), MoveService.STATUS_ERROR, "fail"),
        ]
        ok_n, blocked_n, error_n = _transfer_counts(items)
        self.assertEqual(ok_n, 2)
        self.assertEqual(blocked_n, 1)
        self.assertEqual(error_n, 1)

    def test_status_display_is_friendly(self) -> None:
        self.assertEqual(BlenderJobHistoryDialog._status_display("pending"), "Queued (waiting)")
        self.assertEqual(BlenderJobHistoryDialog._status_display("cancelled"), "Cancelled (not run)")
        self.assertEqual(BlenderJobHistoryDialog._status_display("failed"), "Failed")
        self.assertEqual(BlenderJobHistoryDialog._status_display("complete"), "Complete")


if __name__ == "__main__":
    unittest.main()

