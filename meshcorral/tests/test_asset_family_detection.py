"""Tests for extension-only asset family detection."""

from __future__ import annotations

import unittest

from meshcorral.app.config import (
    ASSET_MODE_3D,
    ASSET_MODE_IMAGES,
    supported_extensions_for_asset_mode,
)
from meshcorral.services.asset_family import (
    ASSET_FAMILY_DCC_SCENE,
    ASSET_FAMILY_GEOMETRY,
    ASSET_FAMILY_IMAGE,
    ASSET_FAMILY_SUPPORT,
    detect_asset_family,
    preview_kind_label_for_family,
)
from meshcorral.models.file_record import FileRecord
from meshcorral.services.search_service import filter_records


class TestAssetFamilyDetection(unittest.TestCase):
    def test_detect_geometry(self) -> None:
        self.assertEqual(detect_asset_family(".stl"), ASSET_FAMILY_GEOMETRY)

    def test_detect_dcc_scene_blend(self) -> None:
        self.assertEqual(detect_asset_family(".blend"), ASSET_FAMILY_DCC_SCENE)

    def test_detect_dcc_scene_ztl(self) -> None:
        self.assertEqual(detect_asset_family(".ztl"), ASSET_FAMILY_DCC_SCENE)

    def test_detect_dcc_scene_ma_mb(self) -> None:
        self.assertEqual(detect_asset_family(".ma"), ASSET_FAMILY_DCC_SCENE)
        self.assertEqual(detect_asset_family(".mb"), ASSET_FAMILY_DCC_SCENE)

    def test_detect_support_mtl(self) -> None:
        self.assertEqual(detect_asset_family(".mtl"), ASSET_FAMILY_SUPPORT)

    def test_detect_image_png(self) -> None:
        self.assertEqual(detect_asset_family(".png"), ASSET_FAMILY_IMAGE)

    def test_3d_mode_includes_blend_and_mtl(self) -> None:
        exts = supported_extensions_for_asset_mode(ASSET_MODE_3D)
        self.assertIn(".blend", exts)
        self.assertIn(".mtl", exts)

    def test_images_mode_excludes_3d_dcc_support(self) -> None:
        exts = supported_extensions_for_asset_mode(ASSET_MODE_IMAGES)
        self.assertNotIn(".stl", exts)
        self.assertNotIn(".blend", exts)
        self.assertNotIn(".mtl", exts)

    def test_type_filter_matches_family_bucket(self) -> None:
        from pathlib import Path

        rows = [
            FileRecord(
                path=Path("C:/x/a.stl"),
                name="a.stl",
                extension=".stl",
                parent_folder="x",
                size_bytes=1,
                modified_time=0.0,
            ),
            FileRecord(
                path=Path("C:/x/b.blend"),
                name="b.blend",
                extension=".blend",
                parent_folder="x",
                size_bytes=1,
                modified_time=0.0,
            ),
            FileRecord(
                path=Path("C:/x/c.mtl"),
                name="c.mtl",
                extension=".mtl",
                parent_folder="x",
                size_bytes=1,
                modified_time=0.0,
            ),
        ]
        out = filter_records(rows, category_filter="DCC Scene", asset_mode=ASSET_MODE_3D)
        self.assertEqual([r.extension for r in out], [".blend"])
        out2 = filter_records(rows, category_filter="Support", asset_mode=ASSET_MODE_3D)
        self.assertEqual([r.extension for r in out2], [".mtl"])

    def test_preview_kind_labels(self) -> None:
        self.assertEqual(preview_kind_label_for_family(ASSET_FAMILY_GEOMETRY), "3D ASSET")
        self.assertEqual(preview_kind_label_for_family(ASSET_FAMILY_DCC_SCENE), "DCC SCENE")
        self.assertEqual(preview_kind_label_for_family(ASSET_FAMILY_SUPPORT), "SUPPORT FILE")
        self.assertEqual(preview_kind_label_for_family(ASSET_FAMILY_IMAGE), "IMAGE")


if __name__ == "__main__":
    unittest.main()

