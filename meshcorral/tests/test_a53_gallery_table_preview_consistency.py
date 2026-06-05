"""A5.3 — gallery / table / preview state language and filename display."""

from __future__ import annotations

import unittest

from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.ui.empty_states import METADATA_DEFERRED, empty_state_spec
from meshcorral.ui.filename_display import truncate_filename
from meshcorral.ui.thumbnails.asset_state_copy import (
    STATE_DEFERRED,
    STATE_FAILED,
    STATE_READY,
    STATE_TIMEOUT,
    STATE_UNSUPPORTED,
    standard_copy_for_confidence,
    standard_copy_for_inspector,
)
from meshcorral.ui.thumbnails.thumbnail_confidence import (
    ThumbConfidenceState,
    confidence_state_for,
)
from meshcorral.ui.thumbnails.thumbnail_ux_copy import build_preview_thumb_ux


class TestStandardStateCopy(unittest.TestCase):
    def test_deferred_language(self) -> None:
        std = standard_copy_for_confidence(ThumbConfidenceState.DEFERRED)
        self.assertEqual(std.title, "Deferred Preview")
        self.assertIn("Deferred", std.subtitle)

    def test_ready_language(self) -> None:
        std = standard_copy_for_confidence(ThumbConfidenceState.READY)
        self.assertEqual(std.title, "Thumbnail Ready")
        self.assertIn("Preview", std.subtitle)

    def test_unsupported_language(self) -> None:
        std = standard_copy_for_confidence(ThumbConfidenceState.UNSUPPORTED)
        self.assertEqual(std.title, "No Preview")
        self.assertIn("preview", std.subtitle.lower())

    def test_failed_timeout_corrupt(self) -> None:
        self.assertEqual(standard_copy_for_confidence(ThumbConfidenceState.FAILED), STATE_FAILED)
        self.assertEqual(standard_copy_for_confidence(ThumbConfidenceState.TIMEOUT), STATE_TIMEOUT)

    def test_inspector_deferred_matches_gallery(self) -> None:
        std = standard_copy_for_inspector(
            health=ThumbHealth.PENDING,
            visual=ThumbVisualState.PLACEHOLDER,
            deferred=True,
        )
        self.assertEqual(std, STATE_DEFERRED)

    def test_preview_ux_uses_standard_deferred(self) -> None:
        ux = build_preview_thumb_ux(
            health=ThumbHealth.PENDING,
            visual=ThumbVisualState.PLACEHOLDER,
            generating=False,
            queued=False,
            decoding=False,
            can_mesh_thumbnail=True,
            has_blender_thumbnail=False,
            bridge_error_message=None,
            thumb_perf_deferred=True,
        )
        self.assertEqual(ux.headline, "Deferred Preview")
        self.assertIn("Deferred", ux.body)

    def test_metadata_empty_state_matches(self) -> None:
        spec = empty_state_spec(METADATA_DEFERRED)
        self.assertEqual(spec.title, STATE_DEFERRED.title)
        self.assertEqual(spec.body, STATE_DEFERRED.subtitle)


class TestFilenameTruncation(unittest.TestCase):
    def test_short_name_unchanged(self) -> None:
        self.assertEqual(truncate_filename("part.stl"), "part.stl")

    def test_long_name_keeps_extension(self) -> None:
        long = "a" * 80 + "_mesh.stl"
        out = truncate_filename(long, max_chars=40)
        self.assertTrue(out.endswith(".stl"))
        self.assertIn("…", out)
        self.assertLess(len(out), len(long))

    def test_confidence_card_subtitle_deferred(self) -> None:
        state = confidence_state_for(ThumbVisualState.PLACEHOLDER, deferred=True)
        self.assertIn("Deferred", state.card_subtitle())


if __name__ == "__main__":
    unittest.main()
