"""Tests for scan timing diagnostics, footer heartbeat copy, and staged model updates."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from meshcorral.models.file_record import FileRecord
from meshcorral.services.scan_cancel import ScanCancelToken
from meshcorral.services.scanner import iter_scan_file_records
from meshcorral.ui.footer_status import (
    format_loading_thumbnails_progress,
    format_scan_footer,
    format_scan_still_scanning_footer,
)
from meshcorral.ui.scan_timing_profiler import ScanTimingSession, timed_scan_item


class TestScanFooterHeartbeatCopy(unittest.TestCase):
    """Locked footer strings for long-running scans."""

    def test_scan_footer_files_found(self) -> None:
        text = format_scan_footer(files_found=340, esc_hint=True)
        self.assertIn("Scanning folder", text)
        self.assertIn("340", text)
        self.assertIn("Press Esc to cancel", text)

    def test_still_scanning_footer(self) -> None:
        text = format_scan_still_scanning_footer(files_found=12)
        self.assertEqual(text, "Still scanning… 12 files found · Press Esc to cancel")

    def test_loading_thumbnails_progress(self) -> None:
        text = format_loading_thumbnails_progress(completed=120, total=340)
        self.assertEqual(text, "Loading thumbnails… 120 / 340")


class TestScanTimingSession(unittest.TestCase):
    def test_finish_is_idempotent(self) -> None:
        session = ScanTimingSession(
            scan_root="C:/photos",
            asset_mode="images",
            include_subfolders=True,
        )
        with mock.patch.object(session, "_append") as append_mock:
            session.finish("complete")
            session.finish("complete")
        self.assertEqual(append_mock.call_count, 1)

    def test_slow_item_logged_only_above_threshold(self) -> None:
        session = ScanTimingSession(
            scan_root="/x",
            asset_mode="3d",
            include_subfolders=False,
        )
        with mock.patch.object(session, "_append") as append_mock:
            session.note_slow_item(kind="file", path="/x/big.psd", elapsed_s=4.9)
            session.note_slow_item(kind="file", path="/x/big.psd", elapsed_s=5.1)
        self.assertEqual(append_mock.call_count, 1)


class TestScanCancelStopsIterator(unittest.TestCase):
    def test_cancel_token_stops_scan_before_first_yield(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for i in range(8):
                (root / f"img_{i}.png").write_bytes(b"x")
            token = ScanCancelToken()
            token.request_cancel()
            rows = list(
                iter_scan_file_records(
                    root,
                    recursive=False,
                    allowed_extensions={".png"},
                    cancel_token=token,
                )
            )
            self.assertTrue(token.is_canceled())
            self.assertEqual(rows, [])


class TestTimedScanItem(unittest.TestCase):
    def test_timed_scan_item_no_session_is_noop(self) -> None:
        with timed_scan_item(None, kind="file", path="/nope"):
            pass


if __name__ == "__main__":
    unittest.main()
