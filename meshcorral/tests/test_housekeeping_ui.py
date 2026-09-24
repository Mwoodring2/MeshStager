"""Existing browser composition and owned-worker safety for Housekeeping."""
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from PySide6.QtCore import QSettings, QThread, Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest, QSignalSpy
from meshcorral.ui.housekeeping.widgets import HousekeepingSidebar
from meshcorral.services.housekeeping.models import LABELS
from meshcorral.models.file_record import FileRecord
from meshcorral.services.housekeeping.models import Snapshot, finding, path_key, AnalysisCanceled
from meshcorral.services.housekeeping.repository import HousekeepingRepository
from meshcorral.services.housekeeping.service import HousekeepingService
from meshcorral.services.scan_cancel import ScanCancelToken
from meshcorral.ui.housekeeping.controller import HousekeepingWorker
from meshcorral.ui.search.async_filter_engine import compute_filtered_records
from meshcorral.ui.search.search_index import SearchIndex
from meshcorral.services.favorites.favorite_filter import FAVORITE_FILTER_ONLY
from meshcorral.tests.test_source_browse_scan_buttons import _SettingsSandbox
from meshcorral.services.settings_service import SettingsService

class TestHousekeepingFilters(unittest.TestCase):
    def test_composes_with_search_tags_favorites_and_collections(self):
        records = [FileRecord(Path(f"C:/assets/{n}.stl"), f"{n}.stl", ".stl", "assets", 10, 1.0) for n in ("head", "head_copy", "foot")]
        result = compute_filtered_records(records, query_text='head tag:approved collection:"Print"', search_index=SearchIndex(),
            asset_mode="3d", housekeeping_filter=lambda r: r in records[:2],
            user_tags_for=lambda r: ("approved",), collections_for=lambda r: ("print",),
            collection_filter=lambda r: r in records[:2], favorite_filter=FAVORITE_FILTER_ONLY,
            is_favorite_for=lambda r: r == records[1])
        self.assertEqual(result, [records[1]])

class TestHousekeepingUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        sandbox = _SettingsSandbox()
        sandbox.__enter__()
        self.addCleanup(sandbox.__exit__, None, None, None)
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.service = HousekeepingService(HousekeepingRepository(self.root / "hk.sqlite"))
        class IsolatedSettings(SettingsService):
            def __init__(self):
                super().__init__(QSettings())
        for target, value in (
            ("meshcorral.ui.main_window.SettingsService", IsolatedSettings),
            ("meshcorral.ui.main_window.MainWindow._maybe_show_startup_native_degraded_hint", Mock()),
            ("meshcorral.ui.main_window.MainWindow._maybe_autotrim_bridge_storage_at_startup", Mock()),
            ("meshcorral.ui.housekeeping.controller.HousekeepingService", Mock(return_value=self.service)),
        ):
            p = patch(target, value)
            p.start()
            self.addCleanup(p.stop)
        from meshcorral.ui.main_window import MainWindow
        self.window = MainWindow()
        self.addCleanup(self.window.close)
        self.app.processEvents()
        self.ctrl = self.window._housekeeping
        self.records = []
        for name in ("head", "head_copy", "foot"):
            path = self.root / (name + ".glb")
            path.write_bytes(b"mesh" if name != "foot" else b"other")
            self.records.append(FileRecord.from_path(path))
        self.window._all_records = list(self.records)
        self.window._current_source = str(self.root)
        self.window._selected_source_path = str(self.root)
        self.ctrl.source = path_key(self.root)
        self.ctrl.snapshot = Snapshot("test", tuple(finding(r, "exact_duplicate", {"message": "identical", "matching_files": 2}, group="group1") for r in self.records[:2]))
        self.window._reset_filters()
        self.ctrl.refresh_selection()

    def pump(self, predicate):
        deadline = time.monotonic() + 30
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(predicate())

    def test_category_filters_same_browser_without_scan_or_mode_change(self):
        source, mode = self.window._current_source, self.window._view_stack.currentIndex()
        with patch.object(self.window, "_run_scan") as scan:
            sidebar = self.ctrl.sidebar
            sidebar.categories.show()
            item = sidebar.categories.topLevelItem(2)
            QTest.mouseClick(sidebar.categories.viewport(), Qt.MouseButton.LeftButton,
                             pos=sidebar.categories.visualItemRect(item).center())
            self.assertEqual(self.window._view_records, self.records[:2])
            scan.assert_not_called()
        self.assertEqual(self.window._current_source, source)
        self.assertEqual(self.window._view_stack.currentIndex(), mode)
        self.assertEqual(self.window._model.rowCount(), 2)
        self.assertEqual(self.window._gallery_model.rowCount(), 2)

    def test_counts_are_unique_assets(self):
        self.assertEqual(self.ctrl._counts["exact_duplicate"], 2)
        self.assertEqual(self.ctrl._counts["*"], 2)

    def test_category_preserves_search(self):
        self.window._search_edit.setText("head_copy")
        self.ctrl.sidebar.select("exact_duplicate")
        self.assertEqual(self.window._search_edit.text(), "head_copy")
        self.assertEqual(self.window._view_records, [self.records[1]])

    def test_duplicate_group_uses_existing_browser(self):
        self.ctrl.editor.set_findings([self.ctrl.snapshot.findings[0]])
        with patch.object(self.window, "_run_scan") as scan:
            self.ctrl.view_group()
            scan.assert_not_called()
        self.assertEqual(self.ctrl.sidebar.current_data(), "group:group1")
        self.assertEqual(self.window._view_records, self.records[:2])

    def test_inspector_plain_text_and_ignore_action(self):
        self.service.repository.publish(self.root, self.ctrl.snapshot.findings, 3)
        f = self.ctrl.snapshot.findings[0]
        self.ctrl.editor.set_findings([f])
        self.assertIn("Group", self.ctrl.editor.details.text())
        self.ctrl.ignore()
        self.pump(lambda: self.ctrl.worker is None)
        self.assertTrue(next(x for x in self.ctrl.snapshot.findings if x.finding_id == f.finding_id).ignored)

    def test_analysis_runs_off_ui_thread_and_completes(self):
        original = self.service.analyze
        threads = []
        def run(*args, **kwargs):
            threads.append(QThread.currentThread())
            return original(*args, **kwargs)
        with patch.object(self.service, "analyze", side_effect=run):
            self.ctrl.analyze()
            self.pump(lambda: self.ctrl.worker is None)
        self.assertNotEqual(threads[0], self.app.thread())
        self.assertEqual(sum(f.kind == "exact_duplicate" for f in self.ctrl.snapshot.findings), 2)

    def test_explicit_cancel_retains_previous_snapshot(self):
        entered = threading.Event()
        def run(*args, canceled, **kwargs):
            entered.set()
            while not canceled():
                time.sleep(.001)
            raise AnalysisCanceled()
        before = self.ctrl.snapshot
        with patch.object(self.service, "analyze", side_effect=run):
            self.assertFalse(self.ctrl.sidebar.cancel_button.isEnabled())
            self.ctrl.analyze()
            self.pump(entered.is_set)
            self.assertTrue(self.ctrl.sidebar.cancel_button.isEnabled())
            self.ctrl.sidebar.cancel_button.click()
            self.pump(lambda: self.ctrl.worker is None)
            self.assertFalse(self.ctrl.sidebar.cancel_button.isEnabled())
        self.assertEqual(self.ctrl.snapshot, before)

    def test_normal_scan_disables_analysis(self):
        self.window._is_scanning = True
        try:
            self.ctrl.analyze()
            self.assertIsNone(self.ctrl.worker)
        finally:
            self.window._is_scanning = False

    def test_shutdown_cancels_and_joins_worker(self):
        entered = threading.Event()
        def run(*args, canceled, **kwargs):
            entered.set()
            while not canceled():
                time.sleep(.001)
            raise AnalysisCanceled()
        with patch.object(self.service, "analyze", side_effect=run):
            self.ctrl.analyze()
            self.pump(entered.is_set)
            worker = self.ctrl.worker
            self.ctrl.close()
            self.assertFalse(worker.isRunning())
            self.ctrl.close()
            self.ctrl.analyze()
            self.assertTrue(self.ctrl.closed)

    def test_late_result_after_close_does_not_update_window(self):
        self.ctrl.close()
        with patch.object(self.window, "_apply_filters") as apply:
            self.ctrl._result({"source": self.ctrl.source, "operation": "load", "snapshot": Snapshot()})
            self.ctrl._stage("late")
            apply.assert_not_called()

    def test_analyze_button_dispatches_without_signal_argument_error(self):
        with patch.object(self.service, "analyze", return_value=(self.ctrl.snapshot, None)) as analyze:
            self.ctrl.sidebar.analyze_button.click()
            self.pump(lambda: self.ctrl.worker is None)
            analyze.assert_called_once()

    def test_in_place_catalog_growth_refreshes_counts(self):
        self.window._all_records = []
        self.ctrl.refresh_selection()
        self.window._all_records.extend(self.records)
        self.ctrl.refresh_selection()
        self.assertEqual(self.ctrl._counts["exact_duplicate"], 2)

    def test_left_sections_scroll_instead_of_compressing_controls(self):
        self.window.resize(1200, 800)
        self.window.ensurePolished()
        self.window.grab()
        scroll = self.window._left_content_scroll
        self.assertGreaterEqual(scroll.widget().height(), scroll.widget().minimumSizeHint().height())
        self.assertLessEqual(scroll.widget().width(), scroll.viewport().width())
        self.assertGreaterEqual(self.ctrl.sidebar.analyze_button.height(), self.ctrl.sidebar.analyze_button.minimumSizeHint().height())
        self.assertGreaterEqual(self.ctrl.sidebar.categories.height(), self.ctrl.sidebar.categories.minimumSizeHint().height())

    def test_worker_emits_safely_after_qobject_deletion(self):
        import shiboken6
        worker = HousekeepingWorker(self.service, ("load", str(self.root), None), ScanCancelToken())
        signal = worker.result
        shiboken6.delete(worker)
        worker._emit(signal, {})


