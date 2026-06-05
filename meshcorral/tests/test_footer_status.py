"""Tests for production footer/status copy (Prime v1.0 RC A3)."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from meshcorral.ui.footer_status import (
    FooterCounts,
    format_app_footer,
    format_counts_strip,
    format_filter_footer,
    format_footer_confidence_counts,
    format_scan_complete_message,
    format_thumbnail_failure_footer,
    format_thumbnail_footer,
    format_verbose_diagnostics,
    prime_mode_hint,
    prime_mode_label,
    status_export_complete,
    status_generating_visible_thumbnails,
    status_layout_saved,
    status_no_matching_results,
    status_scan_canceled,
    status_thumbnails_deferred,
    verbose_footer_enabled,
)


class TestIdleFooter(unittest.TestCase):
    """Default counts strip without Prime or failures."""

    def test_idle_counts_strip(self) -> None:
        line = format_counts_strip(FooterCounts(46, 46, 1))
        self.assertIn("Indexed: 46", line)
        self.assertIn("Visible: 46", line)
        self.assertIn("Selected: 1", line)
        self.assertNotIn("Queue", line)

    def test_idle_app_footer(self) -> None:
        line = format_app_footer(
            workflow="Ready",
            counts=FooterCounts(46, 46, 1),
        )
        self.assertTrue(line.startswith("Ready"))
        self.assertIn("Indexed: 46", line)


class TestGeneratingFooter(unittest.TestCase):
    """Thumbnail activity line."""

    def test_generating_footer(self) -> None:
        line = format_thumbnail_footer(generating=3, queued=8)
        self.assertEqual(line, "Thumbnails: Generating 3 · Queued 8")

    def test_batch_generating_footer(self) -> None:
        line = format_thumbnail_footer(batch_completed=3, batch_total=12)
        self.assertEqual(line, "Thumbnails: Generating 3 of 12")


class TestFailureFooter(unittest.TestCase):
    """Failure hints in counts strip and toast helpers."""

    def test_failure_counts_strip(self) -> None:
        line = format_counts_strip(
            FooterCounts(46, 46, 1),
            failed_thumbnails=3,
        )
        self.assertIn("3 thumbnails failed", line)
        self.assertIn("Open Jobs for details", line)

    def test_thumbnail_failure_toast(self) -> None:
        msg = format_thumbnail_failure_footer(source_filename="part.stl", error_message="x")
        self.assertIn("part.stl", msg)
        self.assertIn("Open Jobs", msg)


class TestFilteredFooter(unittest.TestCase):
    """Search and filter workflow labels."""

    def test_searching_footer(self) -> None:
        workflow, suffix = format_filter_footer(visible=12, indexed=1240, query="ext:stl")
        self.assertEqual(workflow, "Searching…")
        self.assertEqual(suffix, "Query: ext:stl")

    def test_filtered_subset_footer(self) -> None:
        workflow, suffix = format_filter_footer(visible=46, indexed=1240, query="")
        self.assertEqual(workflow, "Filtered")
        self.assertEqual(suffix, "46 visible of 1,240")


class TestPrimeFooters(unittest.TestCase):
    """Prime Local / Server labels and hints."""

    def test_prime_local_footer(self) -> None:
        line = format_counts_strip(
            FooterCounts(1240, 1240, 0),
            prime_mode=prime_mode_label(prime_active=True, network_like=False),
            prime_hint=prime_mode_hint(prime_active=True, network_like=False),
        )
        self.assertIn("Prime Local", line)
        self.assertIn("Using cached previews", line)

    def test_prime_server_footer(self) -> None:
        line = format_counts_strip(
            FooterCounts(1240, 80, 0),
            prime_mode=prime_mode_label(prime_active=True, network_like=True),
            prime_hint=prime_mode_hint(prime_active=True, network_like=True),
        )
        self.assertIn("Prime Server", line)
        self.assertIn("Visible previews load first", line)


class TestVerboseFooter(unittest.TestCase):
    """Developer counters hidden unless env flag is set."""

    def test_verbose_disabled_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ROUNDUP_VERBOSE_FOOTER", None)
            self.assertFalse(verbose_footer_enabled())
        snap = {"cache_hits": 10, "cache_misses": 2}
        verbose = ""
        if verbose_footer_enabled():
            verbose = format_verbose_diagnostics(snap)
        line = format_counts_strip(FooterCounts(1, 1, 0), verbose_diagnostics=verbose)
        self.assertNotIn("cache_hits", line)

    def test_verbose_counters_when_enabled(self) -> None:
        with patch.dict(os.environ, {"ROUNDUP_VERBOSE_FOOTER": "1"}):
            self.assertTrue(verbose_footer_enabled())
        snap = {"cache_hits": 10, "cache_misses": 2}
        verbose = format_verbose_diagnostics(snap)
        self.assertIn("cache_hits=10", verbose)
        line = format_counts_strip(FooterCounts(1, 1, 0), verbose_diagnostics=verbose)
        self.assertIn("cache_hits=10", line)


class TestStatusMessageHelpers(unittest.TestCase):
    """One-shot status toasts stay concise."""

    def test_status_helpers(self) -> None:
        self.assertEqual(status_scan_canceled(), "Scan canceled.")
        self.assertEqual(status_no_matching_results(), "No matching results.")
        self.assertEqual(status_generating_visible_thumbnails(), "Generating visible previews…")
        self.assertEqual(
            status_thumbnails_deferred(),
            "Large files deferred for fast browsing",
        )
        self.assertEqual(status_layout_saved("Work"), "Layout saved: Work")
        self.assertEqual(status_export_complete(), "Export complete.")


class TestLegacyFooterConfidence(unittest.TestCase):
    """Legacy formatter omits queue from the counts strip."""

    def test_queue_ignored_in_strip(self) -> None:
        line = format_footer_confidence_counts(10, 8, 2, 99)
        self.assertIn("Indexed: 10", line)
        self.assertNotIn("Queue", line)


if __name__ == "__main__":
    unittest.main()
