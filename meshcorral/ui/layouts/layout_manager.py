"""Save, restore, and name workspace layouts via QSettings."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QSettings

from meshcorral.services.settings_service import SettingsService
from meshcorral.ui.layouts.layout_presets import (
    builtin_preset,
    default_workspace_state,
    list_builtin_preset_names,
)
from meshcorral.ui.layouts.workspace_state import WorkspaceState

if TYPE_CHECKING:
    from meshcorral.ui.main_window import MainWindow

logger = logging.getLogger(__name__)

_KEY_SESSION = "layouts/session_v1"
_KEY_NAMED_PREFIX = "layouts/named/"


class LayoutManager:
    """
    Persist workflow UI state separate from widget instances.

    Session state auto-saves on shutdown; named presets are user- or built-in-defined.
    """

    def __init__(self, settings: QSettings | None = None) -> None:
        self._settings = settings or QSettings(
            SettingsService.ORG_NAME,
            SettingsService.APP_NAME,
        )

    def save_session(self, state: WorkspaceState) -> None:
        """Persist the last session layout."""
        self._settings.setValue(_KEY_SESSION, state.to_json())

    def load_session(self) -> WorkspaceState | None:
        """Load last session, or ``None`` if never saved."""
        raw = self._settings.value(_KEY_SESSION, "", type=str)
        if not raw or not str(raw).strip():
            return None
        return WorkspaceState.from_json(str(raw))

    def clear_session(self) -> None:
        """Remove stored session (reset uses defaults instead)."""
        self._settings.remove(_KEY_SESSION)

    def save_named(self, name: str, state: WorkspaceState) -> bool:
        """Save a user-named layout; returns False if name is empty."""
        key = (name or "").strip()
        if not key:
            return False
        self._settings.setValue(_KEY_NAMED_PREFIX + key, state.to_json())
        return True

    def load_named(self, name: str) -> WorkspaceState | None:
        """Load a user-saved or built-in preset by name."""
        key = (name or "").strip()
        if not key:
            return None
        builtin = builtin_preset(key)
        if builtin is not None:
            return builtin
        raw = self._settings.value(_KEY_NAMED_PREFIX + key, "", type=str)
        if not raw or not str(raw).strip():
            return None
        return WorkspaceState.from_json(str(raw))

    def list_user_named_layouts(self) -> list[str]:
        """Return user-saved layout names (excluding built-ins)."""
        prefix = _KEY_NAMED_PREFIX
        names: list[str] = []
        for key in self._settings.allKeys():
            if key.startswith(prefix):
                names.append(key[len(prefix) :])
        return sorted(names, key=str.lower)

    def list_all_layout_names(self) -> list[str]:
        """Built-in presets first, then user layouts."""
        user = self.list_user_named_layouts()
        return list_builtin_preset_names() + [n for n in user if n not in list_builtin_preset_names()]

    def delete_named(self, name: str) -> bool:
        """Delete a user-named layout."""
        key = (name or "").strip()
        if not key or builtin_preset(key) is not None:
            return False
        self._settings.remove(_KEY_NAMED_PREFIX + key)
        return True

    def capture_from_window(self, window: MainWindow) -> WorkspaceState:
        """Extract stable state from the live main window."""
        from meshcorral.ui.file_columns import FILE_COLUMNS

        widths: dict[str, int] = {}
        hidden: list[str] = []
        model = window._model
        col_count = model.columnCount()
        for i in range(min(col_count, len(FILE_COLUMNS))):
            key = FILE_COLUMNS[i].key
            widths[key] = int(window._table.columnWidth(i))
            if window._table.isColumnHidden(i):
                hidden.append(key)

        splitter_sizes = [310, 720, 418]
        splitter = getattr(window, "_main_splitter", None)
        if splitter is not None:
            splitter_sizes = [int(s) for s in splitter.sizes()]
            if len(splitter_sizes) < 3:
                splitter_sizes = [310, 720, 418]

        mode = (
            SettingsService.VIEW_MODE_GALLERY
            if window._view_stack.currentIndex() == 1
            else SettingsService.VIEW_MODE_TABLE
        )

        return WorkspaceState(
            browse_view_mode=mode,
            thumbnail_pixels=int(window._thumb_controller.display_pixel_size()),
            asset_mode=str(window._asset_mode),
            search_query=(window._search_edit.text() or ""),
            restore_search_query=True,
            extension_filter=window.extension_combo.currentText(),
            category_filter=window.category_combo.currentText(),
            folder_filter=window.folder_combo.currentText(),
            thumb_health_filter=window._thumb_filter_combo.currentText(),
            include_subfolders=window._include_subfolders_checkbox.isChecked(),
            inspector_tab_index=window._asset_inspector.inspector_tab_index(),
            main_splitter_sizes=splitter_sizes[:3],
            table_column_widths=widths,
            hidden_column_keys=hidden,
        )

    def apply_to_window(
        self,
        window: MainWindow,
        state: WorkspaceState,
        *,
        apply_search: bool | None = None,
    ) -> None:
        """
        Apply workspace state to the main window.

        Does not start scans or change source folders. Optionally restores the search
        box when *apply_search* is True or ``state.restore_search_query``.
        """
        from meshcorral.app.config import ASSET_MODE_3D, ASSET_MODE_IMAGES
        from meshcorral.ui.file_columns import FILE_COLUMNS

        should_search = (
            apply_search
            if apply_search is not None
            else state.restore_search_query
        )

        splitter = getattr(window, "_main_splitter", None)
        if splitter is not None and len(state.main_splitter_sizes) >= 3:
            splitter.setSizes([int(s) for s in state.main_splitter_sizes[:3]])

        # Asset mode combo (avoid rescan during init).
        mode = state.asset_mode if state.asset_mode in (ASSET_MODE_3D, ASSET_MODE_IMAGES) else ASSET_MODE_3D
        window._search_mode_combo.blockSignals(True)
        for i in range(window._search_mode_combo.count()):
            if window._search_mode_combo.itemData(i) == mode:
                window._search_mode_combo.setCurrentIndex(i)
                break
        window._search_mode_combo.blockSignals(False)
        if mode != window._asset_mode:
            window._asset_mode = mode
            window._settings_service.set_search_mode(mode)
            window._rebuild_category_combo_for_asset_mode()
            window._asset_inspector.configure_for_asset_mode(
                images_priority=(mode == ASSET_MODE_IMAGES)
            )

        window._include_subfolders_checkbox.blockSignals(True)
        window._include_subfolders_checkbox.setChecked(state.include_subfolders)
        window._include_subfolders_checkbox.blockSignals(False)

        # Filters
        window.extension_combo.blockSignals(True)
        idx = window.extension_combo.findText(state.extension_filter)
        if idx >= 0:
            window.extension_combo.setCurrentIndex(idx)
        window.extension_combo.blockSignals(False)

        window.category_combo.blockSignals(True)
        idx = window.category_combo.findText(state.category_filter)
        if idx >= 0:
            window.category_combo.setCurrentIndex(idx)
        window.category_combo.blockSignals(False)
        window._refresh_extension_options()

        window.folder_combo.blockSignals(True)
        idx = window.folder_combo.findText(state.folder_filter)
        if idx >= 0:
            window.folder_combo.setCurrentIndex(idx)
        window.folder_combo.blockSignals(False)

        window._thumb_filter_combo.blockSignals(True)
        idx = window._thumb_filter_combo.findText(state.thumb_health_filter)
        if idx >= 0:
            window._thumb_filter_combo.setCurrentIndex(idx)
        window._thumb_filter_combo.blockSignals(False)

        # Thumbnail size
        px = state.thumbnail_pixels
        if px in SettingsService.THUMB_PIXEL_CHOICES:
            window._thumb_pixel_combo.blockSignals(True)
            for i in range(window._thumb_pixel_combo.count()):
                if int(window._thumb_pixel_combo.itemData(i)) == px:
                    window._thumb_pixel_combo.setCurrentIndex(i)
                    break
            window._thumb_pixel_combo.blockSignals(False)
            window._thumb_controller.set_display_pixel_size(px)
            window._settings_service.set_thumbnail_display_pixels(px)

        # View mode
        view_mode = state.browse_view_mode
        if view_mode not in (
            SettingsService.VIEW_MODE_TABLE,
            SettingsService.VIEW_MODE_GALLERY,
        ):
            view_mode = SettingsService.VIEW_MODE_TABLE
        window._set_browse_view_mode(view_mode)

        # Table columns
        for i, column in enumerate(FILE_COLUMNS):
            if i >= window._model.columnCount():
                break
            w = state.table_column_widths.get(column.key)
            if w is not None and w > 0:
                window._table.setColumnWidth(i, int(w))
            hidden = column.key in state.hidden_column_keys
            window._table.setColumnHidden(i, hidden)

        window._asset_inspector.set_inspector_tab_index(state.inspector_tab_index)

        if should_search:
            window._search_edit.blockSignals(True)
            window._search_edit.setText(state.search_query)
            window._search_edit.blockSignals(False)
            window._apply_filters(refresh_inspector=False)
        else:
            window._apply_filters(refresh_inspector=False)

    def restore_session_to_window(self, window: MainWindow) -> bool:
        """Apply last session if present; returns True when restored."""
        state = self.load_session()
        if state is None:
            return False
        self.apply_to_window(window, state)
        return True

    def apply_builtin_preset(self, window: MainWindow, name: str) -> bool:
        """Apply a built-in preset by name."""
        state = builtin_preset(name)
        if state is None:
            return False
        self.apply_to_window(window, state, apply_search=False)
        return True

    def reset_to_defaults(self, window: MainWindow) -> None:
        """Reset layout to factory defaults (does not clear session storage)."""
        self.apply_to_window(window, default_workspace_state(), apply_search=False)
