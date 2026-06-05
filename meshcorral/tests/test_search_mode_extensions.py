"""Asset Mode (3D vs Images): extension sets and filtering must never mix types."""

from __future__ import annotations

import unittest

from meshcorral.app.config import ASSET_MODE_3D, ASSET_MODE_IMAGES, SUPPORTED_3D_EXTENSIONS
from meshcorral.models.file_record import FileRecord
from meshcorral.services.search_service import filter_records


def _rec(path: str, ext: str) -> FileRecord:
    from pathlib import Path

    p = Path(path)
    return FileRecord(
        path=p,
        name=p.name,
        extension=ext,
        parent_folder="f",
        size_bytes=1,
        modified_time=0.0,
    )


class TestSearchModeExtensions(unittest.TestCase):
    def test_images_extensions_disjoint_from_3d_mesh_extensions(self) -> None:
        from meshcorral.app.config import (
            extensions_for_asset_category,
            supported_extensions_for_asset_mode,
        )

        img = supported_extensions_for_asset_mode(ASSET_MODE_IMAGES)
        d3 = supported_extensions_for_asset_mode(ASSET_MODE_3D)
        self.assertNotIn(".stl", img)
        self.assertNotIn(".obj", img)
        self.assertIn(".png", img)
        self.assertIn(".stl", d3)
        ext_list_img = extensions_for_asset_category(ASSET_MODE_IMAGES, "All")
        self.assertNotIn(".stl", ext_list_img)
        self.assertIn(".png", ext_list_img)

    def test_filter_records_respects_asset_mode_extension_universe(self) -> None:
        stl = _rec("C:/a/mesh.stl", ".stl")
        png = _rec("C:/a/tex.png", ".png")
        both = [stl, png]
        out_3d = filter_records(both, asset_mode=ASSET_MODE_3D)
        self.assertEqual(out_3d, [stl])
        out_img = filter_records(both, asset_mode=ASSET_MODE_IMAGES)
        self.assertEqual(out_img, [png])

    def test_supported_3d_includes_fbx_for_scan_consistency(self) -> None:
        self.assertIn(".fbx", SUPPORTED_3D_EXTENSIONS)


if __name__ == "__main__":
    unittest.main()
