"""Prime v1.0 RC A5.1 — deferred tone and thumbnail state hierarchy."""

from __future__ import annotations

import unittest

from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.ui.thumbnails.thumbnail_confidence import (
    ThumbConfidenceState,
    confidence_state_for,
)
from meshcorral.ui.thumbnails.thumbnail_style_rules import default_style_rules
from meshcorral.ui.thumbnails.unsupported_visuals import (
    UnsupportedVisualKind,
    resolve_unsupported_visual,
)


class TestA51DeferredTone(unittest.TestCase):
    """Deferred cards are calm and intentional, not failure-like."""

    def test_deferred_card_copy(self) -> None:
        state = confidence_state_for(
            ThumbVisualState.PLACEHOLDER,
            deferred=True,
        )
        self.assertEqual(state.card_title(), "Deferred Preview")
        self.assertIn("Deferred", state.card_subtitle())
        self.assertTrue(state.is_informational())
        self.assertFalse(state.is_failure_family())

    def test_deferred_identity_not_failed(self) -> None:
        identity = resolve_unsupported_visual(".stl", deferred=True)
        self.assertEqual(identity.kind, UnsupportedVisualKind.DEFERRED)
        self.assertEqual(identity.title, "Defer")
        failed = resolve_unsupported_visual(
            ".stl",
            health=ThumbHealth.FAILED_THUMBNAIL,
            visual=ThumbVisualState.FAILED,
        )
        self.assertNotEqual(identity.base_rgb, failed.base_rgb)

    def test_deferred_lower_alpha_than_failure(self) -> None:
        rules = default_style_rules()
        deferred_a = rules.card_background_alpha_for(ThumbConfidenceState.DEFERRED)
        failed_a = rules.card_background_alpha_for(ThumbConfidenceState.FAILED)
        self.assertLess(deferred_a, failed_a)


class TestA51StateHierarchy(unittest.TestCase):
    """Unsupported, failed, corrupt, and timeout are visually distinct."""

    def test_unsupported_not_corrupt(self) -> None:
        unsupported = confidence_state_for(
            ThumbVisualState.UNSUPPORTED,
            health=ThumbHealth.UNSUPPORTED,
        )
        corrupt = confidence_state_for(ThumbVisualState.FAILED)
        self.assertEqual(unsupported, ThumbConfidenceState.UNSUPPORTED)
        self.assertEqual(corrupt, ThumbConfidenceState.CORRUPT)
        self.assertNotEqual(unsupported, corrupt)

    def test_failed_not_corrupt(self) -> None:
        failed = confidence_state_for(
            ThumbVisualState.FAILED,
            health=ThumbHealth.FAILED_THUMBNAIL,
        )
        corrupt = confidence_state_for(ThumbVisualState.FAILED)
        self.assertEqual(failed, ThumbConfidenceState.FAILED)
        self.assertEqual(corrupt, ThumbConfidenceState.CORRUPT)

    def test_timeout_not_generic_failed(self) -> None:
        timeout = confidence_state_for(
            ThumbVisualState.FAILED,
            health=ThumbHealth.FAILED_THUMBNAIL,
            bridge_error_message="Worker timed out after 120s",
        )
        failed = confidence_state_for(
            ThumbVisualState.FAILED,
            health=ThumbHealth.FAILED_THUMBNAIL,
            bridge_error_message="Unknown blender error",
        )
        self.assertEqual(timeout, ThumbConfidenceState.TIMEOUT)
        self.assertEqual(failed, ThumbConfidenceState.FAILED)
        self.assertTrue(timeout.is_recoverable_warning())
        self.assertFalse(timeout.is_failure_family())

    def test_timeout_visual_identity(self) -> None:
        identity = resolve_unsupported_visual(
            ".stl",
            health=ThumbHealth.FAILED_THUMBNAIL,
            visual=ThumbVisualState.FAILED,
            bridge_error_message="timed out",
        )
        self.assertEqual(identity.kind, UnsupportedVisualKind.TIMEOUT)
        failed = resolve_unsupported_visual(
            ".stl",
            health=ThumbHealth.FAILED_THUMBNAIL,
            visual=ThumbVisualState.FAILED,
            bridge_error_message="export failed",
        )
        self.assertEqual(failed.kind, UnsupportedVisualKind.FAILED)


if __name__ == "__main__":
    unittest.main()
