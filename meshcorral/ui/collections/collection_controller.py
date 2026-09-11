"""Collection UI coordination, with database work confined to the UI thread."""

import logging
import sqlite3
from pathlib import Path

from PySide6.QtWidgets import QDialog

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.services.collections.collection_service import CollectionService, CollectionError
from meshcorral.ui.collections.collection_widgets import CollectionDialog, CollectionSidebar
from meshcorral.ui.empty_states import COLLECTION_EMPTY, COLLECTION_UNAVAILABLE, empty_state_spec

logger = logging.getLogger(__name__)


class CollectionController:
    """Own service, snapshots, and dialogs; MainWindow retains browser ownership."""

    def __init__(self, window, service=None):
        self.window = window
        self.sidebar = CollectionSidebar()
        self.service = None
        self.collections = []
        self.memberships = {}
        self._names_for_path = {}
        self.available = False
        try:
            self.service = service or CollectionService()
            self._reload()
        except (sqlite3.Error, OSError, CollectionError) as exc:
            logger.warning("Collections unavailable at startup: %s", exc)
            if self.service is not None:
                self.service.close()
                self.service = None
            self.sidebar.setEnabled(False)
            self.sidebar.setToolTip("Collections unavailable. Restart MeshStager to try again.")

    def wire(self):
        self.editor = self.window._asset_inspector.collection_editor()
        self.sidebar.selection_changed.connect(self.window._apply_filters)
        self.sidebar.create_requested.connect(self.create)
        self.sidebar.rename_requested.connect(self.rename)
        self.sidebar.delete_requested.connect(self.delete)
        self.editor.add_requested.connect(self.add_selected)
        self.editor.remove_requested.connect(self.remove_selected)
        self.refresh_selection()

    def close(self):
        if self.service is not None:
            try:
                self.service.close()
            except sqlite3.Error as exc:
                logger.warning("Collection service close failed: %s", exc)
            finally:
                self.service = None

    def _reload(self):
        collections = self.service.list_collections()
        memberships = self.service.membership_snapshot()
        names = {c.collection_id: c.name.casefold() for c in collections}
        self.collections = collections
        self.memberships = memberships
        # Path keys use the same canonicalizer as Tags/Favorites; Path's comparison
        # follows platform case rules after the shared canonicalizer is applied.
        self._names_for_path = {
            Path(path): tuple(names[cid] for cid in ids) for path, ids in memberships.items()
        }
        self.sidebar.populate(collections)
        self.available = True

    def filter_predicate(self):
        selected = self.sidebar.selected_id()
        if selected is None:
            return None
        paths = frozenset(Path(path) for path, ids in self.memberships.items() if selected in ids)
        return lambda record: Path(_norm_path_key(record.path)) in paths

    def search_provider(self):
        # Capture an immutable generation for existing async filter workers. They
        # never call SQLite or observe a partially refreshed collection snapshot.
        names = self._names_for_path
        return lambda record: names.get(Path(_norm_path_key(record.path)), ())

    def refresh_selection(self):
        if not hasattr(self, "editor"):
            return
        records = self.window.selected_records()
        ids = set()
        for record in records:
            ids.update(self.memberships.get(_norm_path_key(record.path), ()))
        names = [c.name for c in self.collections if c.collection_id in ids]
        self.editor.set_selection(len(records), names, available=self.available)

    def empty_spec(self):
        selected = self.sidebar.selected_id()
        if selected is None:
            return None
        collection = next((c for c in self.collections if c.collection_id == selected), None)
        if collection is None or collection.member_count == 0:
            return empty_state_spec(COLLECTION_EMPTY)
        predicate = self.filter_predicate()
        if not any(predicate(r) for r in self.window._all_records):
            return empty_state_spec(COLLECTION_UNAVAILABLE)
        return None

    def _changed(self):
        try:
            self._reload()
        except CollectionError as exc:
            self.window._update_status(str(exc))
            return
        # Match Tags' in-memory invalidation; no filesystem discovery is involved.
        self.window._async_filter_engine.search_index.rebuild(
            self.window._all_records,
            user_tags_for=self.window._user_tags_for_record,
            collections_for=self.search_provider(),
        )
        self.window._apply_filters()
        self.refresh_selection()

    def _show(self, dialog, operation):
        dialog.submit_with(operation)
        try:
            if dialog.exec() == QDialog.DialogCode.Accepted:
                self._changed()
        finally:
            dialog.deleteLater()

    def create(self):
        if self.service is None:
            return
        dialog = CollectionDialog(self.window, title="New Collection", prompt="Collection name", name="")
        self._show(dialog, lambda: self.service.create_collection(dialog.input.text()))

    def rename(self):
        selected = self.sidebar.selected_id()
        collection = next((c for c in self.collections if c.collection_id == selected), None)
        if collection is None or self.service is None:
            return
        dialog = CollectionDialog(self.window, title="Rename Collection", prompt="Collection name", name=collection.name)
        self._show(dialog, lambda: self.service.rename_collection(selected, dialog.input.text()))

    def delete(self):
        selected = self.sidebar.selected_id()
        collection = next((c for c in self.collections if c.collection_id == selected), None)
        if collection is None or self.service is None:
            return
        dialog = CollectionDialog(self.window, title="Delete Collection", action="Delete Collection",
                                  prompt=f"Delete ‘{collection.name}’? Assets will remain on disk.")
        self._show(dialog, lambda: self.service.delete_collection(selected))

    def add_selected(self):
        self._membership_dialog(add=True)

    def remove_selected(self):
        self._membership_dialog(add=False)

    def _membership_dialog(self, *, add):
        paths = [r.path for r in self.window.selected_records()]
        if not paths or self.service is None:
            return
        choices = self.collections
        if not add:
            ids = set()
            for path in paths:
                ids.update(self.memberships.get(_norm_path_key(path), ()))
            choices = [c for c in choices if c.collection_id in ids]
        if not choices:
            self.window._update_status("Create a collection in the sidebar first." if add else "No collections on the selected assets.")
            return
        verb = "Add to" if add else "Remove from"
        dialog = CollectionDialog(self.window, title=f"{verb} Collection", choices=choices,
                                  prompt=f"{verb} a collection for all {len(paths):,} selected asset(s).",
                                  action="Add" if add else "Remove")
        operation = self.service.add_assets if add else self.service.remove_assets
        self._show(dialog, lambda: operation(dialog.choices.currentData(), paths))

    def add_context_actions(self, menu):
        menu.addSeparator()
        enabled = self.available and bool(self.window.selected_records())
        for text, handler in (("Add to Collection…", self.add_selected), ("Remove from Collection…", self.remove_selected)):
            action = menu.addAction(text)
            action.setEnabled(enabled)
            action.triggered.connect(handler)
