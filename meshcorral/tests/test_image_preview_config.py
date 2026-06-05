"""Sanity checks for image preview extension configuration."""

from __future__ import annotations

import unittest

from meshcorral.app.config import (
    IMAGE_PREVIEW_EXTENSIONS,
    SUPPORTED_3D_EXTENSIONS,
    SUPPORTED_IMAGE_EXTENSIONS,
    THREE_D_PREVIEW_EXTENSIONS,
)


class TestImagePreviewConfig(unittest.TestCase):
    """Ensure preview extensions stay lowercase and cover common formats."""

    def test_common_raster_extensions_present(self) -> None:
        """PNG, JPEG, and WebP must be included for the preview panel."""
        self.assertIn(".png", IMAGE_PREVIEW_EXTENSIONS)
        self.assertIn(".jpg", IMAGE_PREVIEW_EXTENSIONS)
        self.assertIn(".webp", IMAGE_PREVIEW_EXTENSIONS)

    def test_extensions_are_lowercase(self) -> None:
        """Paths are compared with suffix.lower(); constants must be lower case."""
        for ext in SUPPORTED_IMAGE_EXTENSIONS:
            self.assertEqual(ext, ext.lower())
        for ext in SUPPORTED_3D_EXTENSIONS:
            self.assertEqual(ext, ext.lower())
        self.assertIs(IMAGE_PREVIEW_EXTENSIONS, SUPPORTED_IMAGE_EXTENSIONS)
        self.assertIs(THREE_D_PREVIEW_EXTENSIONS, SUPPORTED_3D_EXTENSIONS)

    def test_3d_preview_extensions_no_overlap_with_images(self) -> None:
        """Image and 3D type-card sets are disjoint (first branch wins for images)."""
        self.assertEqual(SUPPORTED_IMAGE_EXTENSIONS & SUPPORTED_3D_EXTENSIONS, set())

    def test_3d_includes_obj_and_stl(self) -> None:
        """Common 3D formats must be covered by the type card set."""
        self.assertIn(".obj", SUPPORTED_3D_EXTENSIONS)
        self.assertIn(".stl", SUPPORTED_3D_EXTENSIONS)
        self.assertIn(".blend", SUPPORTED_3D_EXTENSIONS)
