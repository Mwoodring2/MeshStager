"""
Regression tests for Patch 2 footer confidence (Indexed / Visible / Selected).

Blender readiness strings from :func:`describe_blender_readiness` are covered in
``test_blender_locator.py`` (Ready / Not configured / Not found).

Manual GUI checks (Roundup):
1. Before scan: status strip shows Indexed: 0, Visible: 0, Selected: 0;
   Bridge line shows Ready / Not found / Not configured from path discovery only.
2. After scan: Indexed matches the scan total; Visible matches the filtered table row count.
3. Change Name contains or filters: Visible changes; Indexed stays the same until a new scan.
4. Queue several thumbnail jobs: Jobs button shows depth; footer thumbnails line shows Generating/Queued.
5. Settings → set or clear Blender path → Save: footer Bridge line updates without using
   Test Blender (no ``blender --version`` on that path).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from PySide6.QtCore import QSettings

from meshcorral.app.bridge import blender_locator
from meshcorral.app.bridge.blender_locator import describe_blender_readiness
from meshcorral.services.settings_service import SettingsService
from meshcorral.ui.footer_status import format_footer_confidence_counts


class TestFormatFooterConfidenceCounts(unittest.TestCase):
    """Pure formatter used by the main window status strip."""

    def test_before_scan_all_zeros(self) -> None:
        """Unscanned session: file counts without queue depth in the strip."""
        line = format_footer_confidence_counts(0, 0, 0, 0)
        self.assertIn("Indexed: 0", line)
        self.assertIn("Visible: 0", line)
        self.assertIn("Selected: 0", line)
        self.assertNotIn("Queue", line)

    def test_after_scan_indexed_visible_selected(self) -> None:
        """Indexed is full working set; visible is filtered subset; selected is independent."""
        line = format_footer_confidence_counts(100, 12, 3, 0)
        self.assertIn("Indexed: 100", line)
        self.assertIn("Visible: 12", line)
        self.assertIn("Selected: 3", line)

    def test_filter_changes_visible_only_in_formatter(self) -> None:
        """Formatter reflects caller counts: same indexed, smaller visible after filters."""
        before = format_footer_confidence_counts(50, 50, 0, 0)
        after = format_footer_confidence_counts(50, 4, 0, 0)
        self.assertIn("Visible: 50", before)
        self.assertIn("Visible: 4", after)
        self.assertIn("Indexed: 50", after)

    def test_queue_pending_omitted_from_strip(self) -> None:
        """Queue depth is on the thumbnails line, not the counts strip."""
        line = format_footer_confidence_counts(10, 10, 1, 7)
        self.assertNotIn("Queue", line)
        self.assertIn("Indexed: 10", line)

    def test_thousands_separators(self) -> None:
        """Large counts use grouping commas."""
        line = format_footer_confidence_counts(1234, 1200, 5, 0)
        self.assertIn("1,234", line)
        self.assertIn("1,200", line)


class TestDescribeBlenderReadinessLightweight(unittest.TestCase):
    """
    Re-assert readiness mapping stays path-only (no subprocess).

    Detailed cases also live in ``test_blender_locator.TestBlenderLocator``.
    """

    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self._ini_dir = Path(self._td.name)

    def tearDown(self) -> None:
        self._td.cleanup()

    def test_ready_not_configured_not_found(self) -> None:
        """Three labels from settings + locator result only."""
        ini = str(self._ini_dir / "footer_readiness.ini")
        qs = QSettings(ini, QSettings.Format.IniFormat)
        qs.clear()
        svc = SettingsService(qs)
        self.assertEqual(describe_blender_readiness(svc, None), "Not configured")

        svc.set_blender_executable(r"Z:\nonexistent\blender_roundup_test.exe")
        self.assertEqual(describe_blender_readiness(svc, None), "Not found")

        fake = Path(__file__).resolve()
        self.assertEqual(describe_blender_readiness(svc, fake), "Ready")

    def test_describe_blender_readiness_does_not_call_version_subprocess(self) -> None:
        """Readiness must not spawn ``blender --version``."""
        ini = str(self._ini_dir / "footer_no_subprocess.ini")
        qs = QSettings(ini, QSettings.Format.IniFormat)
        qs.clear()
        svc = SettingsService(qs)
        fake_exe = Path(__file__).resolve()
        with patch.object(blender_locator, "_run_version_subprocess", new=MagicMock()) as m:
            describe_blender_readiness(svc, fake_exe)
        m.assert_not_called()


if __name__ == "__main__":
    unittest.main()
