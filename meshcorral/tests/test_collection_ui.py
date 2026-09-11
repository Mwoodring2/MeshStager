"""Collection controls and browser integration through the production controller."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QWidget

from meshcorral.models.file_record import FileRecord
from meshcorral.services.collections.collection_repository import CollectionRepository
from meshcorral.services.collections.collection_service import CollectionService
from meshcorral.ui.collections.collection_controller import CollectionController
from meshcorral.ui.collections.collection_widgets import CollectionDialog, CollectionEditor
from meshcorral.ui.empty_states import COLLECTION_EMPTY, COLLECTION_UNAVAILABLE
from meshcorral.ui.search.async_filter_engine import AsyncFilterEngine
from meshcorral.ui.search.search_index import SearchIndex
from meshcorral.ui.search.query_parser import parse_query
from meshcorral.ui.responsive_dialog import primary_actions_outside_scroll


class TestCollectionUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.service = CollectionService(CollectionRepository(self.root / "collections.sqlite"))
        self.addCleanup(self.service.close)
        self.window = QWidget()
        self.addCleanup(self.window.close)
        self.editor = CollectionEditor(self.window)
        self.window._asset_inspector = SimpleNamespace(collection_editor=lambda: self.editor)
        self.records = [FileRecord(path=self.root / f"{name}.stl", name=f"{name}.stl", extension=".stl", parent_folder="lib") for name in ("a", "b", "c")]
        self.window._all_records = self.records
        self.window.selected_records = Mock(return_value=self.records[:2])
        self.window._update_status = Mock()
        self.window._apply_filters = Mock()
        self.window._user_tags_for_record = lambda r: ("approved",)
        self.window._async_filter_engine = AsyncFilterEngine(self.window)
        self.controller = CollectionController(self.window, self.service)
        self.controller.wire()
        self.addCleanup(self.controller.close)

    def seed(self, name="Print Ready", paths=None):
        c = self.service.create_collection(name)
        if paths is not None:
            self.service.add_assets(c.collection_id, paths)
        self.controller._changed()
        return c

    def test_sidebar_population_order_and_counts(self):
        self.seed("Zulu")
        c = self.seed("alpha", [self.records[0].path])
        combo = self.controller.sidebar.combo
        self.assertEqual(combo.itemText(0), "All Assets")
        self.assertEqual(combo.itemText(1), "alpha (1)")
        self.assertEqual(combo.itemData(1), c.collection_id)

    def test_select_and_leave_filter(self):
        c = self.seed(paths=[self.records[0].path])
        self.controller.sidebar.combo.setCurrentIndex(1)
        self.assertEqual(list(filter(self.controller.filter_predicate(), self.records)), self.records[:1])
        self.controller.sidebar.combo.setCurrentIndex(0)
        self.assertIsNone(self.controller.filter_predicate())
        self.assertEqual(self.window._all_records, self.records)

    def test_filter_and_search_use_canonical_paths(self):
        self.seed(paths=[self.records[0].path])
        self.controller.sidebar.combo.setCurrentIndex(1)
        alias = FileRecord(path=self.root / "folder" / ".." / "a.stl", name="a.stl", extension=".stl", parent_folder="lib")
        self.assertTrue(self.controller.filter_predicate()(alias))
        self.assertEqual(self.controller.search_provider()(alias), ("print ready",))

    def test_sidebar_empty_state(self):
        self.seed()
        self.controller.sidebar.combo.setCurrentIndex(1)
        self.assertEqual(self.controller.empty_spec().token, COLLECTION_EMPTY)

    def test_unloaded_members_never_fabricate_rows(self):
        self.seed(paths=[self.root / "offline.stl"])
        self.controller.sidebar.combo.setCurrentIndex(1)
        self.assertEqual(list(filter(self.controller.filter_predicate(), self.records)), [])
        self.assertEqual(self.controller.empty_spec().token, COLLECTION_UNAVAILABLE)

    def test_inspector_membership_and_no_membership(self):
        self.seed(paths=[self.records[0].path])
        self.assertIn("Print Ready", self.editor.summary.text())
        self.assertIn("Across selected assets", self.editor.summary.text())
        self.window.selected_records.return_value = self.records[2:]
        self.controller.refresh_selection()
        self.assertEqual(self.editor.summary.text(), "No collections")
        self.assertTrue(self.editor.add_button.isEnabled())
        self.assertFalse(self.editor.remove_button.isEnabled())

    def test_no_selection_disables_actions(self):
        self.window.selected_records.return_value = []
        self.controller.refresh_selection()
        self.assertFalse(self.editor.add_button.isEnabled())
        self.assertFalse(self.editor.remove_button.isEnabled())

    def test_bulk_dialog_add_and_remove(self):
        c = self.seed()
        def accept(dialog):
            dialog._button_box.accepted.emit()
            return dialog.result()
        with patch.object(CollectionDialog, "exec", accept):
            self.controller.add_selected()
            self.assertEqual(self.service.get_collection(c.collection_id).member_count, 2)
            self.controller.remove_selected()
        self.assertEqual(self.service.get_members(c.collection_id), frozenset())

    def test_delete_requires_confirmation_and_cancel_preserves(self):
        c = self.seed(paths=[self.records[0].path])
        self.controller.sidebar.combo.setCurrentIndex(1)
        with patch.object(CollectionDialog, "exec", return_value=QDialog.DialogCode.Rejected):
            self.controller.delete()
        self.assertEqual(self.service.get_collection(c.collection_id).member_count, 1)

    def test_rename_and_delete_refresh_search(self):
        c = self.seed(paths=[self.records[0].path])
        self.service.rename_collection(c.collection_id, "Renamed")
        self.controller._changed()
        index = self.window._async_filter_engine.search_index
        kwargs = {"collections_for": self.controller.search_provider()}
        self.assertEqual(index.filter_records(self.records, parse_query('collection:"Print Ready"'), **kwargs), [])
        self.assertEqual(index.filter_records(self.records, parse_query('collection:Renamed'), **kwargs), self.records[:1])
        self.service.delete_collection(c.collection_id)
        self.controller._changed()
        self.assertEqual(index.filter_records(self.records, parse_query('collection:Renamed'), collections_for=self.controller.search_provider()), [])

    def test_snapshot_survives_edits_and_shutdown(self):
        c = self.seed(paths=[self.records[0].path])
        provider = self.controller.search_provider()
        self.service.remove_assets(c.collection_id, [self.records[0].path])
        self.controller._changed()
        self.controller.close()
        self.assertEqual(provider(self.records[0]), ("print ready",))
        self.assertEqual(self.controller.search_provider()(self.records[0]), ())

    def test_dialog_retains_invalid_input(self):
        dialog = CollectionDialog(self.window, title="New Collection", prompt="Name", name=" ")
        dialog.submit_with(lambda: self.service.create_collection(dialog.input.text()))
        dialog._button_box.accepted.emit()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Rejected)
        self.assertIn("Enter", dialog.error.text())
        self.assertEqual(dialog.input.text(), " ")
        self.assertTrue(primary_actions_outside_scroll(dialog._content_scroll, dialog._button_box))

    def test_startup_storage_failure_does_not_crash(self):
        with patch("meshcorral.ui.collections.collection_controller.CollectionService", side_effect=OSError("unavailable")):
            with self.assertLogs(level="WARNING"):
                controller = CollectionController(self.window)
        self.assertFalse(controller.available)
        self.assertFalse(controller.sidebar.isEnabled())
        controller.close()


class TestCollectionAsyncSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_large_collection_search_delivers_from_snapshot(self):
        engine = AsyncFilterEngine()
        engine._pool = QThreadPool(engine)
        rows = [FileRecord(path=Path(f"C:/lib/{i}.stl"), name=f"{i}.stl", extension=".stl", parent_folder="lib") for i in range(450)]
        wanted = frozenset(r.path for r in rows[:100])
        provider = lambda r: ("Ready",) if r.path in wanted else ()
        received = []
        engine.results_ready.connect(received.append)
        result = engine.request_filter(rows, {"collections_for": provider}, "collection:Ready")
        self.assertTrue(result.pending)
        # Deliver only this engine's queued callback. A nested global event loop
        # would also run deferred startup timers left by unrelated window tests.
        self.assertTrue(engine._pool.waitForDone(5000))
        QCoreApplication.sendPostedEvents(engine, QEvent.Type.MetaCall)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].records, rows[:100])


    def test_overlapping_requests_keep_latest_collection_snapshot(self):
        from threading import Event
        engine = AsyncFilterEngine()
        engine._pool = QThreadPool(engine)
        engine._pool.setMaxThreadCount(2)
        rows = [FileRecord(path=Path(f"C:/lib/{i}.stl"), name=f"{i}.stl", extension=".stl", parent_folder="lib") for i in range(450)]
        entered = Event()
        release = Event()
        def old_provider(record):
            entered.set()
            release.wait(5)
            return ("Old",)
        received = []
        engine.results_ready.connect(received.append)
        try:
            engine.request_filter(rows, {"collections_for": old_provider}, "collection:Old")
            self.assertTrue(entered.wait(5))
            engine.request_filter(rows, {"collections_for": lambda r: ("New",) if r == rows[0] else ()}, "collection:New")
        finally:
            release.set()
            self.assertTrue(engine._pool.waitForDone(5000))
        QCoreApplication.sendPostedEvents(engine, QEvent.Type.MetaCall)
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].records, rows[:1])
