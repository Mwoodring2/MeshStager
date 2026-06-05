"""Tests for legacy Roundup → MeshStager data migration."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QSettings

from meshcorral.app.data_migration import (
    migrate_qsettings_if_needed,
    resolve_user_data_dir,
)


class TestResolveUserDataDir(unittest.TestCase):
    """Filesystem migration copies legacy Roundup data forward once."""

    def test_copies_legacy_tree_when_current_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            legacy = root / "Roundup"
            legacy.mkdir()
            (legacy / "cache").mkdir()
            (legacy / "cache" / "asset_tags.sqlite").write_text("legacy", encoding="utf-8")

            with patch("meshcorral.app.data_migration._local_app_data_root", return_value=root):
                current = resolve_user_data_dir("MeshStager", "Roundup")

            self.assertEqual(current, root / "MeshStager")
            self.assertTrue((current / "cache" / "asset_tags.sqlite").is_file())
            self.assertTrue((legacy / "cache" / "asset_tags.sqlite").is_file())

    def test_merge_copies_missing_files_from_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            current = root / "MeshStager"
            current.mkdir()
            (current / "marker.txt").write_text("new", encoding="utf-8")
            legacy = root / "Roundup"
            legacy.mkdir()
            (legacy / "old.txt").write_text("old", encoding="utf-8")

            with patch("meshcorral.app.data_migration._local_app_data_root", return_value=root):
                resolved = resolve_user_data_dir("MeshStager", "Roundup")

            self.assertEqual(resolved, current)
            self.assertEqual((current / "marker.txt").read_text(encoding="utf-8"), "new")
            self.assertTrue((current / "old.txt").is_file())
            self.assertEqual((current / "old.txt").read_text(encoding="utf-8"), "old")


class TestMigrateQSettings(unittest.TestCase):
    """QSettings scope migration preserves keys without deleting legacy store."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])

    def test_copies_legacy_keys_once(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            QSettings.setDefaultFormat(QSettings.Format.IniFormat)
            QSettings.setPath(
                QSettings.Format.IniFormat,
                QSettings.Scope.UserScope,
                td,
            )

            legacy = QSettings("WoodringToolsTest", "Roundup")
            legacy.clear()
            legacy.setValue("ui/theme_mode", "dark")
            legacy.setValue("scan/search_mode", "3d")
            legacy.sync()

            migrate_qsettings_if_needed(
                org_name="WoodringToolsTest",
                app_name="MeshStager",
                legacy_app_name="Roundup",
            )

            current = QSettings("WoodringToolsTest", "MeshStager")
            self.assertEqual(current.value("ui/theme_mode"), "dark")
            self.assertEqual(current.value("scan/search_mode"), "3d")
            self.assertTrue(current.value("branding/migrated_from_roundup"))

            legacy_after = QSettings("WoodringToolsTest", "Roundup")
            self.assertEqual(legacy_after.value("ui/theme_mode"), "dark")


if __name__ == "__main__":
    unittest.main()
