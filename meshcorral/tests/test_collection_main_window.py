"""Real MainWindow collection filter, source, selection, and lifecycle checks."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtWidgets import QApplication

from meshcorral.app.config import ASSET_MODE_3D, ASSET_MODE_IMAGES
from meshcorral.models.file_record import FileRecord
from meshcorral.services.collections.collection_repository import CollectionRepository
from meshcorral.services.collections.collection_service import CollectionService
from meshcorral.tests.test_mode_switch_source_preservation import _SettingsSandbox


class TestCollectionMainWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.sandbox = _SettingsSandbox()
        self.sandbox.__enter__()
        self.addCleanup(self.sandbox.__exit__, None, None, None)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        service = CollectionService(CollectionRepository(self.root / "collections.sqlite"))
        from meshcorral.ui.main_window import MainWindow
        with patch("meshcorral.ui.collections.collection_controller.CollectionService", return_value=service):
            self.window = MainWindow()
        self.addCleanup(self.window.close)
        self.window._asset_mode = ASSET_MODE_3D
        self.window._selected_source_path = str(self.root)
        self.window._current_source = str(self.root)
        self.window._reset_filters()
        self.records = [FileRecord(path=self.root / f"{name}.stl", name=f"{name}.stl", extension=".stl", parent_folder="lib") for name in ("a", "b")]
        self.window._all_records = self.records
        self.window._apply_filters()
        self.controller = self.window._collections
        self.collection = service.create_collection("Print Ready")
        service.add_assets(self.collection.collection_id, [self.records[0].path])
        self.controller._changed()

    def test_collection_filter_preserves_source_mode_without_scan(self):
        with patch.object(self.window, "_run_scan") as scan:
            self.controller.sidebar.combo.setCurrentIndex(1)
            self.assertEqual(self.window._view_records, self.records[:1])
            self.assertEqual(self.window._selected_source_path, str(self.root))
            self.assertEqual(self.window._current_source, str(self.root))
            self.assertEqual(self.window._asset_mode, ASSET_MODE_3D)
            self.controller.sidebar.combo.setCurrentIndex(0)
            self.assertEqual(self.window._view_records, self.records)
            scan.assert_not_called()

    def test_reset_clears_collection_filter(self):
        self.controller.sidebar.combo.setCurrentIndex(1)
        self.window._reset_filters()
        self.assertIsNone(self.controller.sidebar.selected_id())
        self.assertEqual(self.window._view_records, self.records)

    def test_search_updates_after_membership_change(self):
        self.window._search_edit.setText('collection:"Print Ready"')
        self.window._apply_filters()
        self.assertEqual(self.window._view_records, self.records[:1])
        self.controller.service.add_assets(self.collection.collection_id, [self.records[1].path])
        self.controller._changed()
        self.assertEqual(self.window._view_records, self.records)
        self.controller.service.remove_assets(self.collection.collection_id, [self.records[0].path])
        self.controller._changed()
        self.assertEqual(self.window._view_records, self.records[1:])

    def test_empty_state_and_delete_restore_rows(self):
        self.controller.sidebar.combo.setCurrentIndex(1)
        self.controller.service.remove_assets(self.collection.collection_id, [self.records[0].path])
        self.controller._changed()
        self.assertEqual(self.window._view_records, [])
        self.assertIn("This collection is empty", self.window._view_hint_label.text())
        self.controller.service.delete_collection(self.collection.collection_id)
        self.controller._changed()
        self.assertEqual(self.window._view_records, self.records)

    def test_context_menu_and_single_inspector(self):
        self.window._view_stack.setCurrentIndex(0)
        self.window._table.selectRow(0)
        self.window._collections.refresh_selection()
        self.assertIn("Print Ready", self.window._asset_inspector.collection_editor().summary.text())
        actions = {action.text(): action for action in self.window._build_file_context_menu().actions()}
        self.assertTrue(actions["Add to Collection…"].isEnabled())
        self.assertTrue(actions["Remove from Collection…"].isEnabled())

    def test_mode_switch_retains_membership_and_source(self):
        index = self.window._search_mode_combo.findData(ASSET_MODE_IMAGES)
        self.window._search_mode_combo.setCurrentIndex(index)
        self.assertEqual(self.window._selected_source_path, str(self.root))
        self.assertEqual(self.controller.service.get_collection(self.collection.collection_id).member_count, 1)

    def test_shutdown_closes_service_without_new_threads(self):
        from PySide6.QtCore import QThread
        before = self.window.findChildren(QThread)
        self.controller._changed()
        self.assertEqual(self.window.findChildren(QThread), before)
        self.window._shutdown_app(reason="collections test")
        self.assertIsNone(self.controller.service)
        self.window._shutdown_app(reason="collections idempotency")
