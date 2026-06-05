"""Tests for :class:`~meshcorral.app.bridge.thumb_index.BlenderThumbPathIndex`."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from meshcorral.app.bridge.job_models import BridgeJobResult, BridgeJobStatus
from meshcorral.app.bridge.thumb_index import (
    BlenderThumbPathIndex,
    _norm_path_key,
    inspector_metadata_format,
    metadata_display_tuple,
)
from meshcorral.models.file_record import FileRecord
from meshcorral.models.thumb_health import ThumbHealth


class TestThumbIndex(unittest.TestCase):
    def test_norm_path_key_is_string(self) -> None:
        p = Path("C:/tmp/foo.stl")
        self.assertIsInstance(_norm_path_key(p), str)
        self.assertIsInstance(_norm_path_key("C:/tmp/foo.stl"), str)

    def test_refresh_maps_complete_result_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "outputs" / "blender_bridge" / "job-1"
            root.mkdir(parents=True)
            src = (Path(td) / "mesh.stl").resolve()
            src.write_bytes(b"x")
            thumb = root / "thumbnail.png"
            thumb.write_bytes(b"fakepng")
            (root / "result.json").write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "source_file": str(src),
                        "thumbnail_path": str(thumb),
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "meshcorral.app.bridge.thumb_index.resolve_bridge_paths"
            ) as m:
                m.return_value.outputs_root = Path(td) / "outputs" / "blender_bridge"
                idx = BlenderThumbPathIndex()
                n = idx.refresh()
            self.assertEqual(n, 1)
            self.assertEqual(idx.thumbnail_path_for(src), thumb)

    def test_metadata_display_tuple_from_json(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "m.json"
            p.write_text(
                '{"tags": ["a", "b"], "faces": 1200}',
                encoding="utf-8",
            )
            t, m = metadata_display_tuple(p)
            self.assertIn("a", t)
            self.assertIn("1200", m)
            tags, body, copy_t = inspector_metadata_format(p)
            self.assertIn("a", tags)
            self.assertIn("Faces: 1200", body)
            self.assertIn("— JSON —", copy_t)

    def test_register_job_result_updates_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = (Path(td) / "a.stl").resolve()
            src.write_bytes(b"1")
            out = Path(td) / "out1"
            out.mkdir()
            thumb = out / "thumb.png"
            thumb.write_bytes(b"png")
            (out / "result.json").write_text("{}", encoding="utf-8")
            res = BridgeJobResult(
                job_id="j1",
                status=BridgeJobStatus.COMPLETE,
                source_file=str(src),
                output_dir=str(out),
                thumbnail_path=str(thumb),
            )
            idx = BlenderThumbPathIndex()
            key = idx.register_job_result(res)
            self.assertEqual(key, _norm_path_key(src))
            self.assertEqual(idx.thumbnail_path_for(src), thumb)

    def test_refresh_indexes_failed_thumbnail_job(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bridge_root = Path(td) / "outputs" / "blender_bridge" / "job-bad"
            bridge_root.mkdir(parents=True)
            src = (Path(td) / "mesh.stl").resolve()
            src.write_bytes(b"x")
            (bridge_root / "result.json").write_text(
                json.dumps(
                    {
                        "status": "failed",
                        "job_type": "generate_thumbnail",
                        "source_file": str(src),
                        "output_dir": str(bridge_root),
                        "log_path": str(bridge_root / "blender.log"),
                        "error_message": "boom",
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "meshcorral.app.bridge.thumb_index.resolve_bridge_paths"
            ) as m:
                m.return_value.outputs_root = Path(td) / "outputs" / "blender_bridge"
                idx = BlenderThumbPathIndex()
                n = idx.refresh()
            self.assertEqual(n, 0)
            info = idx.failure_info_for(src)
            self.assertIsNotNone(info)
            self.assertEqual(info.error_message, "boom")
            rec = FileRecord(
                path=src,
                name=src.name,
                extension=".stl",
                parent_folder=src.parent.name,
                size_bytes=1,
                modified_time=0.0,
            )
            self.assertEqual(idx.thumb_health(rec), ThumbHealth.FAILED_THUMBNAIL)

    def test_complete_thumb_clears_failure_on_register(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = (Path(td) / "mesh.stl").resolve()
            src.write_bytes(b"x")
            out = Path(td) / "out_ok"
            out.mkdir()
            thumb = out / "thumbnail.png"
            thumb.write_bytes(b"png")
            (out / "result.json").write_text("{}", encoding="utf-8")
            fail = BridgeJobResult(
                job_id="bad",
                status=BridgeJobStatus.FAILED,
                job_type="generate_thumbnail",
                source_file=str(src),
                output_dir=str(out),
                error_message="nope",
            )
            ok = BridgeJobResult(
                job_id="ok",
                status=BridgeJobStatus.COMPLETE,
                job_type="generate_thumbnail",
                source_file=str(src),
                output_dir=str(out),
                thumbnail_path=str(thumb),
            )
            idx = BlenderThumbPathIndex()
            idx.register_job_result(fail)
            self.assertIsNotNone(idx.failure_info_for(src))
            idx.register_job_result(ok)
            self.assertIsNone(idx.failure_info_for(src))


if __name__ == "__main__":
    unittest.main()
