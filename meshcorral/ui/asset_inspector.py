"""Right-side asset inspector: tabbed production panel (Prime v1.0 Sprint B)."""

from __future__ import annotations

from typing import Final

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from meshcorral.ui.empty_states import (
    MULTI_SELECTION,
    NO_SELECTION,
    READY_TO_SCAN,
    empty_state_spec,
    make_empty_state_widget,
    update_empty_state_widget,
)
from meshcorral.ui.inspector.asset_actions_panel import InspectorMultiActionsPanel
from meshcorral.ui.inspector.inspector_context import InspectorSingleDetail
from meshcorral.ui.inspector.inspector_tabs import InspectorTabbedPanel

_PREVIEW_MAX_3D: Final[int] = 300
_PREVIEW_MAX_IMAGES: Final[int] = 380

_BLENDER_DISABLED_HINT: Final[str] = (
    "Blender thumbnails are available in 3D Asset Mode (.stl / .obj / .fbx)"
)
# Back-compat for tests importing module-level constants.
_EMPTY_MESSAGE = empty_state_spec(NO_SELECTION).body
_EMPTY_NO_SESSION_MESSAGE = empty_state_spec(READY_TO_SCAN).body
_INSPECTOR_SECTION_LABEL_GAP = 6
_INSPECTOR_LAYOUT_SPACING = _INSPECTOR_SECTION_LABEL_GAP
_INSPECTOR_HEADER_STACK_GAP = 8