class TestHousekeepingSidebar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.sidebar = HousekeepingSidebar()
        self.addCleanup(self.sidebar.close)
        self.addCleanup(self.sidebar.deleteLater)

    def test_labels_counts_and_zero_count_rows_remain_available(self):
        self.sidebar.populate({"*": 1234, "exact_duplicate": 12})
        tree = self.sidebar.categories
        self.assertEqual([tree.topLevelItem(i).text(0) for i in range(1, 10)],
                         ["All Findings", *LABELS.values()])
        self.assertEqual(tree.topLevelItem(1).text(1), "1,234")
        self.assertEqual(tree.topLevelItem(2).text(1), "12")
        zero = tree.topLevelItem(3)
        self.assertEqual(zero.text(1), "0")
        self.assertTrue(zero.flags() & Qt.ItemFlag.ItemIsEnabled)
        self.assertTrue(zero.textAlignment(1) & Qt.AlignmentFlag.AlignRight)

    def test_refresh_preserves_selection_without_emitting_and_reset_clears(self):
        self.sidebar.select("naming")
        spy = QSignalSpy(self.sidebar.changed)
        self.sidebar.populate({"naming": 7})
        self.assertEqual(self.sidebar.current_data(), "naming")
        self.assertEqual(spy.count(), 0)
        self.sidebar.reset()
        self.assertIsNone(self.sidebar.current_data())
        self.assertEqual(spy.count(), 0)

    def test_rows_fit_light_and_dark_themes_without_internal_scrolling(self):
        from meshcorral.ui.theme import build_app_stylesheet
        for mode in ("light", "dark"):
            with self.subTest(mode=mode):
                self.sidebar.setStyleSheet(build_app_stylesheet(mode))
                self.sidebar.ensurePolished()
                self.sidebar.resize(220, self.sidebar.sizeHint().height())
                self.sidebar.grab()
                tree = self.sidebar.categories
                last = tree.topLevelItem(tree.topLevelItemCount() - 1)
                self.assertLessEqual(tree.visualItemRect(last).bottom(), tree.viewport().height())
                self.assertEqual(tree.verticalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                self.assertEqual(tree.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                self.assertFalse(self.sidebar.cancel_button.isEnabled())
                self.assertLess(tree.geometry().bottom(), self.sidebar.analyze_button.geometry().top())
