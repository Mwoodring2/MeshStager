"""Unit tests for move planning and execution contract."""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from meshcorral.services.move_service import MoveService, PlanExecutionResult


def _write_file(path: Path, content: bytes = b"x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


class TestMoveServiceExecution(unittest.TestCase):
    """``execute_move_plan`` / ``execute_copy_plan`` return ``PlanExecutionResult``."""

    def setUp(self) -> None:
        self.svc = MoveService()

    def test_execute_move_plan_returns_counts_and_parallel_messages(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "a.txt"
            dest_dir = base / "out"
            _write_file(src)
            dest_dir.mkdir()
            plan = self.svc.build_move_plan([src], dest_dir)
            out = self.svc.execute_move_plan(plan)
        self.assertIsInstance(out, PlanExecutionResult)
        self.assertEqual(out.success_count, 1)
        self.assertEqual(len(out.messages), len(out.items))
        self.assertEqual(out.items[0].status, MoveService.STATUS_MOVED)
        self.assertIn("MOVED", out.messages[0])

    def test_execute_copy_plan_returns_copied_count(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "b.txt"
            dest_dir = base / "copyhere"
            _write_file(src)
            dest_dir.mkdir()
            plan = self.svc.build_move_plan(
                [src], dest_dir, ready_message="Ready to copy."
            )
            out = self.svc.execute_copy_plan(plan)
            self.assertEqual(out.success_count, 1)
            self.assertEqual(out.items[0].status, MoveService.STATUS_COPIED)
            self.assertEqual(len(out.messages), 1)
            self.assertTrue(src.exists())

    def test_build_plan_allows_destination_folder_to_be_created(self) -> None:
        """Destination path may not exist yet if its parent directory exists."""
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "n.txt"
            dest_dir = base / "will_create"
            _write_file(src)
            plan = self.svc.build_move_plan([src], dest_dir)
        self.assertEqual(plan[0].status, MoveService.STATUS_OK)

    def test_blocked_plan_yields_zero_success(self) -> None:
        with TemporaryDirectory() as tmp:
            base = Path(tmp)
            src = base / "c.txt"
            dest_dir = base / "d"
            _write_file(src)
            dest_dir.mkdir()
            (dest_dir / "c.txt").write_bytes(b"block")
            plan = self.svc.build_move_plan([src], dest_dir)
            self.assertEqual(plan[0].status, MoveService.STATUS_BLOCKED)
            out = self.svc.execute_move_plan(plan)
        self.assertEqual(out.success_count, 0)
        self.assertEqual(out.items[0].status, MoveService.STATUS_BLOCKED)
        self.assertEqual(len(out.messages), 1)
