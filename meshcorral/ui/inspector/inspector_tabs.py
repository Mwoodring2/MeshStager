"""Prime v1.0 — tabbed inspector for a single selected asset."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from meshcorral.ui.inspector.asset_actions_panel import AssetActionsPanel
from meshcorral.ui.inspector.diagnostics_panel import DiagnosticsPanel
from meshcorral.ui.inspector.inspector_context import InspectorSingleDetail
from meshcorral.ui.inspector.metadata_panel import MetadataPanel
from meshcorral.ui.inspector.preview_panel import PreviewPanel
from meshcorral.ui.layout_constants import (
    INSPECTOR_PREVIEW_MIN_HEIGHT_3D,
    INSPECTOR_PREVIEW_MIN_HEIGHT_IMAGES,
    INSPECTOR_TAB_MIN_HEIGHT,
)

_PREVIEW_MAX_3D: int = 300
_PREVIEW_MAX_IMAGES: int = 380
_PREVIEW_MIN_3D: int = INSPECTOR_PREVIEW_MIN_HEIGHT_3D
_PREVIEW_MIN_IMAGES: int = INSPECTOR_PREVIEW_MIN_HEIGHT_IMAGES


def _tab_scroll(inner: QWidget) -> QScrollArea:
    """Scroll area for one inspector tab (keeps the tab bar pinned above content)."""
    scroll = QScrollArea()
    scroll.setObjectName("InspectorTabScroll")
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll.setWidget(inner)
    return scroll


class InspectorTabbedPanel(QWidget):
    """
    Preview / Metadata / Diagnostics / Actions tabs for one asset.

    Forwards the same signals as :class:`~meshcorral.ui.asset_inspector.AssetInspectorPanel`.
    """

    open_file_clicked = Signal()
    open_folder_clicked = Signal()
    generate_thumbnail_clicked = Signal()
    copy_path_clicked = Signal()
    metadata_copied = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._blender_enabled = True
        self._images_priority: bool | None = None
        self._build_ui()
        self._wire_signals()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(False)
        self._tabs.setUsesScrollButtons(True)
        self._tabs.setObjectName("InspectorTabs")
        self._tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        tab_bar = self._tabs.tabBar()
        tab_bar.setObjectName("InspectorTabBar")
        tab_bar.setExpanding(True)
        tab_bar.setDrawBase(True)
        tab_bar.setElideMode(Qt.TextElideMode.ElideNone)
        tab_bar.setMinimumHeight(INSPECTOR_TAB_MIN_HEIGHT)

        self._preview = PreviewPanel()
        self._metadata = MetadataPanel()
        self._diagnostics = DiagnosticsPanel()
        self._actions = AssetActionsPanel()

        self._tabs.addTab(_tab_scroll(self._preview), "Preview")
        self._tabs.addTab(_tab_scroll(self._metadata), "Metadata")
        self._tabs.addTab(_tab_scroll(self._diagnostics), "Diagnostics")
        self._tabs.addTab(_tab_scroll(self._actions), "Actions")
        root.addWidget(self._tabs, 1)

    def _wire_signals(self) -> None:
        self._preview.regenerate_thumbnail_clicked.connect(
            self.generate_thumbnail_clicked.emit
        )
        self._metadata.copy_path_clicked.connect(self.copy_path_clicked.emit)
        self._metadata.copy_metadata_clicked.connect(self.metadata_copied.emit)
        self._actions.open_file_clicked.connect(self.open_file_clicked.emit)
        self._actions.reveal_in_explorer_clicked.connect(self.open_folder_clicked.emit)
        self._actions.copy_path_clicked.connect(self.copy_path_clicked.emit)
        self._actions.regenerate_thumbnail_clicked.connect(
            self.generate_thumbnail_clicked.emit
        )

    def configure_for_asset_mode(self, *, images_priority: bool) -> None:
        """Tune preview bounds when asset mode changes."""
        if self._images_priority == images_priority:
            return
        max_px = _PREVIEW_MAX_IMAGES if images_priority else _PREVIEW_MAX_3D
        min_h = _PREVIEW_MIN_IMAGES if images_priority else _PREVIEW_MIN_3D
        self._preview.configure_preview_size(max_px=max_px, min_h=min_h)
        self._images_priority = images_priority

    def inspector_tab_index(self) -> int:
        """Current inspector tab index (0=Preview … 3=Actions)."""
        return int(self._tabs.currentIndex())

    def set_inspector_tab_index(self, index: int) -> None:
        """Select an inspector tab when in range."""
        if 0 <= int(index) < self._tabs.count():
            self._tabs.setCurrentIndex(int(index))

    def set_blender_thumbnail_actions_enabled(self, enabled: bool) -> None:
        """Gate Blender thumbnail buttons when not in 3D asset mode."""
        self._blender_enabled = bool(enabled)

    def preview_panel(self) -> PreviewPanel:
        """The single Preview tab content widget (tests and layout audits)."""
        return self._preview

    def tag_editor(self):
        """User tag editor on the Metadata tab."""
        return self._metadata.tag_editor

    def collection_editor(self):
        """Collection membership controls in Metadata."""
        return self._metadata.collection_editor

    def favorite_toggle(self):
        """Favorite star on the Metadata tab."""
        return self._metadata.favorite_toggle

    def apply_detail(
        self, detail: InspectorSingleDetail, *, metadata_deferred: bool = False
    ) -> None:
        """Push one asset snapshot into all tabs."""
        path_ok = bool(detail.path_str.strip())
        self._preview.apply(
            name=detail.name,
            extension_badge=detail.extension_badge(),
            thumbnail_state=detail.thumbnail_state_display,
            preview_kind=detail.preview_kind,
            preview_subline=detail.preview_subline,
            pixmap=detail.pixmap,
            missing_file=detail.missing_file,
            preview_blocked_message=detail.preview_blocked_message,
            can_regenerate=detail.can_generate_blender_thumbnail,
            blender_enabled=self._blender_enabled,
            preview_thumb_headline=detail.preview_thumb_headline,
            preview_thumb_body=detail.preview_thumb_body,
            preview_show_retry_thumbnail=detail.preview_show_retry_thumbnail,
            preview_retry_button_label=detail.preview_retry_button_label,
            filename_tooltip_text=detail.filename_full or detail.name,
        )
        self._metadata.apply(
            path_str=detail.path_str,
            folder_display=detail.folder_display,
            extension=detail.extension,
            size_display=detail.size_display,
            modified_display=detail.modified_display,
            asset_mode_display=detail.asset_mode_display,
            metadata_source_display=detail.metadata_source_display,
            dimensions_display=detail.dimensions_display,
            face_count_display=detail.face_count_display,
            vertex_count_display=detail.vertex_count_display,
            watertight_display=detail.watertight_display,
            mesh_density_display=detail.mesh_density_display,
            archive_members_display=detail.archive_members_rich_display,
            cache_status_display=detail.metadata_cache_display,
            tags=detail.tags,
            metadata_block=detail.metadata_block,
            metadata_copy_text=detail.metadata_copy_text,
            path_actions_enabled=path_ok,
            metadata_deferred=metadata_deferred,
        )
        self._diagnostics.apply(
            thumb_status=detail.thumb_status_display,
            renderer_profile=detail.renderer_profile_display,
            mesh_health=detail.mesh_health_display,
            archive_member_count=detail.archive_member_count_display,
            unsupported_reason=detail.unsupported_reason_display,
            cache_status=detail.cache_status_display,
            deferred_reason=detail.deferred_reason_display,
            thumbnail_backend=detail.thumbnail_backend_display,
            thumbnail_failure_reason=detail.thumbnail_failure_reason_display,
            thumbnail_fallback_reason=detail.thumbnail_fallback_reason_display,
            thumbnail_suggested_action=detail.thumbnail_suggested_action_display,
            thumbnail_state_display=detail.thumbnail_state_display,
        )
        self._actions.set_open_thumbnail_path(detail.blender_thumbnail_path)
        self._actions.apply(
            missing_file=detail.missing_file,
            path_enabled=path_ok,
            can_regenerate=detail.can_generate_blender_thumbnail,
            has_blender_thumbnail=detail.has_blender_thumbnail,
            blender_enabled=self._blender_enabled,
        )
