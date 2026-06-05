"""Tests for :mod:`meshcorral.app.bridge.job_history` (scan ``result.json`` on disk)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from meshcorral.app.bridge.job_history import list_recent_blender_bridge_jobs


class TestJobHistoryScan(unittest.TestCase):
    def test_lists_jobs_from_result_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            out = t / "blender_out"
            j1 = out / "j1-uuid"
            j1.mkdir(parents=True)
            (j1 / "result.json").write_text(
                json.dumps(
                    {
                        "job_id": "j1-uuid",
                        "job_type": "generate_thumbnail",
                        "status": "complete",
                        "source_file": "C:/m/a.stl",
                        "output_dir": str(j1.resolve()),
                        "thumbnail_path": str(j1 / "thumbnail.png"),
                        "error_message": None,
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "meshcorral.app.bridge.job_history.resolve_bridge_paths",
                return_value=SimpleNamespace(outputs_root=out),
            ):
                items = list_recent_blender_bridge_jobs(limit=10)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].job_id, "j1-uuid")
        self.assertEqual(items[0].source_filename, "a.stl")
        self.assertEqual(items[0].status, "complete")

    def test_empty_when_no_output_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp) / "missing" / "nested"
            t.mkdir(parents=True)
            with patch(
                "meshcorral.app.bridge.job_history.resolve_bridge_paths",
                return_value=SimpleNamespace(outputs_root=t / "nope"),
            ):
                items = list_recent_blender_bridge_jobs()
        self.assertEqual(items, [])