class AssetInspectorPanel(QWidget):
    """
    Three states: no selection, multiple selection (batch summary), or one asset (tabbed detail).

    Public API and signals are unchanged for :class:`~meshcorral.ui.main_window.MainWindow`.
    """

    open_file_clicked = Signal()
    open_folder_clicked = Signal()
    generate_thumbnail_clicked = Signal()
    copy_path_clicked = Signal()
    batch_queue_thumbnails_clicked = Signal()
    batch_copy_paths_clicked = Signal()
    generate_missing_for_view_clicked = Signal()
    metadata_copied = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._blender_mode_enabled: bool = True
        self._build_ui()
        self._wire_tab_signals()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(_INSPECTOR_LAYOUT_SPACING)

        title = QLabel("Asset inspector")
        title.setObjectName("SectionTitle")
        root.addWidget(title)

        bar = QHBoxLayout()
        bar.setSpacing(_INSPECTOR_LAYOUT_SPACING)
        self._btn_gen_missing = QPushButton("Generate Missing 3D Thumbnails")
        self._btn_gen_missing.setObjectName("SecondaryButton")
        self._btn_gen_missing.setToolTip(
            "Queue missing 3D thumbnails for the current filtered view."
        )
        self._btn_gen_missing.clicked.connect(
            self.generate_missing_for_view_clicked.emit
        )
        bar.addWidget(self._btn_gen_missing, 1)
        root.addLayout(bar)

        self._blender_disabled_hint = QLabel(_BLENDER_DISABLED_HINT)
        self._blender_disabled_hint.setObjectName("MutedLabel")
        self._blender_disabled_hint.setWordWrap(True)
        self._blender_disabled_hint.setVisible(False)
        root.addWidget(self._blender_disabled_hint)

        root.addSpacing(_INSPECTOR_HEADER_STACK_GAP)

        self._stack = QStackedWidget()
        self._stack.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Preferred,
        )
        self._empty_page = self._build_empty_page()
        self._multi_page = InspectorMultiActionsPanel()
        self._tabbed = InspectorTabbedPanel()
        self._tabbed.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._stack.addWidget(self._empty_page)
        self._stack.addWidget(self._multi_page)
        self._stack.addWidget(self._tabbed)
        self._stack.setCurrentIndex(0)
        root.addWidget(self._stack, 0)
        self._set_stack_expands(False)

    def _wire_tab_signals(self) -> None:
        self._tabbed.open_file_clicked.connect(self.open_file_clicked.emit)
        self._tabbed.open_folder_clicked.connect(self.open_folder_clicked.emit)
        self._tabbed.generate_thumbnail_clicked.connect(
            self.generate_thumbnail_clicked.emit
        )
        self._tabbed.copy_path_clicked.connect(self.copy_path_clicked.emit)
        self._tabbed.metadata_copied.connect(self.metadata_copied.emit)
        self._multi_page.batch_queue_thumbnails_clicked.connect(
            self.batch_queue_thumbnails_clicked.emit
        )
        self._multi_page.batch_copy_paths_clicked.connect(
            self.batch_copy_paths_clicked.emit
        )

    def _set_stack_expands(self, expands: bool) -> None:
        """Let the tab stack grow only in single-asset mode (avoids empty dead space)."""
        lay = self.layout()
        if not isinstance(lay, QVBoxLayout):
            return
        if expands:
            self._stack.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            lay.setStretchFactor(self._stack, 1)
        else:
            self._stack.setSizePolicy(
                QSizePolicy.Policy.Preferred,
                QSizePolicy.Policy.Maximum,
            )
            lay.setStretchFactor(self._stack, 0)

    def _build_empty_page(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self._empty_state_host = make_empty_state_widget(
            empty_state_spec(NO_SELECTION),
            parent=w,
        )
        v.addWidget(self._empty_state_host)
        body = self._empty_state_host.findChild(QLabel, "EmptyStateBody")
        self._empty_detail_label = body if body is not None else QLabel()
        return w

    def tag_editor(self):
        """User tag editor on the Metadata tab."""
        return self._tabbed.tag_editor()

    def collection_editor(self):
        """Collection membership controls in Metadata."""
        return self._tabbed.collection_editor()

    def favorite_toggle(self):
        """Favorite star toggle on the Metadata tab."""
        return self._tabbed.favorite_toggle()

    def set_generate_missing_enabled(self, enabled: bool) -> None:
        """Enable the current-view action when a folder has been scanned."""
        self._btn_gen_missing.setEnabled(bool(enabled) and self._blender_mode_enabled)

    def set_blender_thumbnail_actions_enabled(self, enabled: bool) -> None:
        """Enable/disable Blender thumbnail actions based on Asset Mode."""
        self._blender_mode_enabled = bool(enabled)
        self._btn_gen_missing.setEnabled(
            self._blender_mode_enabled and self._btn_gen_missing.isEnabled()
        )
        self._tabbed.set_blender_thumbnail_actions_enabled(enabled)
        self._blender_disabled_hint.setVisible(not enabled)

    def inspector_tab_index(self) -> int:
        """Selected tab on the single-asset inspector (0–3)."""
        return self._tabbed.inspector_tab_index()

    def set_inspector_tab_index(self, index: int) -> None:
        """Restore inspector tab selection."""
        self._tabbed.set_inspector_tab_index(index)

    def configure_for_asset_mode(self, *, images_priority: bool) -> None:
        """Tune preview sizing when Asset Mode changes."""
        self._tabbed.configure_for_asset_mode(images_priority=images_priority)

    def show_empty(self, *, session_active: bool = True) -> None:
        """Show the no-selection state."""
        self._stack.setCurrentIndex(0)
        self._set_stack_expands(False)
        kind = NO_SELECTION if session_active else READY_TO_SCAN
        update_empty_state_widget(self._empty_state_host, empty_state_spec(kind))

    def show_multi(
        self,
        *,
        count: int,
        mesh_count: int,
    ) -> None:
        self._stack.setCurrentIndex(1)
        self._set_stack_expands(False)
        self._multi_page.apply(
            count=count,
            mesh_count=mesh_count,
            blender_enabled=self._blender_mode_enabled,
        )

    def show_single(
        self,
        *,
        name: str,
        path_str: str,
        filename_full: str = "",
        extension: str,
        size_display: str,
        modified_display: str,
        tags: str,
        metadata_block: str,
        metadata_copy_text: str,
        pixmap: QPixmap | None,
        missing_file: bool,
        can_generate_blender_thumbnail: bool,
        has_blender_thumbnail: bool,
        blender_thumbnail_path: str,
        preview_kind: str = "",
        preview_subline: str = "",
        preview_blocked_message: str | None = None,
        folder_display: str = "",
        asset_mode_display: str = "",
        metadata_source_display: str = "",
        dimensions_display: str = "",
        face_count_display: str = "",
        vertex_count_display: str = "",
        watertight_display: str = "",
        mesh_density_display: str = "",
        archive_members_rich_display: str = "",
        metadata_cache_display: str = "",
        deferred_reason_display: str = "",
        thumb_status_display: str = "",
        renderer_profile_display: str = "",
        mesh_health_display: str = "",
        archive_member_count_display: str = "",
        unsupported_reason_display: str = "",
        cache_status_display: str = "",
        thumbnail_state_display: str = "",
        preview_thumb_headline: str | None = None,
        preview_thumb_body: str | None = None,
        preview_show_retry_thumbnail: bool | None = None,
        preview_retry_button_label: str | None = None,
        thumbnail_backend_display: str = "",
        thumbnail_failure_reason_display: str = "",
        thumbnail_fallback_reason_display: str = "",
        thumbnail_suggested_action_display: str = "",
        metadata_deferred: bool = False,
    ) -> None:
        """Fill tabbed inspector for one selected asset."""
        self._stack.setCurrentIndex(2)
        self._set_stack_expands(True)
        detail = InspectorSingleDetail(
            name=name,
            path_str=path_str,
            extension=extension,
            size_display=size_display,
            modified_display=modified_display,
            folder_display=folder_display,
            asset_mode_display=asset_mode_display,
            metadata_source_display=metadata_source_display,
            dimensions_display=dimensions_display,
            face_count_display=face_count_display,
            vertex_count_display=vertex_count_display,
            watertight_display=watertight_display,
            mesh_density_display=mesh_density_display,
            archive_members_rich_display=archive_members_rich_display,
            metadata_cache_display=metadata_cache_display,
            deferred_reason_display=deferred_reason_display,
            tags=tags,
            metadata_block=metadata_block,
            metadata_copy_text=metadata_copy_text,
            pixmap=pixmap,
            missing_file=missing_file,
            can_generate_blender_thumbnail=can_generate_blender_thumbnail,
            has_blender_thumbnail=has_blender_thumbnail,
            blender_thumbnail_path=blender_thumbnail_path,
            preview_kind=preview_kind,
            preview_subline=preview_subline,
            preview_blocked_message=preview_blocked_message,
            thumb_status_display=thumb_status_display,
            renderer_profile_display=renderer_profile_display,
            mesh_health_display=mesh_health_display,
            archive_member_count_display=archive_member_count_display,
            unsupported_reason_display=unsupported_reason_display,
            cache_status_display=cache_status_display,
            thumbnail_state_display=thumbnail_state_display,
            preview_thumb_headline=preview_thumb_headline,
            preview_thumb_body=preview_thumb_body,
            preview_show_retry_thumbnail=preview_show_retry_thumbnail,
            preview_retry_button_label=preview_retry_button_label,
            thumbnail_backend_display=thumbnail_backend_display,
            thumbnail_failure_reason_display=thumbnail_failure_reason_display,
            thumbnail_fallback_reason_display=thumbnail_fallback_reason_display,
            thumbnail_suggested_action_display=thumbnail_suggested_action_display,
            filename_full=filename_full or name,
        )
        self._tabbed.apply_detail(detail, metadata_deferred=metadata_deferred)
