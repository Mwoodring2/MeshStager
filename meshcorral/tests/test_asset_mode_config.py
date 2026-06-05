"""Tests for scan asset mode helpers in :mod:`meshcorral.app.config`."""

from __future__ import annotations

import unittest

from meshcorral.app.config import (
    ASSET_MODE_3D,
    ASSET_MODE_IMAGES,
    SUPPORTED_3D_EXTENSIONS,
    SUPPORTED_IMAGE_EXTENSIONS,
    file_type_category_map_for_asset_mode,
    supported_extensions_for_asset_mode,
)


class TestAssetModeConfig(unittest.TestCase):
    """Asset modes must partition scan extensions without mixing 3D and image sets in one scan."""

    def test_supported_sets_disjoint(self) -> None:
        """A single scan should not use both 3D and image extensions (unless joined later)."""
        self.assertEqual(
            SUPPORTED_3D_EXTENSIONS & SUPPORTED_IMAGE_EXTENSIONS,
            set(),
        )

    def test_3d_mode_union_equals_supported_3d(self) -> None:
        """3D 'All' category is exactly :data:`SUPPORTED_3D_EXTENSIONS`."""
        m = file_type_category_map_for_asset_mode(ASSET_MODE_3D)
        self.assertEqual(m["All"], SUPPORTED_3D_EXTENSIONS)

    def test_images_mode_only_all(self) -> None:
        m = file_type_category_map_for_asset_mode(ASSET_MODE_IMAGES)
        self.assertEqual(list(m.keys()), ["All", "Image"])
        self.assertEqual(m["All"], SUPPORTED_IMAGE_EXTENSIONS)
        self.assertEqual(m["Image"], SUPPORTED_IMAGE_EXTENSIONS)

    def test_supported_extensions_for_asset_mode(self) -> None:
        self.assertEqual(
            supported_extensions_for_asset_mode(ASSET_MODE_3D),
            set(SUPPORTED_3D_EXTENSIONS),
        )
        self.assertEqual(
            supported_extensions_for_asset_mode(ASSET_MODE_IMAGES),
            set(SUPPORTED_IMAGE_EXTENSIONS),
        )
        self.assertIn(".psd", supported_extensions_for_asset_mode(ASSET_MODE_IMAGES))
