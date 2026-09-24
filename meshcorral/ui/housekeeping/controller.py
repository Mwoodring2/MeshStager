"""One cancellable worker and immutable filters over the existing catalog."""
from __future__ import annotations
import logging
from collections import defaultdict
from PySide6.QtCore import QObject, QThread, Signal, Slot
from meshcorral.services.archive_manifest_cache import DEFAULT_DB_PATH as ARCHIVE_DB
from meshcorral.services.scan_cancel import ScanCancelToken
from meshcorral.services.housekeeping.models import Snapshot, AnalysisCanceled, path_key
from meshcorral.services.housekeeping.service import HousekeepingService
from .widgets import HousekeepingSidebar

log = logging.getLogger(__name__)
# Keep a blocked read's QThread alive after bounded UI shutdown. Never terminate I/O.
_DRAINING = set()

class HousekeepingWorker(QThread):
    result = Signal(object)
    stage = Signal(str)
    def __init__(self, service, request, token):
        super().__init__()
        self.service, self.request, self.token = service, request, token

    def _emit(self, signal, value):
        try:
            signal.emit(value)
        except RuntimeError:
            pass  # receiver/source already torn down

    def run(self):
        operation, source, payload = self.request
        outcome = {"source": source, "operation": operation}
        try:
            if operation == "analyze":
                snapshot, stats = self.service.analyze(payload, source, canceled=self.token.is_canceled,
                    progress=lambda s: self._emit(self.stage, s), archive_db=ARCHIVE_DB)
                outcome.update(snapshot=snapshot, stats=stats)
            elif operation == "ignore":
                outcome["snapshot"] = self.service.ignore(source, payload)
            else:
                outcome["snapshot"] = self.service.load(source)
        except AnalysisCanceled:
            outcome["canceled"] = True
        except Exception as exc:
            log.info("Housekeeping operation failed: %s", exc)
            outcome["error"] = str(exc)
        self._emit(self.result, outcome)

