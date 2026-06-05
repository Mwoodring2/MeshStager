"""Prime v1.0 Sprint D — workspace layout persistence tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PySide6.QtCore import QSettings

from meshcorral.app.config import ASSET_MODE_3D
from meshcorral.services.settings_service import SettingsService
from meshcorral.ui.layouts.layout_manager import LayoutManager
from meshcorral.ui.layouts.layout_presets import (
    PRESET_REVIEW,
    builtin_preset,
    list_builtin_preset_names,
)
from meshcorral.ui.layouts.workspace_state import WorkspaceState, WORKSPACE_SCHEMA_VERSION


class TestWorkspaceStateSerialization(unittest.TestCase):
    """Round-trip JSON state without widgets."""

    def test_json_round_trip(self) -> None:
        state = WorkspaceState(
            browse_view_mode=SettingsService.VIEW_MODE_GALLERY,
            thumbnail_pixels=160,
            asset_mode=ASSET_MODE_3D,
            search_query="ext:stl",
            main_splitter_sizes=[280, 900, 400],
            table_column_widths={"name": 240, "path": 400},
            hidden_column_keys=["path"],
            inspector_tab_index=2,
        )
        restored = WorkspaceState.from_json(state.to_json())
        self.assertEqual(restored.browse_view_mode, SettingsService.VIEW_MODE_GALLERY)
        self.assertEqual(restored.thumbnail_pixels, 160)
        self.assertEqual(restored.search_query, "ext:stl")
        self.assertEqual(restored.main_splitter_sizes, [280, 900, 400])
        self.assertEqual(restored.table_column_widths.get("name"), 240)
        self.assertEqual(restored.hidden_column_keys, ["path"])
        self.assertEqual(restored.inspector_tab_index, 2)

    def test_invalid_json_returns_defaults(self) -> None:
        restored = WorkspaceState.from_json("{not json")
        self.assertEqual(restored.schema_version, WORKSPACE_SCHEMA_VERSION)
        self.assertEqual(restored.browse_view_mode, "table")


class TestLayoutManagerPersistence(unittest.TestCase):
    """QSettings-backed session and named layouts."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        ini = Path(self._tmp.name) / "layout_test.ini"
        self._settings = QSettings(str(ini), QSettings.Format.IniFormat)
        self._manager = LayoutManager(self._settings)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_session_save_load(self) -> None:
        state = WorkspaceState(search_query="helmet", thumbnail_pixels=96)
        self._manager.save_session(state)
        loaded = self._manager.load_session()
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.search_query, "helmet")
        self.assertEqual(loaded.thumbnail_pixels, 96)

    def test_named_and_builtin_presets(self) -> None:
        custom = WorkspaceState(browse_view_mode=SettingsService.VIEW_MODE_TABLE)
        self.assertTrue(self._manager.save_named("My Desk", custom))
        loaded = self._manager.load_named("My Desk")
        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.browse_view_mode, SettingsService.VIEW_MODE_TABLE)

        review = self._manager.load_named("Review")
        self.assertIsNotNone(review)
        assert review is not None
        self.assertEqual(review.thumbnail_pixels, PRESET_REVIEW.thumbnail_pixels)

    def test_list_builtin_names(self) -> None:
        names = list_builtin_preset_names()
        self.assertIn("Scanning", names)
        self.assertEqual(len(names), 5)

    def test_builtin_preset_copy_is_independent(self) -> None:
        a = builtin_preset("Review")
        b = builtin_preset("Review")
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        assert a is not None
        self.assertEqual(a.thumbnail_pixels, PRESET_REVIEW.thumbnail_pixels)
        self.assertIsNot(a, b)


if __name__ == "__main__":
    unittest.main()
