"""Prime v1.0 — thumbnail style, placeholders, profiles, and confidence states."""

from __future__ import annotations

import unittest

from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.ui.thumbnails.thumbnail_confidence import (
    ThumbConfidenceState,
    confidence_state_for,
)
from meshcorral.ui.thumbnails.thumbnail_style_rules import default_style_rules
from meshcorral.ui.thumbnails.thumb_quality_profiles import (
    ThumbProfileName,
    default_quality_profile,
    profile_for_name,
)
from meshcorral.ui.thumbnails.unsupported_visuals import (
    UnsupportedVisualKind,
    classify_extension,
    resolve_unsupported_visual,
)


class TestUnsupportedVisuals(unittest.TestCase):
    def test_per_format_identity(self) -> None:
        self.assertEqual(classify_extension(".ztl"), UnsupportedVisualKind.ZTL)
        self.assertEqual(classify_extension(".ma"), UnsupportedVisualKind.MA)
        self.assertEqual(classify_extension(".psd"), UnsupportedVisualKind.PSD)
        self.assertEqual(classify_extension(".exr"), UnsupportedVisualKind.EXR)
        self.assertEqual(classify_extension(".zip"), UnsupportedVisualKind.ZIP)

    def test_deferred_and_failed_vs_corrupt(self) -> None:
        deferred = resolve_unsupported_visual(".stl", deferred=True)
        self.assertEqual(deferred.kind, UnsupportedVisualKind.DEFERRED)
        self.assertEqual(deferred.title, "Defer")
        failed_job = resolve_unsupported_visual(
            ".stl",
            health=ThumbHealth.FAILED_THUMBNAIL,
            visual=ThumbVisualState.FAILED,
        )
        self.assertEqual(failed_job.kind, UnsupportedVisualKind.FAILED)
        corrupt_decode = resolve_unsupported_visual(
            ".stl",
            health=ThumbHealth.MISSING_THUMBNAIL,
            visual=ThumbVisualState.FAILED,
        )
        self.assertEqual(corrupt_decode.kind, UnsupportedVisualKind.CORRUPT)

    def test_large_file_identity(self) -> None:
        large = resolve_unsupported_visual(
            ".fbx",
            size_bytes=600 * 1024 * 1024,
        )
        self.assertEqual(large.kind, UnsupportedVisualKind.LARGE_FILE)


class TestThumbnailStyleRules(unittest.TestCase):
    def test_health_tint_failed(self) -> None:
        rules = default_style_rules()
        rgb = rules.health_tint_rgb((72, 108, 96), health=ThumbHealth.FAILED_THUMBNAIL)
        self.assertGreater(rgb[0], 72)

    def test_scan_density_padding(self) -> None:
        rules = default_style_rules()
        tight = rules.content_padding_px(record_count=5000)
        normal = rules.content_padding_px(record_count=100)
        self.assertLess(tight, normal)


class TestQualityProfiles(unittest.TestCase):
    def test_default_is_standard(self) -> None:
        profile = default_quality_profile()
        self.assertEqual(profile.name, ThumbProfileName.STANDARD)
        self.assertGreater(profile.inspector_preview_px, profile.gallery_px)

    def test_profile_for_name_fallback(self) -> None:
        unknown = profile_for_name("not-a-profile")
        self.assertEqual(unknown.name, ThumbProfileName.STANDARD)
        high = profile_for_name("high")
        self.assertEqual(high.name, ThumbProfileName.HIGH)


class TestConfidenceStates(unittest.TestCase):
    def test_generating_over_queued(self) -> None:
        state = confidence_state_for(
            ThumbVisualState.QUEUED,
            generating=True,
        )
        self.assertEqual(state, ThumbConfidenceState.GENERATING)

    def test_deferred_placeholder(self) -> None:
        state = confidence_state_for(
            ThumbVisualState.PLACEHOLDER,
            deferred=True,
        )
        self.assertEqual(state, ThumbConfidenceState.DEFERRED)
        self.assertIn("Deferred", state.card_subtitle())
        self.assertFalse(state.is_failure_family())

    def test_failed_job_badge_distinct_from_decode_corrupt(self) -> None:
        job_failed = confidence_state_for(
            ThumbVisualState.FAILED,
            health=ThumbHealth.FAILED_THUMBNAIL,
        )
        self.assertEqual(job_failed, ThumbConfidenceState.FAILED)
        decode_corrupt = confidence_state_for(ThumbVisualState.FAILED)
        self.assertEqual(decode_corrupt, ThumbConfidenceState.CORRUPT)

    def test_unsupported_health(self) -> None:
        state = confidence_state_for(
            ThumbVisualState.UNSUPPORTED,
            health=ThumbHealth.UNSUPPORTED,
        )
        self.assertEqual(state, ThumbConfidenceState.UNSUPPORTED)


if __name__ == "__main__":
    unittest.main()
