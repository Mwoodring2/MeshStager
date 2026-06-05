"""Context menu action specs for Blender bridge batching."""

from __future__ import annotations

import unittest

from meshcorral.ui.context_actions import FILE_CONTEXT_ACTIONS


class TestContextActionBridgeSelection(unittest.TestCase):
    def test_blender_single_one_only(self) -> None:
        by_key = {s.key: s for s in FILE_CONTEXT_ACTIONS}
        s = by_key["blender_thumbnail"]
        self.assertEqual(s.selection_count_min, 1)
        self.assertEqual(s.selection_count_max, 1)

    def test_blender_batch_requires_two(self) -> None:
        by_key = {s.key: s for s in FILE_CONTEXT_ACTIONS}
        s = by_key["blender_thumbnails_batch"]
        self.assertEqual(s.selection_count_min, 2)
        self.assertIsNone(s.selection_count_max)
