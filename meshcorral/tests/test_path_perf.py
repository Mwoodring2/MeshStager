"""Tests for :mod:`meshcorral.utils.path_perf`."""

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from meshcorral.services.settings_service import SettingsService
from meshcorral.utils.path_perf import (
    AUTO_QUEUE_CAP_LOCAL,
    AUTO_QUEUE_CAP_NETWORK,
    effective_auto_thumbnail_cap,
    is_network_like_path,
    is_prime_perf_scan,
    perf_status_message,
)


class TestPathPerf(unittest.TestCase):
    def test_unc_is_network_like(self) -> None:
        self.assertTrue(is_network_like_path(Path(r"\\server\share\folder")))

    def test_local_drive_not_network_by_default(self) -> None:
        self.assertFalse(is_network_like_path(Path("C:/Users/test")))

    def test_remote_drive_windows(self) -> None:
        with mock.patch(
            "meshcorral.utils.path_perf._windows_drive_is_remote",
            return_value=True,
        ):
            self.assertTrue(is_network_like_path(Path("Z:/project/mesh.obj")))

    def test_effective_cap_network(self) -> None:
        root = Path(r"\\nas\assets")
        cap = effective_auto_thumbnail_cap(
            root,
            500,
            2.0,
            SettingsService.CAP_AUTO_THUMB_100,
            unlimited_cap=SettingsService.CAP_AUTO_THUMB_UNLIMITED,
        )
        self.assertEqual(cap, AUTO_QUEUE_CAP_NETWORK)

    def test_effective_cap_large_local(self) -> None:
        root = Path("D:/big")
        cap = effective_auto_thumbnail_cap(
            root,
            250,
            1.0,
            SettingsService.CAP_AUTO_THUMB_100,
            unlimited_cap=SettingsService.CAP_AUTO_THUMB_UNLIMITED,
        )
        self.assertEqual(cap, min(100, AUTO_QUEUE_CAP_LOCAL))

    def test_effective_cap_small_local_uses_settings(self) -> None:
        root = Path("D:/small")
        cap = effective_auto_thumbnail_cap(
            root,
            10,
            1.0,
            SettingsService.CAP_AUTO_THUMB_25,
            unlimited_cap=SettingsService.CAP_AUTO_THUMB_UNLIMITED,
        )
        self.assertEqual(cap, 25)

    def test_prime_perf_scan_large_count(self) -> None:
        self.assertTrue(is_prime_perf_scan(Path("C:/x"), 200, 1.0))

    def test_perf_status_network(self) -> None:
        msg = perf_status_message(Path(r"\\nas\share"), 300, 3.0)
        self.assertEqual(msg, "Server folder detected: visible thumbnails load first.")

    def test_perf_status_large_local(self) -> None:
        msg = perf_status_message(Path("C:/local"), 300, 3.0)
        self.assertEqual(msg, "Large folder mode: thumbnails load as you browse.")


if __name__ == "__main__":
    unittest.main()
