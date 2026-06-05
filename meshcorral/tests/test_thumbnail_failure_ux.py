"""
Tests for severity-aware thumbnail failure UX helpers.

The Roundup app must:

* Never spawn a modal dialog for background or batch thumbnail failures (large
  scans should not interrupt browsing).
* Surface a concise footer that names the asset and points users to Jobs.
* Preserve the diagnostic modal for single, user-triggered jobs where the user
  is actively waiting on that exact result.

These tests cover the pure helpers that drive that policy.
"""

from __future__ import annotations

import unittest

from meshcorral.app.bridge.job_origin import (
    JobOrigin,
    should_show_failure_modal,
)
from meshcorral.ui.footer_status import format_thumbnail_failure_footer
from meshcorral.ui.main_window import thumbnail_failure_should_show_modal


class TestJobOriginPolicy(unittest.TestCase):
    """:func:`should_show_failure_modal` enforces the severity tiers."""

    def test_manual_single_allows_modal(self) -> None:
        """Single user-triggered runs are the only origin that may raise a modal."""
        self.assertTrue(should_show_failure_modal(JobOrigin.MANUAL_SINGLE))

    def test_manual_batch_suppresses_modal(self) -> None:
        """Batch user actions must rely on footer + Jobs panel (no per-job modals)."""
        self.assertFalse(should_show_failure_modal(JobOrigin.MANUAL_BATCH))

    def test_background_auto_suppresses_modal(self) -> None:
        """Auto-after-scan failures stay non-blocking during gallery browsing."""
        self.assertFalse(should_show_failure_modal(JobOrigin.BACKGROUND_AUTO))


class TestJobOriginCoercion(unittest.TestCase):
    """:meth:`JobOrigin.coerce` should fall back to the safe non-blocking default."""

    def test_passthrough(self) -> None:
        """Passing an existing enum returns the same instance."""
        self.assertIs(JobOrigin.coerce(JobOrigin.MANUAL_SINGLE), JobOrigin.MANUAL_SINGLE)

    def test_string_value(self) -> None:
        """Known string values map to the matching enum member."""
        self.assertEqual(JobOrigin.coerce("manual_batch"), JobOrigin.MANUAL_BATCH)

    def test_unknown_falls_back_to_background(self) -> None:
        """Unknown / ``None`` values default to BACKGROUND_AUTO (safer for users)."""
        self.assertEqual(JobOrigin.coerce(None), JobOrigin.BACKGROUND_AUTO)
        self.assertEqual(JobOrigin.coerce("not-a-real-origin"), JobOrigin.BACKGROUND_AUTO)


class TestThumbnailFailureModalGate(unittest.TestCase):
    """``thumbnail_failure_should_show_modal`` mirrors the policy and handles None."""

    def test_none_origin_treated_as_background(self) -> None:
        """An unknown origin must not raise a modal — protects against regressions."""
        self.assertFalse(thumbnail_failure_should_show_modal(None))

    def test_manual_single_allows_modal(self) -> None:
        """Manual single jobs surface the diagnostic dialog."""
        self.assertTrue(thumbnail_failure_should_show_modal(JobOrigin.MANUAL_SINGLE))

    def test_batch_and_background_suppress(self) -> None:
        """Batch and background jobs always stay silent at the modal level."""
        self.assertFalse(thumbnail_failure_should_show_modal(JobOrigin.MANUAL_BATCH))
        self.assertFalse(thumbnail_failure_should_show_modal(JobOrigin.BACKGROUND_AUTO))


class TestThumbnailFailureFooter(unittest.TestCase):
    """Footer toast stays short; full diagnostics live in Jobs."""

    def test_format_names_file_and_points_to_jobs(self) -> None:
        msg = format_thumbnail_failure_footer(
            source_filename="buck.fbx",
            error_message="no renderable mesh",
        )
        self.assertIn("buck.fbx", msg)
        self.assertIn("Open Jobs", msg)
        self.assertNotIn("no renderable mesh", msg)

    def test_format_handles_blank_reason(self) -> None:
        msg = format_thumbnail_failure_footer(source_filename="x.stl", error_message=None)
        self.assertIn("x.stl", msg)
        self.assertIn("Open Jobs", msg)

    def test_format_ignores_long_reason(self) -> None:
        long_msg = "Traceback:" + ("a" * 500)
        msg = format_thumbnail_failure_footer(
            source_filename="big.fbx",
            error_message=long_msg,
        )
        self.assertNotIn("Traceback", msg)
        self.assertIn("big.fbx", msg)

    def test_format_handles_blank_filename(self) -> None:
        msg = format_thumbnail_failure_footer(source_filename="", error_message="boom")
        self.assertIn("this file", msg)
        self.assertNotIn("boom", msg)


if __name__ == "__main__":
    unittest.main()
