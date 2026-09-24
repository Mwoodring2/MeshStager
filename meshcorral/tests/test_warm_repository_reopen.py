"""Complete source catalog safety and worker ordering regressions."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from meshcorral.models.file_record import FileRecord
from meshcorral.services.metadata_cache import MetadataCache
from meshcorral.services.scan_cache_diagnostics import ScanCacheContext
from meshcorral.services.scan_cancel import ScanCancelToken
from meshcorral.ui.scan_runner import FolderScanRunner


class TestWarmRepository(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cache = MetadataCache(self.root / "metadata.sqlite")
        self.addCleanup(self.cache.close)
        self.ext = {".stl"}

    def record(self, name, size=10, mtime=1.0):
        p = self.root / name
        return FileRecord(p, p.name, ".stl", p.parent.name, size, mtime)

    def publish(self, records):
        return self.cache.complete_source_snapshot(self.root, True, self.ext, records)

    def read(self):
        return self.cache.get_records_for_source_root(self.root, True, self.ext)

    def run_worker(self, token=None, ready=None):
        runner = FolderScanRunner()
        events = []
        runner.catalog_ready.connect(lambda cat: events.append(("cached", cat)))
        runner.catalog_reconciled.connect(lambda rows: events.append(("verified", rows)))
        runner.batch_ready.connect(lambda rows: events.append(("batch", rows)))
        runner.scan_finished.connect(lambda *args: events.append(("finished", args)))
        runner.scan_failed.connect(lambda *args: events.append(("failed", args)))
        runner.scan_canceled.connect(lambda *args: events.append(("canceled", args)))
        if ready:
            runner.catalog_ready.connect(ready)
        runner.execute_scan(str(self.root), True, self.ext, False,
                            ScanCacheContext(metadata_cache=self.cache), token)
        return events

    def test_complete_snapshot_and_matching_parameters(self):
        self.assertIsNone(self.read())
        self.publish([self.record("b.stl"), self.record("A.stl")])
        self.assertEqual([r.name for r in self.read().records], ["A.stl", "b.stl"])
        self.assertIsNone(self.cache.get_records_for_source_root(self.root, False, self.ext))
        self.assertIsNone(self.cache.get_records_for_source_root(self.root, True, {".obj"}))
        self.assertIsNone(self.cache.get_records_for_source_root(self.root / "other", True, self.ext))

    def test_10k_batch_read_without_stat_or_per_asset_get(self):
        self.publish([self.record(f"{i:05}.stl") for i in range(10000)])
        with patch.object(Path, "stat", side_effect=AssertionError("stat")), patch.object(self.cache, "get", side_effect=AssertionError("per-row get")):
            result = self.read()
        self.assertEqual(len(result.records), 10000)
        self.assertEqual(result.records[0].metadata_source, "cache")
        self.assertEqual(result.records[-1].name, "09999.stl")

    def test_transaction_cancel_retains_previous_snapshot(self):
        self.publish([self.record("old.stl")])
        calls = iter([False, True])
        self.assertFalse(self.cache.complete_source_snapshot(self.root, True, self.ext,
                         [self.record("new.stl")], canceled=lambda: next(calls)))
        self.assertEqual([r.name for r in self.read().records], ["old.stl"])

    def test_success_publishes_and_reconciles_add_change_remove_no_duplicates(self):
        a = self.root / "unchanged.stl"
        a.write_bytes(b"a")
        old = FileRecord.from_path(a)
        self.publish([old, self.record("removed.stl"), self.record("changed.stl")])
        (self.root / "changed.stl").write_bytes(b"changed contents")
        (self.root / "new.stl").write_bytes(b"new")
        events = self.run_worker()
        self.assertEqual([e[0] for e in events], ["cached", "verified", "finished"])
        cached = {r.name: r for r in events[0][1].records}
        verified = {r.name: r for r in events[1][1]}
        self.assertEqual(set(verified), {"unchanged.stl", "changed.stl", "new.stl"})
        self.assertEqual(len(events[1][1]), 3)
        self.assertIs(verified["unchanged.stl"], cached["unchanged.stl"])
        self.assertEqual(verified["changed.stl"].size_bytes, 16)
        self.assertFalse(self.cache.get(self.root / "removed.stl").file_exists)
        self.assertEqual(len(self.read().records), 3)

    def test_cached_signal_precedes_any_filesystem_validation(self):
        self.publish([self.record("old.stl")])
        shown = []
        def validate(*args):
            self.assertTrue(shown)
            raise ValueError("offline")
        with patch("meshcorral.ui.scan_runner.require_existing_directory", side_effect=validate):
            events = self.run_worker(ready=lambda cat: shown.append(cat))
        self.assertEqual([e[0] for e in events], ["cached", "failed"])
        self.assertEqual(len(self.read().records), 1)

    def test_cancel_during_verification_retains_snapshot(self):
        self.publish([self.record("old.stl")])
        token = ScanCancelToken()
        def walk(*args, **kwargs):
            yield self.record("partial.stl")
            token.request_cancel()
        with patch("meshcorral.ui.scan_runner.iter_scan_file_records", side_effect=walk):
            events = self.run_worker(token)
        self.assertEqual([e[0] for e in events], ["cached", "canceled"])
        self.assertEqual(self.read().records[0].name, "old.stl")

    def test_failed_partial_traversal_retains_snapshot(self):
        self.publish([self.record("old.stl")])
        def walk(*args, **kwargs):
            yield self.record("partial.stl")
            raise OSError("network disconnected")
        with patch("meshcorral.ui.scan_runner.iter_scan_file_records", side_effect=walk), patch("meshcorral.ui.scan_runner.log"):
            events = self.run_worker()
        self.assertEqual(events[-1][0], "failed")
        self.assertEqual(self.read().records[0].name, "old.stl")

    def test_first_failed_scan_never_publishes(self):
        with patch("meshcorral.ui.scan_runner.require_existing_directory", side_effect=ValueError("offline")):
            self.run_worker()
        self.assertIsNone(self.read())

    def test_first_success_and_empty_success_publish(self):
        self.run_worker()
        self.assertEqual(self.read().records, [])
        (self.root / "new.stl").write_bytes(b"new")
        self.run_worker()
        self.assertEqual(self.read().records[0].name, "new.stl")

    def test_hints_preserved_unchanged_cleared_changed(self):
        rec = self.record("asset.stl")
        self.publish([rec])
        self.cache.upsert_from_file_record(rec, thumb_status="ready", thumb_path="preview.png")
        self.publish([rec])
        self.assertEqual(self.read().thumbnail_hints, [(str(rec.path), "preview.png")])
        self.publish([self.record("asset.stl", size=20)])
        self.assertEqual(self.read().thumbnail_hints, [])

    def test_strict_traversal_reports_inaccessible_directory(self):
        from meshcorral.services.scanner import iter_scan_file_records
        def walk(*args, **kwargs):
            kwargs["onerror"](PermissionError("inaccessible child"))
            return iter(())
        with patch("meshcorral.services.scanner.os.walk", side_effect=walk):
            with self.assertRaises(PermissionError):
                list(iter_scan_file_records(self.root, strict_errors=True))

    def test_overlapping_source_does_not_change_membership(self):
        self.publish([self.record("a.stl")])
        self.cache.complete_source_snapshot(self.root.parent, True, self.ext,
                                           [self.record("a.stl"), self.record("b.stl")])
        self.assertEqual([r.name for r in self.read().records], ["a.stl"])


class TestWarmRepositoryUI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_browsable_before_verification_finishes_on_worker(self):
        import threading
        import time
        from meshcorral.app.config import supported_extensions_for_asset_mode
        from meshcorral.tests.test_source_browse_scan_buttons import _SettingsSandbox
        from meshcorral.ui.main_window import MainWindow
        from PySide6.QtCore import QThread
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            root = Path(td)
            cache = MetadataCache(root / "metadata.sqlite")
            from PySide6.QtCore import QSettings
            from meshcorral.services.settings_service import SettingsService
            # QCoreApplication's settings sandbox does not isolate SettingsService,
            # which explicitly uses the real application's organization/name.
            class IsolatedSettingsService(SettingsService):
                def __init__(self):
                    super().__init__(QSettings())
            self.addCleanup(cache.close)
            for target, replacement in (
                ("meshcorral.ui.main_window.SettingsService", IsolatedSettingsService),
                ("meshcorral.ui.main_window.MainWindow._maybe_show_startup_native_degraded_hint", Mock()),
                ("meshcorral.ui.main_window.MainWindow._maybe_autotrim_bridge_storage_at_startup", Mock()),
            ):
                patcher = patch(target, replacement)
                patcher.start()
                self.addCleanup(patcher.stop)
            window = MainWindow()
            self.app.processEvents()  # Drain construction work before the scan assertion.
            window._ensure_metadata_cache = lambda: cache
            window._schedule_auto_thumbnails_after_scan = Mock()
            window._schedule_viewport_thumb_pass = Mock()
            window._deferred_refresh_thumb_index_after_scan = Mock()
            window._schedule_metadata_enrichment_after_scan = Mock()
            window._asset_mode = "3d"
            window._reset_filters()
            released = threading.Event()
            worker_threads = []
            rec = FileRecord(root / "cached.stl", "cached.stl", ".stl", root.name, 1, 1.0)
            cache.complete_source_snapshot(root, window._include_subfolders_checkbox.isChecked(),
                       supported_extensions_for_asset_mode(window._asset_mode), [rec])
            def walk(*args, **kwargs):
                worker_threads.append(QThread.currentThread())
                # Verification must remain blocked until the UI assertions release it.
                # A timeout can expire while the full suite drains unrelated Qt events.
                released.wait()
                yield rec
            try:
                with patch("meshcorral.ui.scan_runner.iter_scan_file_records", side_effect=walk):
                    window._selected_source_path = td
                    window._reopen_completed_source()
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline and window._model.rowCount() != 1:
                        self.app.processEvents()
                        time.sleep(.005)
                    self.assertTrue(window._warm_catalog_active, f"scanning={window._is_scanning}, workers={len(worker_threads)}, rows={window._model.rowCount()}")
                    self.assertTrue(window._is_scanning)
                    self.assertEqual(window._model.rowCount(), 1)
                    self.assertEqual(window._gallery_model.rowCount(), 1)
                    self.assertIn("Verifying", window._scan_status_while_walking(1))
                    released.set()
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline and window._is_scanning:
                        self.app.processEvents()
                        time.sleep(.005)
                    self.assertFalse(window._is_scanning)
                    self.assertNotEqual(worker_threads[0], self.app.thread())
                    self.assertEqual(len(window._all_records), 1)
                    window._deferred_refresh_thumb_index_after_scan.assert_not_called()
                    window._schedule_metadata_enrichment_after_scan.assert_not_called()
            finally:
                released.set()
                window.close()
                self.app.processEvents()
                cache.close()

    def test_changed_source_evicts_only_its_index_entry(self):
        from meshcorral.app.bridge.thumb_index import BlenderThumbPathIndex, _norm_path_key
        index = BlenderThumbPathIndex()
        a, b = Path("a.stl"), Path("b.stl")
        index._source_to_thumb = {_norm_path_key(a): Path("a.png"), _norm_path_key(b): Path("b.png")}
        index.forget_source(a)
        self.assertEqual(index._source_to_thumb, {_norm_path_key(b): Path("b.png")})

    def test_warm_restore_skips_startup_thumbnail_directory_walk(self):
        from PySide6.QtCore import QSettings
        from meshcorral.tests.test_source_browse_scan_buttons import _SettingsSandbox
        from meshcorral.ui.main_window import MainWindow
        with _SettingsSandbox(), tempfile.TemporaryDirectory() as td:
            QSettings().setValue("paths/last_scan_folder", td)
            cache = Mock()
            cache.has_complete_source.return_value = True
            with patch.object(MainWindow, "_ensure_metadata_cache", return_value=cache), patch("meshcorral.ui.thumbnail_controller.ThumbnailViewController.refresh_index") as refresh:
                window = MainWindow()
                try:
                    refresh.assert_not_called()
                    cache.has_complete_source.assert_called_once()
                finally:
                    window.close()