class HousekeepingController(QObject):
    def __init__(self, window, service=None):
        super().__init__(window)
        self.window = window
        self.sidebar = HousekeepingSidebar()
        self.service = None
        self.worker = None
        self.token = None
        self.pending = None
        self.source = ""
        self.snapshot = Snapshot()
        self.group = None
        self.closed = False
        self._catalog_id = None
        self._catalog_paths = frozenset()
        self._by_path = {}
        self._counts = {}
        self._selection_key = None
        try:
            self.service = service or HousekeepingService()
        except Exception as exc:
            log.info("Housekeeping unavailable: %s", exc)
            self.sidebar.setEnabled(False)
            self.sidebar.status.setText("Housekeeping storage unavailable.")

    def wire(self):
        self.editor = self.window._asset_inspector.housekeeping_editor()
        self.sidebar.changed.connect(self._filter_changed)
        self.sidebar.analyze.connect(self.analyze)
        self.sidebar.cancel.connect(self.cancel)
        self.editor.view_group.connect(self.view_group)
        self.editor.ignore.connect(self.ignore)
        self.refresh_selection()

    def _filter_changed(self):
        self.window._apply_filters()

    def _sync(self):
        if self.closed or self.service is None:
            return
        source = self.window._current_source
        source = path_key(source) if source else ""
        if source != self.source:
            self.cancel()
            self.pending = None
            self.source, self.snapshot, self.group = source, Snapshot(), None
            self.sidebar.reset()
            self._rebuild()
            if source:
                self.pending = ("load", source, None)
                self._start_pending()
        if self.window._is_scanning and self.worker is not None and self.worker.request[0] == "analyze":
            self.cancel()
        catalog_id = (id(self.window._all_records), len(self.window._all_records))
        if catalog_id != self._catalog_id:
            self._catalog_id = catalog_id
            self._catalog_paths = frozenset(path_key(r.path) for r in self.window._all_records)
            self._rebuild()
        busy = self.worker is not None
        self.sidebar.analyze_button.setEnabled(bool(self.source and self._catalog_paths and not busy and not self.window._is_scanning))
        self.sidebar.cancel_button.setEnabled(busy and self.worker.request[0] == "analyze")

    def _rebuild(self):
        by_path, counts = defaultdict(list), defaultdict(set)
        for f in self.snapshot.findings:
            if f.path not in self._catalog_paths:
                continue
            by_path[f.path].append(f)
            if f.ignored:
                counts["ignored"].add(f.path)
            else:
                counts["*"].add(f.path)
                counts[f.kind].add(f.path)
        self._by_path = dict(by_path)
        self._counts = {key: len(paths) for key, paths in counts.items()}
        self.sidebar.populate(self._counts, self.group)
        self._selection_key = None

    def filter_predicate(self):
        selected = self.sidebar.current_data()
        if selected is None:
            return None
        paths = frozenset(f.path for f in self.snapshot.findings
            if ((selected == "ignored" and f.ignored) or
                (not f.ignored and (selected == "*" or selected == f.kind or selected == "group:" + f.group_id))))
        return lambda record: path_key(record.path) in paths

    def refresh_selection(self):
        if self.closed or not hasattr(self, "editor"):
            return
        self._sync()
        records = self.window.selected_records()
        key = path_key(records[0].path) if len(records) == 1 else ""
        marker = (key, self.snapshot.generation, id(self._by_path))
        if marker != self._selection_key:
            self.editor.set_findings(self._by_path.get(key, ()))
            self._selection_key = marker

    def analyze(self):
        self._sync()
        if self.closed or self.service is None or self.worker is not None or self.window._is_scanning or not self.source:
            return
        self.pending = ("analyze", self.source, list(self.window._all_records))
        self._start_pending()

    def _start_pending(self):
        if self.closed or self.worker is not None or self.pending is None:
            return
        request, self.pending = self.pending, None
        self.token = ScanCancelToken()
        self.worker = HousekeepingWorker(self.service, request, self.token)
        self.worker.result.connect(self._result)
        self.worker.stage.connect(self._stage)
        self.worker.finished.connect(self._finished)
        self.worker.start()
        self.sidebar.analyze_button.setEnabled(False)
        self.sidebar.cancel_button.setEnabled(request[0] == "analyze")
        self.sidebar.status.setText("Loading findings…" if request[0] == "load" else "Analyzing repository…")

    @Slot(str)
    def _stage(self, text):
        if self.closed:
            return
        self.sidebar.status.setText(text)
        if not self.window._is_scanning:
            self.window._update_status(text)

    @Slot(object)
    def _result(self, result):
        if self.closed or result["source"] != self.source:
            return
        if result.get("canceled"):
            text = "Analysis canceled; previous findings retained."
        elif "error" in result:
            text = "Housekeeping unavailable: " + result["error"]
        else:
            self.snapshot = result["snapshot"]
            self._rebuild()
            stats = result.get("stats")
            text = "Housekeeping complete" if stats else "Cached findings loaded"
            if stats:
                text += f" — {stats.hashed_assets:,} candidate files hashed"
                if stats.warning_count:
                    text += f"; {stats.warning_count:,} checks skipped (offline/changed/unsupported)."
                    log.info("Housekeeping skipped checks: %s", stats.warnings)
            self.window._apply_filters(refresh_inspector=False)
            self.refresh_selection()
        self.sidebar.status.setText(text)
        if result["operation"] != "load" and not self.window._is_scanning:
            self.window._update_status(text)

    @Slot()
    def _finished(self):
        worker = self.worker
        if worker is not None:
            self.worker = None
            worker.deleteLater()
        if not self.closed:
            self._start_pending()
            self.refresh_selection()

    def cancel(self):
        if self.token is not None:
            self.token.request_cancel()

    def view_group(self):
        f = self.editor.combo.currentData()
        if f is None or not f.group_id:
            return
        self.group = f.group_id
        self.sidebar.populate(self._counts, self.group)
        self.sidebar.select("group:" + self.group)

    def ignore(self):
        f = self.editor.combo.currentData()
        if f is None or self.worker is not None or self.closed:
            return
        self.pending = ("ignore", self.source, [f])
        self._start_pending()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.pending = None
        self.cancel()
        worker = self.worker
        if worker is not None and worker.isRunning():
            if not worker.wait(2000):
                _DRAINING.add(worker)
                worker.finished.connect(lambda: _DRAINING.discard(worker))
        if self.service is not None:
            self.service.close()
