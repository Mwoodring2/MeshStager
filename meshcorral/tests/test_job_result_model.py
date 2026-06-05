"""Tests for Blender Bridge :class:`BridgeJobResult` JSON shape."""

from __future__ import annotations

import unittest

from meshcorral.app.bridge.job_models import BridgeJobResult, BridgeJobStatus


class TestJobResultModel(unittest.TestCase):
    """Ensure ``result.json`` field names round-trip (worker ↔ app)."""

    def test_result_json_minimal_fields(self) -> None:
        data = {
            "job_id": "abc-1",
            "job_type": "generate_thumbnail",
            "status": "complete",
            "source_file": "C:/a/model.stl",
            "output_dir": "C:/out/1",
            "thumbnail_path": "C:/out/1/thumbnail.png",
            "error_message": None,
        }
        r = BridgeJobResult.from_json_dict(data)
        self.assertEqual(r.job_id, "abc-1")
        self.assertEqual(r.status, BridgeJobStatus.COMPLETE)
        self.assertEqual(r.job_type, "generate_thumbnail")
        self.assertEqual(r.source_file, "C:/a/model.stl")
        self.assertEqual(r.output_dir, "C:/out/1")
        out = r.to_json_dict()
        self.assertEqual(out["status"], "complete")
        self.assertIn("source_file", out)
        self.assertIn("output_dir", out)
        self.assertEqual(out.get("job_type"), "generate_thumbnail")
