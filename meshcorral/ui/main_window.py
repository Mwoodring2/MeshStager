"""Main window and UI wiring for MeshStager (three-column concept layout)."""

from __future__ import annotations

import io
import logging
import os
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

from PySide6.QtCore import (
    QItemSelectionModel,
    QModelIndex,
    QSettings,
    QSize,
    Qt,
    QThread,
    QTimer,
    QUrl,
)
from PySide6.QtGui import (
    QAction,
    QCloseEvent,
    QDesktopServices,
    QGuiApplication,
    QKeySequence,
    QPixmap,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QInputDialog,
    QLineEdit,
    QListView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from meshcorral.app.config import (
    APP_NAME,
    APP_VERSION,
    ASSET_MODE_3D,
    ASSET_MODE_IMAGES,
    DEBUG_MODE,
    EXPORT_DIR,
    USER_DATA_DIR,
    SUPPORTED_3D_EXTENSIONS,
    SUPPORTED_IMAGE_EXTENSIONS,
    MESH_THUMBNAIL_EXTENSIONS,
    extensions_for_asset_category,
    ordered_category_labels_for_asset_mode,
    read_branded_env_flag,
    supported_extensions_for_asset_mode,
)
from meshcorral.app.icon_branding import apply_window_icon, header_branding_icon_path
from meshcorral.app.bridge.auto_thumb_scan import (
    filter_auto_thumbnail_records,
    is_auto_thumbnail_extension,
    take_with_cap,
)
from meshcorral.app.bridge.bridge_backpressure import (
    BridgeEnqueueReject,
    BridgeEnqueueStats,
    BridgeJobTier,
    bridge_idle_fill_allowed,
    bridge_records_by_tier,
    enqueue_tiered_bridge_thumbnails,
    idle_background_row_indices,
)
from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.app.bridge.visible_thumb_queue import (
    prioritize_visible_records,
    select_auto_thumbnail_candidates,
    select_raster_decode_candidates,
)
from meshcorral.ui.scroll_velocity import ScrollVelocityTracker
from meshcorral.ui.viewport_priority import (
    directional_prefetch_row_indices,
    prioritize_viewport_records,
)
from meshcorral.services.archive_manifest_cache import ArchiveManifestCache
from meshcorral.services.lazy_thumb_health import LazyThumbHealthResolver
from meshcorral.services.metadata_cache import MetadataCache
from meshcorral.services.large_folder_scan_assessment import (
    LargeFolderWarningPersistence,
    build_large_folder_assessment,
)
from meshcorral.services.scan_cache_diagnostics import ScanCacheContext, ScanCacheDiagnostics
from meshcorral.services.scan_cancel import ScanCancelToken
from meshcorral.ui.large_folder_warning_dialog import (
    LargeFolderWarningAction,
    LargeFolderWarningDialog,
    LargeFolderWarningResult,
)
from meshcorral.services.thumb_batch_progress import ThumbBatchProgressTracker
from meshcorral.services.thumb_refresh_accumulator import ThumbRefreshAccumulator
from meshcorral.ui.browse_viewport import visible_row_indices_for_browse_widget
from meshcorral.services.metadata.asset_metadata_summary import AssetMetadataSummary
from meshcorral.services.metadata.geometry_metadata import is_mesh_geometry_extension
from meshcorral.services.metadata.metadata_diagnostics import log_metadata_snapshot
from meshcorral.services.metadata.metadata_summary_builder import build_base_summary
from meshcorral.services.metadata.metadata_summary_registry import MetadataSummaryRegistry
from meshcorral.ui.geometry_metadata_runner import GeometryMetadataRunner
from meshcorral.ui.metadata_enrichment_runner import (
    MetadataEnrichmentRunner,
    MetadataUpdate,
)
from meshcorral.ui.thumb_row_emit import emit_visible_thumb_refresh
from meshcorral.utils.path_perf import (
    AUTO_QUEUE_CAP_NETWORK,
    effective_auto_thumbnail_cap,
    is_network_like_path,
    is_prime_perf_scan,
    perf_status_message,
    remote_throttle_profile,
)
from meshcorral.app.bridge.blender_locator import (
    describe_blender_readiness,
    find_blender_executable,
)
from meshcorral.app.dcc.maya_locator import find_maya_executable
from meshcorral.app.bridge.job_models import BridgeJobResult, BridgeJobStatus
from meshcorral.app.bridge.job_origin import JobOrigin, should_show_failure_modal
from meshcorral.app.bridge.queue_manager import BridgeQueueManager
from meshcorral.services.environment.native_renderer_health import (
    NativeRendererHealth,
    check_native_renderer_health,
    check_startup_environment,
)
from meshcorral.services.thumbnails.native_thumbnail_queue import (
    NativeEnqueueReject,
    NativeThumbnailQueueManager,
)
from meshcorral.services.thumbnails.nonrenderable_thumbs import (
    classify_non_renderable_result,
    fingerprint_for_path,
    is_tracked_non_renderable_extension,
    non_renderable_blocks_auto_enqueue,
)
from meshcorral.services.thumbnails.thumbnail_router import ThumbnailRouter
from meshcorral.services.thumbnails.thumbnail_routing_policy import (
    ThumbnailManualOverride,
    auto_enqueue_allowed,
    is_native_supported,
    route_thumbnail,
    thumbnail_path_for_record,
)
from meshcorral.services.export_service import ExportService
from meshcorral.services.move_service import MoveService
from meshcorral.services.browse_sort import BROWSE_SORT_CHOICES, DEFAULT_SORT_MODE, sort_file_records
from meshcorral.services.scanner import scan_folder_sort_key
from meshcorral.utils.scan_ignores import is_ignored_path
from meshcorral.app.bridge.job_runner import bridge_runtime_root, resolve_bridge_paths
from meshcorral.app.bridge.storage_cleanup import (
    BridgeCleanupManualMode,
    execute_cleanup,
    format_byte_size_human,
    min_age_seconds_for_ui_choice,
    plan_manual_cleanup,
    plan_startup_retention,
)
from meshcorral.services.settings_service import SettingsService
from meshcorral.services.favorites import (
    FAVORITE_FILTER_ALL,
    FAVORITE_FILTER_CHOICES,
    FavoriteService,
)
from meshcorral.services.tagging.tag_service import TagService
from meshcorral.services.search_service import filter_records
from meshcorral.ui.layouts.layout_manager import LayoutManager
from meshcorral.ui.layouts.layout_presets import list_builtin_preset_names
from meshcorral.ui.search.async_filter_engine import ASYNC_FILTER_THRESHOLD, AsyncFilterEngine, FilterRunResult
from meshcorral.services.asset_family import preview_kind_label_for_family, preview_kind_label_for_path
from meshcorral.models.file_record import FileRecord
from meshcorral.models.move_plan import MovePlan
from meshcorral.models.thumb_health import THUMB_FILTER_ALL, THUMB_FILTER_CHOICES, ThumbHealth
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.ui.asset_inspector import AssetInspectorPanel
from meshcorral.ui.branding import BrandHeader
from meshcorral.ui.scan_runner import FolderScanRunner
from meshcorral.ui.scan_timing_profiler import ScanTimingSession
from meshcorral.ui.scan_startup_timing import ScanStartupTimer
from meshcorral.ui.context_actions import FILE_CONTEXT_ACTIONS, ContextActionSpec
from meshcorral.ui.dialogs import AboutDialog, MovePreviewDialog
from meshcorral.ui.blender_job_history_dialog import BlenderJobHistoryDialog
from meshcorral.ui.blender_queue_dialog import BlenderQueueDialog
from meshcorral.ui.file_columns import thumb_column_index
from meshcorral.ui.file_table_model import FileTableModel
from meshcorral.ui.gallery_item_delegate import GalleryItemDelegate
from meshcorral.ui.gallery_list_model import GalleryListModel
from meshcorral.ui.gallery_perf_constants import (
    gallery_max_visible_build,
    gallery_scroll_debounce_ms,
)
from meshcorral.ui.gallery_scroll_filter import GalleryScrollEventFilter
from meshcorral.ui.thumbnail_controller import ThumbnailViewController
from meshcorral.ui.empty_states import (
    FRESH_LAUNCH,
    NO_ASSETS_FOUND,
    NO_MATCHING_RESULTS,
    PREVIEW_UNAVAILABLE,
    READY_TO_SCAN,
    SCAN_CANCELED,
    SOURCE_UNAVAILABLE,
    empty_state_hint_lines,
    empty_state_spec,
)
from meshcorral.ui.footer_status import (
    FooterCounts,
    format_bridge_footer,
    format_counts_strip,
    format_filter_footer,
    format_scan_cancel_pending_footer,
    format_scan_complete_message,
    format_scan_footer,
    format_scan_still_scanning_footer,
    format_loading_thumbnails_progress,
    format_thumbnail_failure_footer,
    format_thumbnail_footer,
    format_verbose_diagnostics,
    prime_mode_hint,
    prime_mode_label,
    status_export_complete,
    status_layout_loaded,
    status_layout_reset,
    status_layout_saved,
    status_loading_visible_thumbnails,
    status_metadata_copied,
    status_path_copied,
    status_preset_applied,
    status_canceling_scan,
    status_scan_canceled,
    status_scan_folder_first,
    status_source_unavailable,
    status_scrolling_thumbnails_paused,
    status_settings_saved,
    status_native_thumbnails_blender_fallback,
    status_thumbnail_ready,
    verbose_footer_enabled,
)
from meshcorral.ui.filename_display import truncate_filename
from meshcorral.ui.thumbnails.asset_state_copy import standard_copy_for_inspector
from meshcorral.ui.thumbnails.thumbnail_ux_copy import (
    REASON_UNSUPPORTED,
    build_preview_thumb_ux,
    classify_bridge_error_kind,
    infer_thumbnail_backend_label,
    suggested_action_for_preview,
)
from meshcorral.ui.font_scaling import normalize_combo_box_fonts
from meshcorral.ui.settings_dialog import SettingsDialog
from meshcorral.ui.theme import apply_theme_palette, build_app_stylesheet
from meshcorral.ui.error_actions import (
    copy_to_clipboard,
    open_file_with_default_app,
    open_folder_in_explorer,
)
from meshcorral.app.dcc.dcc_profiles import (
    configured_executable_for_profile,
    dcc_profile_for_extension,
    get_dcc_profile,
)
from meshcorral.utils.datetime_display import format_local_modified_display
from meshcorral.utils.filesize_display import format_file_size_display
from meshcorral.utils.path_utils import normalize_path, safe_resolve_path
from meshcorral.utils.validators import require_destination_baseline

from meshcorral.ui.layout_constants import (
    CONTROL_HEIGHT as LAYOUT_CONTROL_HEIGHT,
    DEFAULT_RIGHT_PANEL_WIDTH,
    MIN_RIGHT_PANEL_WIDTH,
)

WINDOW_MARGIN = 10
PANEL_MARGIN = 10
PANEL_SPACING = 8
GROUP_SPACING = 12
# Right column: width and vertical rhythm between major blocks.
RIGHT_PANEL_WIDTH = DEFAULT_RIGHT_PANEL_WIDTH
RIGHT_PANEL_SECTION_BREAK = GROUP_SPACING + 6
# Transfer/export scroll vs. pinned file-actions / inspector blocks.
RIGHT_PANEL_TRANSFER_TO_EXPORT_GAP = GROUP_SPACING
RIGHT_PANEL_EXPORT_FILE_ACTIONS_BREAK = GROUP_SPACING
RIGHT_PANEL_FILE_ACTIONS_TOP = GROUP_SPACING
RIGHT_PANEL_FILE_ACTION_BUTTON_GAP = 6
RIGHT_PANEL_FILE_ACTION_TO_INSPECTOR_GAP = PANEL_SPACING
# Left column: slightly more air between section titles, mode row, and filter stacks.
LEFT_PANEL_SPACING = PANEL_SPACING + 4
LEFT_SECTION_BREAK = GROUP_SPACING + 5

_ASSET_SUITE_TAGLINE = "Scan and organize 3D, DCC, and image assets safely."
CONTROL_HEIGHT = LAYOUT_CONTROL_HEIGHT
HEADER_ICON_SIZE = 56

_TIMING_LOGS: bool = read_branded_env_flag("TIMING")

# Name contains field: pause before filter apply (larger datasets need less UI churn).
FILTER_SEARCH_DEBOUNCE_MS = 400

# --- Window geometry persistence (v0.1.1 hotfix) ---
_KEY_WINDOW_GEOMETRY = "ui/window_geometry"
_KEY_WINDOW_STATE = "ui/window_state"


def _safe_default_window_rect(available) -> "QRect":
    """Default window rect: ~75% of available geometry, centered (pure math)."""
    from PySide6.QtCore import QRect

    avail = available
    w = max(800, int(avail.width() * 0.75))
    h = max(600, int(avail.height() * 0.75))
    w = min(w, avail.width())
    h = min(h, avail.height())
    x = avail.left() + (avail.width() - w) // 2
    y = avail.top() + (avail.height() - h) // 2
    return QRect(int(x), int(y), int(w), int(h))


def clamp_rect_to_available(saved, available) -> "QRect":
    """
    Clamp *saved* QRect into *available* (availableGeometry) on both axes.

    Rules:
    - width/height are reduced first to fit
    - x/y are clamped so the window fully fits
    - if the saved rect is mostly off-screen, return a centered default rect instead
    """
    from PySide6.QtCore import QRect

    rect = QRect(saved)
    avail = QRect(available)
    if avail.width() <= 0 or avail.height() <= 0:
        return rect
    if rect.width() <= 0 or rect.height() <= 0:
        return _safe_default_window_rect(avail)

    inter = rect.intersected(avail)
    rect_area = max(1, rect.width() * rect.height())
    inter_area = max(0, inter.width() * inter.height())
    if inter_area / rect_area < 0.20:
        return _safe_default_window_rect(avail)

    # Clamp size first (both dimensions).
    w = min(rect.width(), avail.width())
    h = min(rect.height(), avail.height())

    # Then clamp origin (both axes) so bottom/right edges stay inside availableGeometry.
    x_min = avail.left()
    y_min = avail.top()
    x_max = avail.right() - w + 1
    y_max = avail.bottom() - h + 1
    if x_max < x_min:
        x_max = x_min
    if y_max < y_min:
        y_max = y_min

    x = rect.left()
    y = rect.top()
    x = x_min if x < x_min else x_max if x > x_max else x
    y = y_min if y < y_min else y_max if y > y_max else y
    return QRect(int(x), int(y), int(w), int(h))


def restore_safe_window_geometry(window: QMainWindow, settings: QSettings) -> None:
    """
    Restore window geometry/state safely across multi-monitor setups.

    - Clamp restored QRect to the screen's availableGeometry()
    - If saved geometry is invalid or mostly off-screen, use a centered default rect
    - Preserve maximized state only when it is valid
    """
    raw = settings.value(_KEY_WINDOW_GEOMETRY, b"")
    # Use a plain int default; some PySide6 builds don't allow int(Qt.WindowNoState).
    state_raw = settings.value(_KEY_WINDOW_STATE, 0)

    # Determine target screen: saved rect center → screenAt; else primary.
    screen = QGuiApplication.primaryScreen()
    avail = screen.availableGeometry() if screen is not None else None

    from PySide6.QtCore import QRect, QPoint

    saved_rect = QRect()
    if isinstance(raw, (bytes, bytearray)) and raw:
        # Apply directly to a temp widget to decode bytes is overkill; decode by restoring
        # into the window and reading geometry would cause visible jumps. Use a safe fallback:
        # rely on QMainWindow.restoreGeometry then immediately clamp.
        try:
            window.restoreGeometry(raw)  # type: ignore[arg-type]
            saved_rect = window.geometry()
        except Exception:
            saved_rect = QRect()

    if saved_rect.isNull() or saved_rect.width() <= 0 or saved_rect.height() <= 0:
        if avail is not None:
            window.setGeometry(_safe_default_window_rect(avail))
        return

    center = saved_rect.center()
    s2 = QGuiApplication.screenAt(QPoint(center.x(), center.y()))
    if s2 is not None:
        screen = s2
    if screen is None:
        return
    avail = screen.availableGeometry()

    clamped = clamp_rect_to_available(saved_rect, avail)
    window.setGeometry(clamped)

    try:
        state_int = int(state_raw)
    except (TypeError, ValueError):
        state_int = 0

    # Preserve maximized only if it still fits.
    try:
        maximized_flag = int(Qt.WindowMaximized)
    except (TypeError, ValueError):
        maximized_flag = 0x2
    if state_int & maximized_flag:
        window.setWindowState(window.windowState() | Qt.WindowMaximized)


def filter_search_debounce_milliseconds() -> int:
    """
    Return the debounce delay (ms) between last search keystroke and ``_apply_filters``.

    Kept as a pure accessor so tests can pin the value without constructing the main window.
    """
    return FILTER_SEARCH_DEBOUNCE_MS


def _debug_print_plan_preview(
    dest_dir: Path, sources: list[Path], plan: list[MovePlan]
) -> None:
    """Optional diagnostics for the transfer pipeline (see ``DEBUG_MODE``)."""
    if not DEBUG_MODE:
        return
    print("DEBUG selected records:", len(sources))
    print("DEBUG destination:", dest_dir)
    print("DEBUG plans built:", len(plan))
    for item in plan[:10]:
        print(
            "DEBUG plan:",
            item.source_path,
            "->",
            item.destination_path,
            item.status,
            item.message,
        )


def _shorten_path_display(path: Path | str, max_len: int = 72) -> str:
    """Return a display string for a path, truncating from the left if very long."""
    text = str(path)
    if len(text) <= max_len:
        return text
    return "…" + text[-(max_len - 1) :]


def _reason_transfer_buttons_disabled(
    *,
    has_source: bool,
    has_visible: bool,
    has_selection: bool,
    has_destination: bool,
) -> str:
    """
    Return a short tooltip when Move or Copy is disabled.

    Describes the first unmet requirement. Returns an empty string when all
    prerequisites are satisfied (caller should show the enabled-state tooltip).
    """
    if not has_source:
        return "Scan a source folder first."
    if not has_visible:
        return "No files in the current view. Adjust filters or run a new scan."
    if not has_selection:
        return "Select one or more rows in the table or gallery."
    if not has_destination:
        return "Enter or browse to a destination folder."
    return ""


def _reason_export_disabled(*, has_source: bool, has_visible: bool) -> str:
    """Return a short tooltip when Export Current View is disabled."""
    if not has_source:
        return "Scan a source folder first."
    if not has_visible:
        return "No rows in the current view. Adjust filters or run a new scan."
    return ""


def _reason_file_actions_disabled(*, has_source: bool, has_selection: bool) -> str:
    """Return a short tooltip when Reveal in Explorer or Copy path is disabled."""
    if not has_source:
        return "Scan a source folder first."
    if not has_selection:
        return "Select one or more rows in the table or gallery."
    return ""


def _issue_lines_for_transfer(
    items: list[MovePlan], msg_lines: list[str], limit: int = 10
) -> list[str]:
    """Build user-facing issue lines when no files transferred successfully."""
    if msg_lines:
        return list(msg_lines[:limit])
    lines: list[str] = []
    for item in items[:limit]:
        lines.append(f"{item.status}: {item.message} ({item.source_path})")
    return lines


def _transfer_counts(items: list[MovePlan]) -> tuple[int, int, int]:
    """Return (ok, blocked, error) counts for a transfer attempt."""
    ok = sum(1 for p in items if p.status in (MoveService.STATUS_MOVED, MoveService.STATUS_COPIED))
    blocked = sum(1 for p in items if p.status == MoveService.STATUS_BLOCKED)
    error = sum(1 for p in items if p.status == MoveService.STATUS_ERROR)
    return ok, blocked, error


def thumbnail_failure_should_show_modal(origin: JobOrigin | None) -> bool:
    """
    Return True if a failed thumbnail job's *origin* warrants a modal dialog.

    Treats ``None`` (origin lost or never recorded) as background — the safer,
    non-blocking default for large gallery scans.
    """
    if origin is None:
        return False
    return should_show_failure_modal(origin)


class MainWindow(QMainWindow):
    """Primary application window."""

    def __init__(self) -> None:
        super().__init__()
        apply_window_icon(self)
        self.setWindowTitle(APP_NAME)
        self.resize(1280, 780)

        self._settings_service = SettingsService()
        self._native_renderer_health: NativeRendererHealth = check_native_renderer_health()
        self._startup_environment = check_startup_environment(self._settings_service)
        # Windowed/frozen builds have no console, so record the same readiness lines the
        # Settings → Environment page shows. Lets support confirm a build from the log.
        logger.info(
            "Startup environment | Native renderer: %s | Blender: %s | "
            "Metadata cache: %s | Thumbnail cache: %s",
            self._startup_environment.native_renderer,
            self._startup_environment.blender,
            self._startup_environment.metadata_cache,
            self._startup_environment.thumbnail_cache,
        )
        self._native_degraded_footer_shown = False
        self._layout_manager = LayoutManager()
        self._thumbnail_router = ThumbnailRouter(self._settings_service)
        self._native_thumb_queue = NativeThumbnailQueueManager(self._thumbnail_router, self)
        self._native_job_origins: dict[str, JobOrigin] = {}
        self._bridge_queue = BridgeQueueManager(self._settings_service, self)

        self._mover = MoveService()
        self._exporter = ExportService()
        self._tag_service = TagService()
        self._favorite_service = FavoriteService()
        from meshcorral.ui.collections.collection_controller import CollectionController
        from meshcorral.ui.housekeeping.controller import HousekeepingController
        self._collections = CollectionController(self)
        self._housekeeping = HousekeepingController(self)

        # Guards the Asset Mode handler from clobbering restored state during the
        # construction / restore pass — only user-initiated changes should clear rows.
        self._is_initializing_ui: bool = True
        # Set by :meth:`closeEvent` so background queue paths and slots can no-op
        # during application teardown (deterministic shutdown coordinator).
        self._shutting_down: bool = False
        self._all_records: list = []
        self._view_records: list = []
        # The folder the user selected and sees in the Source panel. Survives Asset
        # Mode switches; ``_current_source`` (the source for the *current* working
        # rows) is cleared on a mode switch while this stays as the scan target.
        self._selected_source_path: str = ""
        self._current_source: str = ""
        self._unavailable_source_text: str = ""
        self._warm_catalog_active = False
        self._is_scanning: bool = False
        self._scan_thread: QThread | None = None
        self._scan_runner: FolderScanRunner | None = None
        self._pre_scan_backup_records: list[FileRecord] = []
        self._pre_scan_backup_source: str = ""
        self._pending_scan_path: str = ""
        self._did_initial_column_resize = False
        self._last_scan_folder = ""
        self._last_scan_elapsed_s: float | None = None
        self._last_scan_progress_folder: str = ""
        self._scan_discovery_count: int = 0
        self._scan_user_canceled_hint: bool = False
        self._scan_cancel_token: ScanCancelToken | None = None
        self._scan_cancel_pending: bool = False
        self._scan_generation: int = 0
        self._scan_accept_events: bool = False
        self._scan_launch_generation: int = 0
        self._scan_launch_pending: bool = False
        self._large_folder_warning_dialog: QDialog | None = None
        self._scan_startup_timer: ScanStartupTimer | None = None
        self._scan_first_batch_logged: bool = False
        self._scan_first_progress_logged: bool = False
        self._scan_timing_session: ScanTimingSession | None = None
        self._scan_last_progress_monotonic_s: float = 0.0
        self._scan_heartbeat_timer = QTimer(self)
        self._scan_heartbeat_timer.setInterval(1500)
        self._scan_heartbeat_timer.timeout.connect(self._on_scan_heartbeat_tick)
        self._header_icon_path = header_branding_icon_path()
        self._last_blender_failure_dialog_s: float = 0.0
        self._session_thumb_failure_count: int = 0
        self._filter_footer_note: str | None = None
        self._active_error_boxes: list[QMessageBox] = []

        self._model = FileTableModel()
        self._thumb_controller = ThumbnailViewController(self)
        self._lazy_thumb_health = LazyThumbHealthResolver(
            self._thumb_controller.resolve_thumb_health
        )
        self._thumb_refresh_accumulator = ThumbRefreshAccumulator(self)
        self._thumb_refresh_accumulator.flush_requested.connect(self._on_thumb_refresh_batch)
        self._thumb_controller.set_refresh_coalescer(self._thumb_refresh_accumulator.add_path_key)
        self._thumb_controller.set_decode_status_callback(self._update_thumb_queue_status)
        self._thumb_batch_progress = ThumbBatchProgressTracker()
        self._thumb_progress_timer = QTimer(self)
        self._thumb_progress_timer.setInterval(1000)
        self._thumb_progress_timer.timeout.connect(self._on_thumb_progress_tick)
        self._scan_still_footer_after_s: float = 2.5
        self._prime_perf_active: bool = False
        self._viewport_epoch: int = 0
        self._last_viewport_scroll_for_epoch: int = -1
        self._last_view_stack_index_for_epoch: int = -1
        self._viewport_thumb_interval_ms: int = 120
        self._enrichment_thread: QThread | None = None
        self._enrichment_runner: MetadataEnrichmentRunner | None = None
        self._enrichment_in_progress: bool = False
        self._metadata_cache: MetadataCache | None = None
        self._archive_manifest_cache: ArchiveManifestCache | None = None
        self._metadata_registry = MetadataSummaryRegistry()
        self._geometry_meta_thread: QThread | None = None
        self._geometry_meta_runner: GeometryMetadataRunner | None = None
        self._geometry_meta_path_pending: str = ""
        self._last_scan_cache_diag: ScanCacheDiagnostics | None = None
        self._scan_skip_auto_thumbnails_once: bool = False
        self._scan_force_lightweight_once: bool = False
        self._scan_visible_thumbs_only_once: bool = False
        self._last_scan_thumb_queued: int = 0
        self._viewport_thumb_timer = QTimer(self)
        self._viewport_thumb_timer.setSingleShot(True)
        self._viewport_thumb_timer.timeout.connect(self._on_viewport_thumb_timer)
        self._scroll_settle_timer = QTimer(self)
        self._scroll_settle_timer.setSingleShot(True)
        self._scroll_settle_timer.timeout.connect(self._on_scroll_settle_timer)
        self._selection_inspector_debounce = QTimer(self)
        self._selection_inspector_debounce.setSingleShot(True)
        self._selection_inspector_debounce.timeout.connect(self._on_selection_inspector_debounced)
        self._bridge_idle_fill_timer = QTimer(self)
        self._bridge_idle_fill_timer.setSingleShot(True)
        self._bridge_idle_fill_timer.timeout.connect(self._run_bridge_idle_fill)
        self._bridge_last_activity_monotonic: float = time.monotonic()
        self._scroll_velocity = ScrollVelocityTracker()
        self._prime_network_like: bool = False
        self._scroll_status_last_monotonic: float = 0.0
        self._scroll_status_fast_active: bool = False
        self._thumb_controller.set_epoch_callback(self.viewport_epoch)
        self._model.set_thumbnail_controller(self._thumb_controller)

        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QTableView.SelectRows)
        self._table.setSelectionMode(QTableView.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(False)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_table_context_menu)
        self._table.doubleClicked.connect(self._on_table_double_clicked)
        self._apply_table_thumbnail_layout()

        self._gallery_model = GalleryListModel(self._thumb_controller)
        self._thumb_controller.set_gallery_model(self._gallery_model)
        self._gallery_list = QListView()
        self._gallery_list.setViewMode(QListView.ViewMode.IconMode)
        self._gallery_list.setResizeMode(QListView.ResizeMode.Fixed)
        self._gallery_list.setWordWrap(True)
        self._gallery_list.setWrapping(True)
        self._gallery_list.setUniformItemSizes(True)
        self._gallery_list.setSpacing(8)
        self._gallery_list.setModel(self._gallery_model)
        self._gallery_list.setItemDelegate(
            GalleryItemDelegate(self._thumb_controller, self._gallery_list)
        )
        self._gallery_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self._gallery_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._gallery_list.customContextMenuRequested.connect(
            self._show_gallery_context_menu
        )
        self._gallery_list.doubleClicked.connect(self._on_gallery_double_clicked)
        self._gallery_scroll_filter = GalleryScrollEventFilter(
            self._gallery_list, self._gallery_model
        )
        self._gallery_list.viewport().installEventFilter(self._gallery_scroll_filter)
        self._sync_gallery_icon_and_grid()

        self._view_stack = QStackedWidget()
        self._view_stack.addWidget(self._table)
        self._view_stack.addWidget(self._gallery_list)
        self._table.verticalScrollBar().valueChanged.connect(self._schedule_viewport_thumb_pass)
        self._gallery_list.verticalScrollBar().valueChanged.connect(
            self._schedule_viewport_thumb_pass
        )
        self._view_stack.currentChanged.connect(lambda _i: self._schedule_viewport_thumb_pass())

        self._source_path_label = QLabel("No source selected")
        self._source_path_label.setObjectName("SourcePath")
        self._source_path_label.setWordWrap(True)
        self._source_stats_label = QLabel("—")
        self._source_stats_label.setObjectName("MutedLabel")
        self._source_stats_label.setWordWrap(True)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search… (e.g. helmet, ext:stl, tag:approved)")
        self._search_edit.setToolTip(
            "Search name, path, folder, extension, type, and your tags. "
            "Tokens: ext:stl, type:3d, folder:name, name:text, tag:print-ready, collection:\"Print Ready\", size>100mb. "
            "Works with Type, Ext, and Folder filters (all must match)."
        )

        self._dest_edit = QLineEdit()
        self._dest_edit.setPlaceholderText("Destination folder…")
        dest_browse = QPushButton("Browse…")
        dest_browse.setToolTip(
            "Choose the destination folder for Move or Copy Selected To."
        )
        dest_browse.clicked.connect(self._browse_destination)

        settings = QSettings()
        last_dest = settings.value("paths/last_destination", "", type=str)
        if last_dest and str(last_dest).strip():
            try:
                restored = normalize_path(str(last_dest))
                require_destination_baseline(restored, "Destination folder")
                self._dest_edit.setText(str(restored))
            except (ValueError, OSError):
                pass
        self._last_scan_folder = settings.value("paths/last_scan_folder", "", type=str)

        _sm = self._settings_service.search_mode()
        if _sm not in (ASSET_MODE_3D, ASSET_MODE_IMAGES):
            _sm = ASSET_MODE_3D
        self._asset_mode: str = _sm
        self._rescan_after_mode_change: bool = False

        self._move_btn = QPushButton("Move Selected…")
        self._move_btn.setObjectName("MoveButton")
        self._move_btn.clicked.connect(self._move_selected)
        self._copy_to_btn = QPushButton("Copy Selected To…")
        self._copy_to_btn.setObjectName("CopyButton")
        self._copy_to_btn.clicked.connect(self._copy_selected_files)
        self._reveal_btn = QPushButton("Reveal in Explorer")
        self._reveal_btn.clicked.connect(self._reveal_selected)
        self._copy_path_btn = QPushButton("Copy Selected Path")
        self._copy_path_btn.clicked.connect(self._copy_selected_path)

        self._build_central_layout(dest_browse=dest_browse)
        self._apply_control_button_heights()
        self._asset_inspector.open_file_clicked.connect(self._inspector_open_file)
        self._asset_inspector.open_folder_clicked.connect(self._inspector_open_folder)
        self._asset_inspector.generate_thumbnail_clicked.connect(
            self._generate_blender_thumbnail
        )
        self._asset_inspector.copy_path_clicked.connect(self._inspector_copy_path)
        self._asset_inspector.batch_queue_thumbnails_clicked.connect(
            self._queue_blender_thumbnails_selected
        )
        self._asset_inspector.batch_copy_paths_clicked.connect(
            self._inspector_batch_copy_paths
        )
        self._asset_inspector.generate_missing_for_view_clicked.connect(
            self._on_generate_missing_thumbnails_for_view
        )
        self._asset_inspector.metadata_copied.connect(
            self._on_inspector_metadata_copied
        )

        self._bridge_queue.queue_count_changed.connect(
            self._on_bridge_queue_count_changed
        )
        self._bridge_queue.running_job_id_changed.connect(
            self._on_bridge_running_job_changed
        )
        self._bridge_queue.running_source_path_changed.connect(
            self._on_bridge_running_source_changed
        )
        self._bridge_queue.job_completed.connect(self._on_thumbnail_job_completed)
        self._native_thumb_queue.job_completed.connect(self._on_thumbnail_job_completed)

        from meshcorral.services.render.render_status import get_render_status_notifier

        get_render_status_notifier().status_changed.connect(self._on_render_pipeline_status)

        self._filter_search_debounce_timer = QTimer(self)
        self._filter_search_debounce_timer.setSingleShot(True)
        self._filter_search_debounce_timer.timeout.connect(self._apply_filters_debounced_fire)

        self._async_filter_engine = AsyncFilterEngine(self)
        self._async_filter_engine.results_ready.connect(self._on_async_filter_results)
        self._filter_refresh_inspector_pending = True

        self._geometry_meta_runner = GeometryMetadataRunner()
        self._geometry_meta_thread = QThread(self)
        self._geometry_meta_runner.moveToThread(self._geometry_meta_thread)
        self._geometry_meta_runner.summary_ready.connect(self._on_geometry_metadata_ready)
        # Started lazily by :meth:`_ensure_geometry_metadata_thread` on the first mesh
        # selection, so a window that is never used owns no running thread to outlive it.

        self._search_edit.textChanged.connect(self._on_search_text_changed)

        self._browse_source_btn.clicked.connect(self._on_browse_source)
        self._scan_source_btn.clicked.connect(self._on_scan_source)
        self._export_top_btn.clicked.connect(self._export_view)
        self._help_header_btn.clicked.connect(self._about)

        self._dest_edit.textChanged.connect(self._on_destination_text_changed)
        sm = self._table.selectionModel()
        if sm is not None:
            sm.selectionChanged.connect(self._on_file_selection_changed)
        gsm = self._gallery_list.selectionModel()
        if gsm is not None:
            gsm.selectionChanged.connect(self._on_file_selection_changed)

        self._thumb_controller.display_pixel_size_changed.connect(
            self._on_thumb_display_pixel_size_changed
        )

        status = QStatusBar()
        self.setStatusBar(status)
        self._status_ready_label = QLabel("Ready")
        self._status_ready_label.setObjectName("BrandSubtitle")
        self._status_stats_label = QLabel("")
        self._status_stats_label.setObjectName("BrandSubtitle")
        self._status_thumbs_label = QLabel("Thumbnails: —")
        self._status_thumbs_label.setObjectName("BrandSubtitle")
        self._status_blender_label = QLabel("Blender: —")
        self._status_blender_label.setObjectName("BrandSubtitle")
        self._status_version_label = QLabel(f"{APP_NAME} v{APP_VERSION}")
        self._status_version_label.setObjectName("BrandSubtitle")
        status.addWidget(self._status_ready_label)
        status.addWidget(self._status_stats_label, 1)
        status.addPermanentWidget(self._status_thumbs_label)
        status.addPermanentWidget(self._status_blender_label)
        status.addPermanentWidget(self._status_version_label)
        self._on_bridge_queue_count_changed(self._bridge_queue.queue_length())
        self._apply_saved_settings()
        # Window restore after style/theme is applied to avoid geometry jitter.
        restore_safe_window_geometry(self, QSettings())
        if not self._layout_manager.restore_session_to_window(self):
            pass
        QTimer.singleShot(450, self._maybe_autotrim_bridge_storage_at_startup)
        # Idle launch: do not activate the previous source or auto-scan / warm-verify.
        # ``paths/last_scan_folder`` stays in QSettings (and ``_last_scan_folder``) so
        # Browse can start in the recent folder and manual open still warm-reopens.
        # Skip the full thumbnail index walk when a complete catalog exists for that
        # recent folder — gallery is empty until the user opens a source anyway.
        warm_catalog_known = bool(self._last_scan_folder) and (
            self._ensure_metadata_cache().has_complete_source(
                self._last_scan_folder,
                self._include_subfolders_checkbox.isChecked(),
                supported_extensions_for_asset_mode(self._asset_mode),
            )
        )
        if not warm_catalog_known:
            self._thumb_controller.refresh_index()
        self._begin_idle_session()
        self._refresh_source_button_states()
        self._update_ui_state()
        self._update_status("Ready")
        QTimer.singleShot(0, self._maybe_show_startup_native_degraded_hint)
        self._scan_cancel_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._scan_cancel_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._scan_cancel_shortcut.setEnabled(False)
        self._scan_cancel_shortcut.activated.connect(self._on_escape_cancel_scan)
        # Construction + idle session are done; subsequent Asset Mode changes are user-driven.
        self._is_initializing_ui = False
        self._wire_tag_ui()
        self._wire_favorite_ui()
        self._collections.wire()
        self._housekeeping.wire()

    def _wire_favorite_ui(self) -> None:
        """Connect Tier 2.2 favorite star toggle."""
        toggle = self._asset_inspector.favorite_toggle()
        toggle.favorite_toggled.connect(self._on_favorite_toggled)

    def _on_favorite_toggled(self, favorited: bool) -> None:
        records = self.selected_records()
        if len(records) != 1:
            return
        self._favorite_service.set_favorite(records[0].path, favorite=favorited)
        self._apply_filters(refresh_inspector=False)
        self._refresh_favorite_toggle_for_selection()
        self._collections.refresh_selection()
        self._housekeeping.refresh_selection()

    def _refresh_favorite_toggle_for_selection(self) -> None:
        records = self.selected_records()
        toggle = self._asset_inspector.favorite_toggle()
        if len(records) == 1:
            toggle.set_enabled(True)
            toggle.set_favorite(self._favorite_service.is_favorite(records[0].path))
        else:
            toggle.set_enabled(False)
            toggle.set_favorite(False)

    def _wire_tag_ui(self) -> None:
        """Connect Tier 2.1 tag UI to :class:`TagService`."""
        editor = self._asset_inspector.tag_editor()
        editor.add_tag_requested.connect(self._open_add_tag_dialog)
        editor.tag_remove_requested.connect(self._on_remove_user_tag)
        editor.tags_changed.connect(self._on_user_tags_changed)

    def _user_tags_for_record(self, record: FileRecord) -> tuple[str, ...]:
        """Normalized user tag names for search indexing."""
        return self._tag_service.user_tags_for_record(record.path)

    def _open_add_tag_dialog(self) -> None:
        """Show :class:`TagDialog` for the current selection."""
        from meshcorral.ui.tags.tag_dialog import TagDialog

        records = self.selected_records()
        paths = [r.path for r in records]
        if not paths:
            return
        title = "Add Tag" if len(paths) == 1 else f"Add Tag to {len(paths)} Assets"
        dialog = TagDialog(self, title=title)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._tag_service.add_tags_from_dialog(paths, dialog.input_text())
        except ValueError as exc:
            QMessageBox.warning(self, "Tags", str(exc))
            return
        self._on_user_tags_changed()

    def _on_remove_user_tag(self, tag: str) -> None:
        """Remove one tag from a single selected asset (MVP)."""
        records = self.selected_records()
        if len(records) != 1:
            return
        self._tag_service.remove_tag(records[0].path, tag)
        self._on_user_tags_changed()

    def _on_user_tags_changed(self) -> None:
        """Refresh search index and inspector after tag edits."""
        self._async_filter_engine.search_index.rebuild(
            self._all_records,
            user_tags_for=self._user_tags_for_record,
        )
        self._refresh_tag_editor_for_selection()
        self._apply_filters(refresh_inspector=False)

    def _refresh_tag_editor_for_selection(self) -> None:
        """Sync Metadata tab tags with the current selection."""
        records = self.selected_records()
        paths = [r.path for r in records]
        editor = self._asset_inspector.tag_editor()
        tag_union: set[str] = set()
        for path in paths:
            tag_union.update(self._tag_service.get_tags(path))
        editor.set_selection(
            paths=paths,
            tags=sorted(tag_union, key=str.lower),
            multi=len(paths) > 1,
        )

    def _apply_saved_settings(self) -> None:
        """Load theme, scan default, destination default, and palette from :class:`SettingsService`."""
        theme_mode = self._settings_service.theme_mode()
        self.apply_theme_everywhere(theme_mode)

        self._include_subfolders_checkbox.setChecked(
            self._settings_service.include_subfolders_default()
        )

        default_destination = self._settings_service.default_destination().strip()
        if default_destination:
            try:
                restored = normalize_path(default_destination)
                require_destination_baseline(restored, "Destination folder")
                self._dest_edit.setText(str(restored))
            except (ValueError, OSError):
                pass

        self._apply_browse_view_settings()
        self._refresh_destination_field_style()
        self._update_ui_state()
        self._refresh_blender_readiness_label()

    def apply_theme_everywhere(self, theme_mode: str) -> None:
        """
        Single entry point to apply the current theme to the whole UI.

        This updates both application palette (native controls/dialogs) and stylesheet-driven
        surfaces, and forces a re-polish to avoid mixed light/dark widget backgrounds.
        """
        mode = theme_mode if theme_mode in ("dark", "light") else "dark"
        css = build_app_stylesheet(theme_mode=mode)
        app = QApplication.instance()
        if app is not None:
            apply_theme_palette(app, mode)
            # Ensure dialogs and late-created widgets share the same stylesheet.
            app.setStyleSheet(css)
        self.setStyleSheet(css)
        self._thumb_controller.set_theme_mode(mode)

        # Force style refresh to clear any stale palette-derived backgrounds.
        try:
            self.style().unpolish(self)
            self.style().polish(self)
        except Exception:  # noqa: BLE001
            pass
        try:
            self.update()
        except TypeError:
            pass
        for w in (
            getattr(self, "_table", None),
            getattr(self, "_gallery_list", None),
            getattr(self, "_right_panel", None),
            getattr(self, "_center_panel", None),
            getattr(self, "_asset_inspector", None),
            getattr(self, "_blender_job_menu", None),
        ):
            if w is None:
                continue
            try:
                w.style().unpolish(w)
                w.style().polish(w)
            except Exception:  # noqa: BLE001
                pass
            # Some PySide bindings expose `update()` overloads that require args on certain types.
            try:
                w.update()
            except TypeError:
                pass
            try:
                if hasattr(w, "viewport") and callable(w.viewport):  # type: ignore[truthy-function]
                    vp = w.viewport()  # type: ignore[misc]
                    try:
                        vp.update()
                    except TypeError:
                        pass
            except Exception:  # noqa: BLE001
                pass

        # Re-polishing restores the stylesheet's pixel font, so restate combo box fonts on
        # the point axis afterwards (Qt reads a point size when opening a drop-down popup).
        normalize_combo_box_fonts(self)

    def _rebuild_layout_load_menu(self) -> None:
        """Refresh user-named entries under Load layout."""
        self._layout_load_menu.clear()
        for preset_name in list_builtin_preset_names():
            self._layout_load_menu.addAction(
                preset_name,
                lambda checked=False, n=preset_name: self._on_load_named_layout(n),
            )
        user_names = self._layout_manager.list_user_named_layouts()
        if user_names:
            self._layout_load_menu.addSeparator()
            for name in user_names:
                self._layout_load_menu.addAction(
                    name,
                    lambda checked=False, n=name: self._on_load_named_layout(n),
                )

    def _on_save_named_layout(self) -> None:
        """Prompt for a name and persist the current workspace."""
        name, ok = QInputDialog.getText(
            self,
            "Save layout",
            "Layout name:",
        )
        if not ok or not (name or "").strip():
            return
        state = self._layout_manager.capture_from_window(self)
        if not self._layout_manager.save_named(name.strip(), state):
            return
        self._rebuild_layout_load_menu()
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(status_layout_saved(name.strip()), 4000)

    def _on_load_named_layout(self, name: str) -> None:
        """Apply a built-in or user-saved layout."""
        state = self._layout_manager.load_named(name)
        if state is None:
            QMessageBox.information(self, "Load layout", f"Layout not found: {name}")
            return
        self._layout_manager.apply_to_window(self, state, apply_search=False)
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(status_layout_loaded(name), 4000)

    def _on_apply_layout_preset(self, name: str) -> None:
        """Apply a built-in preset from the Layout menu."""
        if not self._layout_manager.apply_builtin_preset(self, name):
            QMessageBox.information(self, "Layout", f"Unknown preset: {name}")
            return
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(status_preset_applied(name), 4000)

    def _on_reset_layout(self) -> None:
        """Restore factory layout defaults."""
        self._layout_manager.reset_to_defaults(self)
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(status_layout_reset(), 4000)

    def _persist_workspace_layout(self) -> None:
        """Save current workspace for next launch (session restore)."""
        try:
            state = self._layout_manager.capture_from_window(self)
            self._layout_manager.save_session(state)
        except (RuntimeError, AttributeError, TypeError) as exc:
            logger.debug("workspace layout save skipped: %s", exc)

    def _open_settings_dialog(self) -> None:
        """Open Settings; on Save, re-apply stored values to this window."""
        dialog = SettingsDialog(self._settings_service, self)
        dialog.adjustSize()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._apply_saved_settings()
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(status_settings_saved(), 3000)

    def _apply_table_thumbnail_layout(self) -> None:
        """
        Align table icon sizing vs row height for the Thumb column.

        Gallery zoom (`display_pixel_size`) controls icon mode; the table intentionally uses a
        separate stable thumbnail decode size via :class:`~meshcorral.ui.thumbnail_controller.ThumbnailViewController`.
        """
        tp = int(self._thumb_controller.table_thumb_pixel_size())
        self._table.setIconSize(QSize(tp, tp))
        self._table.verticalHeader().setDefaultSectionSize(tp + 28)
        self._table.verticalHeader().setMinimumSectionSize(tp + 20)
        ix = thumb_column_index()
        w = tp + 24
        hh = self._table.horizontalHeader()
        hh.setSectionResizeMode(ix, QHeaderView.ResizeMode.Fixed)
        hh.resizeSection(ix, w)
        self._table.setColumnWidth(ix, w)

    def _apply_browse_view_settings(self) -> None:
        """Restore table/gallery mode and thumbnail pixel size from :class:`SettingsService`."""
        mode = self._settings_service.browse_view_mode()
        px = self._settings_service.thumbnail_display_pixels()
        self._thumb_pixel_combo.blockSignals(True)
        for i in range(self._thumb_pixel_combo.count()):
            if int(self._thumb_pixel_combo.itemData(i)) == px:
                self._thumb_pixel_combo.setCurrentIndex(i)
                break
        self._thumb_pixel_combo.blockSignals(False)
        self._thumb_controller.set_display_pixel_size(px)
        self._sync_gallery_icon_and_grid()
        if mode == SettingsService.VIEW_MODE_GALLERY:
            self._view_stack.setCurrentIndex(1)
            self._view_gallery_btn.setChecked(True)
        else:
            self._view_stack.setCurrentIndex(0)
            self._view_table_btn.setChecked(True)

    def _sync_gallery_icon_and_grid(self) -> None:
        """Keep icon mode grid in sync with the current zoomed thumbnail size."""
        px = self._thumb_controller.display_pixel_size()
        self._gallery_list.setIconSize(QSize(px, px))
        self._gallery_list.setGridSize(self._gallery_model.current_cell_size())

    def _on_thumb_display_pixel_size_changed(self, _px: int) -> None:
        self._sync_gallery_icon_and_grid()

    def _on_view_mode_table_chosen(self) -> None:
        self._set_browse_view_mode(SettingsService.VIEW_MODE_TABLE)

    def _on_view_mode_gallery_chosen(self) -> None:
        self._set_browse_view_mode(SettingsService.VIEW_MODE_GALLERY)

    def _set_browse_view_mode(self, mode: str) -> None:
        if mode not in (
            SettingsService.VIEW_MODE_TABLE,
            SettingsService.VIEW_MODE_GALLERY,
        ):
            mode = SettingsService.VIEW_MODE_TABLE
        paths = self._selected_paths_for_selection_restore()
        if mode == SettingsService.VIEW_MODE_GALLERY:
            self._view_stack.setCurrentIndex(1)
            self._view_gallery_btn.setChecked(True)
            self._gallery_list.setFocus()
        else:
            self._view_stack.setCurrentIndex(0)
            self._view_table_btn.setChecked(True)
            self._apply_table_thumbnail_layout()
            self._table.setFocus()
        self._settings_service.set_browse_view_mode(mode)
        self._restore_selection_from_paths(paths)

    def _on_thumb_pixel_combo_changed(self, index: int) -> None:
        if index < 0:
            return
        data = self._thumb_pixel_combo.currentData()
        if data is None:
            return
        px = int(data)
        if px == self._thumb_controller.display_pixel_size():
            return
        self._thumb_controller.set_display_pixel_size(px)
        self._settings_service.set_thumbnail_display_pixels(px)

    def _on_gallery_double_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        rec = self._gallery_model.record_at(index.row())
        if rec is None:
            return
        self._open_with_preferred_dcc_or_default(rec.path)

    def _show_gallery_context_menu(self, pos) -> None:  # type: ignore[no-untyped-def]
        menu = self._build_file_context_menu()
        global_pos = self._gallery_list.viewport().mapToGlobal(pos)
        menu.exec(global_pos)

    def _make_panel(self) -> QFrame:
        """Controlling surface for a column: card-style containment (see :obj:`#Panel` style)."""
        panel = QFrame()
        panel.setObjectName("Panel")
        panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        return panel

    def _make_divider(self) -> QFrame:
        """Thin horizontal rule for grouping within a panel."""
        line = QFrame()
        line.setObjectName("Divider")
        line.setFrameShape(QFrame.NoFrame)
        line.setFixedHeight(1)
        return line

    def _welcome_center_accent_line(self) -> QWidget:
        """Narrow centered rule for the welcome panel (muted, not a progress-style bar)."""
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch(1)
        line = QFrame()
        line.setObjectName("WelcomeDivider")
        line.setFixedSize(160, 1)
        lay.addWidget(line, 0)
        lay.addStretch(1)
        return wrap

    def _apply_control_button_heights(self) -> None:
        """Consistent control height for primary workflow and utility buttons."""
        for button in (
            self._browse_source_btn,
            self._scan_source_btn,
            self._welcome_scan_btn,
            self._copy_to_btn,
            self._move_btn,
            self._export_top_btn,
            self._reveal_btn,
            self._copy_path_btn,
            self._reset_filters_btn,
            self._browse_dest_btn,
            self._blender_jobs_header_btn,
            self._view_table_btn,
            self._view_gallery_btn,
        ):
            button.setMinimumHeight(CONTROL_HEIGHT)
        self._thumb_pixel_combo.setMinimumHeight(CONTROL_HEIGHT)

    def _build_left_panel(self) -> QFrame:
        from PySide6.QtWidgets import QLayout, QStyle
        left_frame = self._make_panel()
        # Preserve the existing usable width when the vertical scrollbar appears.
        left_frame.setMinimumWidth(220 + self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent))
        # Additive sections must scroll instead of compressing their controls.
        outer = QVBoxLayout(left_frame)
        outer.setContentsMargins(0, 0, 0, 0)
        self._left_content_scroll = QScrollArea()
        self._left_content_scroll.setWidgetResizable(True)
        self._left_content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._left_content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_content = QWidget()
        left_content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        left_v = QVBoxLayout(left_content)
        left_v.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        self._left_content_scroll.setWidget(left_content)
        outer.addWidget(self._left_content_scroll)
        left_v.setContentsMargins(PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN)
        left_v.setSpacing(LEFT_PANEL_SPACING)

        st = QLabel("Source")
        st.setObjectName("SectionTitle")
        left_v.addWidget(st)
        left_v.addSpacing(4)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        mode_row.addWidget(QLabel("Asset Mode"), 0)
        self._search_mode_combo = QComboBox()
        self._search_mode_combo.addItem("3D / DCC Assets", ASSET_MODE_3D)
        self._search_mode_combo.addItem("Images / Textures", ASSET_MODE_IMAGES)
        self._search_mode_combo.setToolTip(
            "3D / DCC Assets: scan geometry, DCC scene files, and support sidecars. "
            "Images / Textures: scan image files only. "
            "Switching Asset Mode clears the table until you scan again."
        )
        self._search_mode_combo.blockSignals(True)
        for i in range(self._search_mode_combo.count()):
            if self._search_mode_combo.itemData(i) == self._asset_mode:
                self._search_mode_combo.setCurrentIndex(i)
                break
        self._search_mode_combo.blockSignals(False)
        self._search_mode_combo.currentIndexChanged.connect(self._on_search_mode_changed)
        mode_row.addWidget(self._search_mode_combo, 1)
        left_v.addLayout(mode_row)
        left_v.addSpacing(4)

        source_btn_row = QHBoxLayout()
        source_btn_row.setSpacing(6)
        self._browse_source_btn = QPushButton("Browse…")
        self._browse_source_btn.setToolTip("Pick the folder to scan for assets.")
        self._scan_source_btn = QPushButton("Scan Source")
        self._scan_source_btn.setObjectName("PrimaryButton")
        self._scan_source_btn.setToolTip("Scan the selected folder and load results into the table.")
        source_btn_row.addWidget(self._browse_source_btn)
        source_btn_row.addWidget(self._scan_source_btn, 1)
        left_v.addLayout(source_btn_row)
        left_v.addWidget(self._source_path_label)
        left_v.addWidget(self._source_stats_label)
        self._source_mode_hint = QLabel()
        self._source_mode_hint.setObjectName("MutedLabel")
        self._source_mode_hint.setWordWrap(True)
        left_v.addWidget(self._source_mode_hint)

        left_v.addSpacing(LEFT_SECTION_BREAK)
        left_v.addWidget(self._make_divider())
        left_v.addSpacing(LEFT_SECTION_BREAK)

        fh = QLabel("Filters")
        fh.setObjectName("SectionTitle")
        left_v.addWidget(fh)
        left_v.addSpacing(4)

        left_v.addWidget(QLabel("Name contains"))
        left_v.addWidget(self._search_edit)
        left_v.addSpacing(4)
        self.category_combo = QComboBox()
        for label in ordered_category_labels_for_asset_mode(self._asset_mode):
            self.category_combo.addItem(label)
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        self.category_combo.setToolTip(
            "Broad file groups. Extension list updates when Type or Asset Mode changes."
        )
        le_row = QHBoxLayout()
        le_row.addWidget(QLabel("Type"))
        le_row.addWidget(self.category_combo, 1)
        left_v.addLayout(le_row)
        left_v.addSpacing(4)
        self.extension_combo = QComboBox()
        self.extension_combo.addItem("All")
        for ext in extensions_for_asset_category(self._asset_mode, "All"):
            self.extension_combo.addItem(ext)
        self.extension_combo.currentTextChanged.connect(self._apply_filters)
        self.extension_combo.setToolTip("Filter by file extension (depends on Type above).")
        ex_row = QHBoxLayout()
        ex_row.addWidget(QLabel("Ext"))
        ex_row.addWidget(self.extension_combo, 1)
        left_v.addLayout(ex_row)
        left_v.addSpacing(4)
        self.folder_combo = QComboBox()
        self.folder_combo.addItem("All Folders")
        self.folder_combo.currentTextChanged.connect(self._apply_filters)
        self.folder_combo.setToolTip(
            "Show only files whose parent folder name matches (from the last scan)."
        )
        fo_row = QHBoxLayout()
        fo_row.addWidget(QLabel("Folder"))
        fo_row.addWidget(self.folder_combo, 1)
        left_v.addLayout(fo_row)
        left_v.addSpacing(4)

        self._favorite_filter_combo = QComboBox()
        for label in FAVORITE_FILTER_CHOICES:
            self._favorite_filter_combo.addItem(label)
        self._favorite_filter_combo.currentTextChanged.connect(self._apply_filters)
        self._favorite_filter_combo.setToolTip(
            "Show all assets or only those marked with ☆ Favorite."
        )
        fav_row = QHBoxLayout()
        fav_row.addWidget(QLabel("Favorites"))
        fav_row.addWidget(self._favorite_filter_combo, 1)
        left_v.addLayout(fav_row)
        left_v.addSpacing(4)

        self._thumb_filter_combo = QComboBox()
        for label in THUMB_FILTER_CHOICES:
            self._thumb_filter_combo.addItem(label)
        self._thumb_filter_combo.currentTextChanged.connect(self._apply_filters)
        self._thumb_filter_combo.setToolTip(
            "Filter by Blender thumbnail coverage (from bridge result.json on disk)."
        )
        th_row = QHBoxLayout()
        th_row.addWidget(QLabel("Thumbnails"))
        th_row.addWidget(self._thumb_filter_combo, 1)
        left_v.addLayout(th_row)
        left_v.addSpacing(4)

        self._include_subfolders_checkbox = QCheckBox("Include subfolders")
        self._include_subfolders_checkbox.setChecked(True)
        self._include_subfolders_checkbox.setToolTip(
            "When checked, a scan includes subfolders. When off, only the top folder is scanned."
        )
        left_v.addWidget(self._include_subfolders_checkbox)
        self._reset_filters_btn = QPushButton("Reset Filters")
        self._reset_filters_btn.setToolTip(
            "Clear Name contains and set Type, Ext, and Folder to All. "
            "The current scan, Asset Mode, and Include subfolders stay as they are."
        )
        self._reset_filters_btn.clicked.connect(self._reset_filters)
        left_v.addWidget(self._reset_filters_btn)

        left_v.addSpacing(LEFT_SECTION_BREAK)
        left_v.addWidget(self._collections.sidebar)
        left_v.addWidget(self._housekeeping.sidebar)
        left_v.addStretch(1)
        return left_frame

    def _build_center_panel(self) -> QFrame:
        center_frame = self._make_panel()
        center_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        center_v = QVBoxLayout(center_frame)
        center_v.setContentsMargins(PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN)
        center_v.setSpacing(PANEL_SPACING)

        header = QFrame()
        header.setObjectName("PanelHeader")
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(8, 5, 8, 5)
        hlay.setSpacing(PANEL_SPACING)
        cv_title = QLabel("Current view")
        cv_title.setObjectName("SectionTitle")
        self._current_view_count_label = QLabel("0 files")
        self._current_view_count_label.setObjectName("MutedLabel")
        hlay.addWidget(cv_title)
        hlay.addWidget(self._current_view_count_label)
        hlay.addStretch(1)
        sort_lbl = QLabel("Sort")
        sort_lbl.setObjectName("MutedLabel")
        hlay.addWidget(sort_lbl)
        self._sort_combo = QComboBox()
        for label, mode_id in BROWSE_SORT_CHOICES:
            self._sort_combo.addItem(label, mode_id)
        default_sort_idx = 0
        for i in range(self._sort_combo.count()):
            if self._sort_combo.itemData(i) == DEFAULT_SORT_MODE:
                default_sort_idx = i
                break
        self._sort_combo.setCurrentIndex(default_sort_idx)
        self._sort_combo.setToolTip(
            "Sort the current filtered file list (table and gallery). "
            "Does not rescan or regenerate thumbnails."
        )
        self._sort_combo.currentIndexChanged.connect(self._on_browse_sort_changed)
        hlay.addWidget(self._sort_combo)
        self._view_table_btn = QToolButton()
        self._view_table_btn.setObjectName("HeaderActionButton")
        self._view_table_btn.setText("Table")
        self._view_table_btn.setCheckable(True)
        self._view_table_btn.setToolTip("List view with all columns and sortable fields.")
        self._view_gallery_btn = QToolButton()
        self._view_gallery_btn.setObjectName("HeaderActionButton")
        self._view_gallery_btn.setText("Gallery")
        self._view_gallery_btn.setCheckable(True)
        self._view_gallery_btn.setToolTip("Thumbnail grid of the current filtered file list (same data as the table).")
        self._view_mode_buttongroup = QButtonGroup(self)
        self._view_mode_buttongroup.setExclusive(True)
        self._view_mode_buttongroup.addButton(self._view_table_btn)
        self._view_mode_buttongroup.addButton(self._view_gallery_btn)
        self._view_table_btn.clicked.connect(
            self._on_view_mode_table_chosen
        )
        self._view_gallery_btn.clicked.connect(
            self._on_view_mode_gallery_chosen
        )
        hlay.addWidget(self._view_table_btn)
        hlay.addWidget(self._view_gallery_btn)
        thumbs = QLabel("Gallery Size")
        thumbs.setObjectName("MutedLabel")
        hlay.addWidget(thumbs)
        self._thumb_pixel_combo = QComboBox()
        for px in SettingsService.THUMB_PIXEL_CHOICES:
            label = f"{px}px"
            if px == 48:
                label = "48px (small)"
            elif px == 256:
                label = "256px (large)"
            self._thumb_pixel_combo.addItem(label, int(px))
        self._thumb_pixel_combo.setToolTip(
            "Thumbnail size in Gallery view only. The table’s Thumb column uses a larger fixed "
            "size (~72–96px) so thumbnails stay readable next to dense columns."
        )
        self._thumb_pixel_combo.currentIndexChanged.connect(
            self._on_thumb_pixel_combo_changed
        )
        hlay.addWidget(self._thumb_pixel_combo)
        center_v.addWidget(header)

        self._view_hint_label = QLabel("")
        self._view_hint_label.setObjectName("MutedLabel")
        self._view_hint_label.setWordWrap(True)
        self._view_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._browser_center_page = QWidget()
        self._browser_center_page.setObjectName("PanelInner")
        browser_v = QVBoxLayout(self._browser_center_page)
        browser_v.setContentsMargins(0, 0, 0, 0)
        browser_v.setSpacing(PANEL_SPACING)
        browser_v.addWidget(self._view_hint_label)
        self._view_hint_label.hide()
        browser_v.addWidget(self._view_stack, 1)

        self._welcome_center_page = self._build_welcome_center_page()
        self._center_body_stack = QStackedWidget()
        self._center_body_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._center_body_stack.addWidget(self._welcome_center_page)
        self._center_body_stack.addWidget(self._browser_center_page)
        center_v.addWidget(self._center_body_stack, 1)
        return center_frame

    def _build_welcome_center_page(self) -> QWidget:
        """
        First-run style welcome when there is no meaningful browse session yet.

        Rule: show this page while ``_current_source`` is empty (no folder has been scanned
        yet in this session, including after Asset Mode clears the working set).
        """
        page = QFrame()
        page.setObjectName("WelcomeCenterPanel")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(28, 36, 28, 36)
        outer.setSpacing(0)

        outer.addStretch(1)

        mid = QHBoxLayout()
        mid.setSpacing(0)
        mid.addStretch(1)

        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(16)

        title = QLabel("Welcome to MeshStager")
        title.setObjectName("SectionTitle")
        title.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )
        inner_layout.addWidget(title)
        inner_layout.addWidget(self._welcome_center_accent_line())
        feature_spine = QLabel("3D · DCC · Images")
        feature_spine.setObjectName("WelcomeFeatureRow")
        feature_spine.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        inner_layout.addWidget(feature_spine, alignment=Qt.AlignmentFlag.AlignHCenter)

        tagline = QLabel(empty_state_spec(FRESH_LAUNCH).body)
        tagline.setObjectName("MutedLabel")
        tagline.setWordWrap(True)
        tagline.setMaximumWidth(520)
        tagline.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        inner_layout.addWidget(tagline, alignment=Qt.AlignmentFlag.AlignHCenter)
        inner_layout.addSpacing(4)
        inner_layout.addWidget(self._welcome_center_accent_line())

        bullets = QLabel(
            "• Scan Blender and Maya projects\n"
            "• Filter by asset family or extension\n"
            "• Preview thumbnails and scene files\n"
            "• Move or copy files with overwrite protection"
        )
        bullets.setObjectName("MutedLabel")
        bullets.setWordWrap(True)
        bullets.setMaximumWidth(520)
        bullets.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        inner_layout.addWidget(bullets, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._welcome_scan_btn = QPushButton("Scan Source")
        self._welcome_scan_btn.setObjectName("PrimaryButton")
        self._welcome_scan_btn.setMinimumWidth(200)
        self._welcome_scan_btn.setToolTip(
            "Scan the selected source folder (use Browse… in the left panel to choose one)."
        )
        self._welcome_scan_btn.clicked.connect(self._on_scan_source)
        inner_layout.addWidget(self._welcome_scan_btn, alignment=Qt.AlignmentFlag.AlignHCenter)

        mid.addWidget(inner, 0)
        mid.addStretch(1)
        outer.addLayout(mid)
        outer.addStretch(2)
        return page

    def _sync_center_welcome_vs_browser(self) -> None:
        """Toggle welcome vs. file browser stack based on whether a source folder has been scanned."""
        if not self._current_source:
            self._center_body_stack.setCurrentWidget(self._welcome_center_page)
        else:
            self._center_body_stack.setCurrentWidget(self._browser_center_page)

    def _build_right_panel(self, *, dest_browse: QPushButton) -> QFrame:
        right_frame = self._make_panel()
        right_frame.setMinimumWidth(MIN_RIGHT_PANEL_WIDTH)
        # The right panel can become vertically dense; wrap content in a scroll area so
        # we keep a reasonable width without forcing window height.
        outer = QVBoxLayout(right_frame)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        scroll = QScrollArea()
        scroll.setObjectName("PanelScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        transfer_block = QWidget()
        transfer_block.setObjectName("PanelInner")
        right = QVBoxLayout(transfer_block)
        right.setContentsMargins(PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN)
        right.setSpacing(PANEL_SPACING)
        scroll.setWidget(transfer_block)
        scroll.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        outer.addWidget(scroll, 0)
        self._browse_dest_btn = dest_browse

        tr = QLabel("Transfer")
        tr.setObjectName("SectionTitle")
        right.addWidget(tr)
        dl = QLabel("Destination")
        dl.setObjectName("PanelSubTitle")
        right.addWidget(dl)
        dest_row = QHBoxLayout()
        dest_row.setSpacing(6)
        dest_row.addWidget(self._dest_edit, 1)
        dest_row.addWidget(dest_browse)
        right.addLayout(dest_row)
        self._copy_to_btn.setObjectName("CopyButton")
        self._move_btn.setObjectName("MoveButton")
        right.addWidget(self._copy_to_btn)
        right.addWidget(self._move_btn)

        right.addSpacing(RIGHT_PANEL_TRANSFER_TO_EXPORT_GAP)

        self._export_top_btn = QPushButton("Export Current View")
        self._export_top_btn.setObjectName("ExportButton")
        right.addWidget(self._export_top_btn)

        export_break = RIGHT_PANEL_EXPORT_FILE_ACTIONS_BREAK // 2
        right.addSpacing(export_break)
        right.addWidget(self._make_divider())
        right.addSpacing(export_break)

        self._right_file_actions_wrap = QWidget()
        self._right_file_actions_wrap.setObjectName("RightFileActionsBlock")
        self._right_file_actions_wrap.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Maximum,
        )
        file_actions_layout = QVBoxLayout(self._right_file_actions_wrap)
        file_actions_layout.setContentsMargins(
            PANEL_MARGIN,
            RIGHT_PANEL_FILE_ACTIONS_TOP,
            PANEL_MARGIN,
            0,
        )
        file_actions_layout.setSpacing(RIGHT_PANEL_FILE_ACTION_BUTTON_GAP)
        file_actions_title = QLabel("File actions")
        file_actions_title.setObjectName("SectionTitle")
        file_actions_layout.addWidget(file_actions_title)
        file_actions_layout.addWidget(self._reveal_btn)
        file_actions_layout.addWidget(self._copy_path_btn)
        outer.addWidget(self._right_file_actions_wrap, 0)

        inspector_wrap = QWidget()
        inspector_wrap.setObjectName("InspectorDock")
        inspector_layout = QVBoxLayout(inspector_wrap)
        inspector_layout.setContentsMargins(
            PANEL_MARGIN,
            RIGHT_PANEL_FILE_ACTION_TO_INSPECTOR_GAP,
            PANEL_MARGIN,
            PANEL_MARGIN,
        )
        inspector_layout.setSpacing(0)
        inspector_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._asset_inspector = AssetInspectorPanel()
        self._asset_inspector.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Expanding
        )
        inspector_layout.addWidget(self._asset_inspector, 1)
        outer.addWidget(inspector_wrap, 1)

        summary_wrap = QWidget()
        summary_wrap.setObjectName("PanelInner")
        summary_layout = QVBoxLayout(summary_wrap)
        summary_layout.setContentsMargins(
            PANEL_MARGIN,
            PANEL_SPACING,
            PANEL_MARGIN,
            PANEL_MARGIN,
        )
        summary_layout.setSpacing(PANEL_SPACING)
        summary_layout.addWidget(self._make_divider())
        st = QLabel("Transfer summary")
        st.setObjectName("PanelSubTitle")
        summary_layout.addWidget(st)
        self.move_summary_selected = QLabel("Selected: 0")
        self.move_summary_destination = QLabel("Destination: Not set")
        self.move_summary_ready = QLabel("Ready: 0")
        self.move_summary_conflicts = QLabel("Conflicts: 0")
        self.move_summary_selected.setToolTip(
            "Selected files in the current table or gallery (hidden-by-filter rows are never selected)."
        )
        self.move_summary_destination.setToolTip(
            "Folder used for Move and Copy Selected To. Must be a valid folder path."
        )
        self.move_summary_ready.setToolTip(
            "Dry-run count of transfers that would succeed now—same rules as the Move/Copy preview."
        )
        self.move_summary_conflicts.setToolTip(
            "Dry-run count of rows that would not run yet (collision, same path, bad destination, or "
            "missing source). Matches the preview Status column."
        )
        summary_layout.addWidget(self.move_summary_selected)
        summary_layout.addWidget(self.move_summary_destination)
        summary_layout.addWidget(self.move_summary_ready)
        summary_layout.addWidget(self.move_summary_conflicts)
        outer.addWidget(summary_wrap, 0)

        return right_frame

    def _build_central_layout(self, *, dest_browse: QPushButton) -> None:
        """Assemble brand header and three :obj:`#Panel` columns: filters / current view / transfer."""
        root = QWidget()
        main_v = QVBoxLayout()
        main_v.setContentsMargins(WINDOW_MARGIN, WINDOW_MARGIN, WINDOW_MARGIN, WINDOW_MARGIN)
        main_v.setSpacing(PANEL_SPACING)

        header_right = QHBoxLayout()
        header_right.setSpacing(6)
        self._layout_header_btn = QToolButton()
        self._layout_header_btn.setObjectName("HeaderActionButton")
        self._layout_header_btn.setText("Layout")
        self._layout_header_btn.setToolTip(
            "Save, load, and reset workspace layouts (panels, view mode, filters, inspector tab)."
        )
        self._layout_menu = QMenu(self)
        self._layout_menu.addAction("Save layout as…", self._on_save_named_layout)
        self._layout_load_menu = self._layout_menu.addMenu("Load layout")
        self._layout_menu.addAction("Reset layout to defaults", self._on_reset_layout)
        self._layout_menu.addSeparator()
        for preset_name in list_builtin_preset_names():
            self._layout_menu.addAction(
                f"Preset: {preset_name}",
                lambda checked=False, n=preset_name: self._on_apply_layout_preset(n),
            )
        self._rebuild_layout_load_menu()
        self._layout_header_btn.setMenu(self._layout_menu)
        self._layout_header_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        self._settings_header_btn = QToolButton()
        self._settings_header_btn.setObjectName("HeaderActionButton")
        self._settings_header_btn.setText("⚙")
        self._settings_header_btn.setToolTip(
            "Preferences: theme, include subfolders default, default destination, move confirmation."
        )
        self._settings_header_btn.clicked.connect(self._open_settings_dialog)
        self._blender_jobs_header_btn = QToolButton()
        self._blender_jobs_header_btn.setObjectName("HeaderActionButton")
        self._blender_jobs_header_btn.setText("Jobs")
        self._blender_jobs_header_btn.setToolTip(
            "Blender bridge: job history, pending queue, cancel pending, open outputs."
        )
        self._blender_job_menu = QMenu(self)
        self._blender_job_menu.addAction("Job history…", self._open_blender_job_history_dialog)
        self._blender_job_menu.addAction("Pending queue…", self._open_blender_pending_queue_dialog)
        self._blender_job_menu.addAction(
            "Refresh thumbnails",
            self._on_refresh_thumbnails,
        )
        self._blender_job_menu.addAction(
            "Clear thumbnail cache",
            self._on_clear_thumbnail_cache,
        )
        self._blender_job_menu.addSeparator()
        self._blender_job_menu.addAction(
            "Refresh metadata for current view",
            self._on_refresh_metadata_for_view,
        )
        self._blender_job_menu.addAction(
            "Clear metadata cache",
            self._on_clear_metadata_cache,
        )
        self._blender_job_menu.addAction(
            "Prune metadata cache (30 days)…",
            self._on_prune_metadata_cache,
        )
        self._blender_job_menu.addAction(
            "Rebuild archive manifest for selection",
            self._on_rebuild_archive_manifest_selection,
        )
        self._blender_job_menu.addSeparator()
        self._blender_job_menu.addAction(
            "Clean old thumbnail jobs…", self._on_bridge_cleanup_clean_old_jobs
        )
        self._blender_job_menu.addAction(
            "Delete failed thumbnail jobs…",
            self._on_bridge_cleanup_failed_only,
        )
        self._blender_job_menu.addAction(
            "Delete completed thumbnail jobs…",
            self._on_bridge_cleanup_completed_only,
        )
        self._blender_job_menu.addAction(
            "Open bridge storage folder",
            self._on_bridge_open_storage_folder,
        )
        self._blender_job_menu.addSeparator()
        self._cancel_all_pending_action = self._blender_job_menu.addAction(
            "Cancel all pending", self._cancel_all_blender_pending
        )
        self._blender_jobs_header_btn.setMenu(self._blender_job_menu)
        self._blender_jobs_header_btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self._help_header_btn = QToolButton()
        self._help_header_btn.setObjectName("HeaderActionButton")
        self._help_header_btn.setText("?")
        self._help_header_btn.setToolTip(
            f"About {APP_NAME}: app name, version, and The Yard suite context."
        )
        header_right.addWidget(self._layout_header_btn)
        header_right.addWidget(self._settings_header_btn)
        header_right.addWidget(self._blender_jobs_header_btn)
        header_right.addWidget(self._help_header_btn)
        header_right_w = QWidget()
        header_right_w.setLayout(header_right)
        brand_header = BrandHeader(
            app_name=APP_NAME,
            subtitle="Find and organize your files safely",
            icon_path=self._header_icon_path,
            right_widget=header_right_w,
        )
        main_v.addWidget(brand_header)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        self._left_panel = self._build_left_panel()
        self._center_panel = self._build_center_panel()
        self._right_panel = self._build_right_panel(dest_browse=dest_browse)
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.setObjectName("MainWorkspaceSplitter")
        self._main_splitter.setChildrenCollapsible(False)
        self._main_splitter.addWidget(self._left_panel)
        self._main_splitter.addWidget(self._center_panel)
        self._main_splitter.addWidget(self._right_panel)
        self._main_splitter.setStretchFactor(0, 0)
        self._main_splitter.setStretchFactor(1, 1)
        self._main_splitter.setStretchFactor(2, 0)
        self._main_splitter.setSizes([310, 720, RIGHT_PANEL_WIDTH])
        body_layout.addWidget(self._main_splitter, 1)
        main_v.addWidget(body, 1)

        root.setLayout(main_v)
        self.setCentralWidget(root)

    def _update_ui_state(self, *, refresh_inspector: bool = True) -> None:
        """
        Refresh all UI that depends on the working set, filters, selection,
        destination, or scan state (labels and button enablement).

        When *refresh_inspector* is False (e.g. filter-only refreshes after ``Name contains`` debounce),
        skip the inspector to avoid redundant decode work until selection signals run.
        """
        self._update_source_label()
        self._update_source_mode_hint()
        self._refresh_source_stats_line()
        self._update_result_summary_label()
        self._update_current_view_count_label()
        self._update_action_buttons()
        self._update_move_summary()
        self._asset_inspector.set_generate_missing_enabled(bool(self._current_source))
        self._asset_inspector.set_blender_thumbnail_actions_enabled(
            self._asset_mode == ASSET_MODE_3D
        )
        self._asset_inspector.configure_for_asset_mode(
            images_priority=(self._asset_mode == ASSET_MODE_IMAGES)
        )
        if refresh_inspector:
            self._update_asset_inspector()
        self._refresh_tag_editor_for_selection()
        self._refresh_favorite_toggle_for_selection()
        self._collections.refresh_selection()
        self._housekeeping.refresh_selection()
        self._sync_center_welcome_vs_browser()
        self._refresh_status_counts_strip()

    def _refresh_status_counts_strip(self) -> None:
        """Keep Indexed / Visible / Selected in sync without changing the workflow label."""
        self._status_stats_label.setText(self._footer_counts_strip())

    def _footer_counts_strip(self) -> str:
        """Production counts strip (Prime hints, filter notes, optional verbose diagnostics)."""
        counts = FooterCounts(
            len(self._all_records),
            len(self._view_records),
            len(self.selected_records()),
        )
        prime_mode = prime_mode_label(
            prime_active=self._prime_perf_active,
            network_like=self._prime_network_like,
        )
        prime_hint: str | None = None
        if self._prime_perf_active and not self._is_scanning:
            prime_hint = prime_mode_hint(
                prime_active=True,
                network_like=self._prime_network_like,
            )
        verbose = ""
        if verbose_footer_enabled():
            snap = self._thumb_controller.paint_diagnostics().snapshot()
            verbose = format_verbose_diagnostics(snap)
        return format_counts_strip(
            counts,
            prime_mode=prime_mode,
            prime_hint=prime_hint,
            filter_note=self._filter_footer_note,
            failed_thumbnails=self._session_thumb_failure_count,
            verbose_diagnostics=verbose,
        )

    def _refresh_blender_readiness_label(self) -> None:
        """
        Set the permanent Bridge line from settings + path discovery only (no --version).

        Transient Running / Complete / Failed lines still use :meth:`_set_blender_job_status`.
        """
        resolved = find_blender_executable(self._settings_service)
        label = describe_blender_readiness(self._settings_service, resolved)
        self._status_blender_label.setText(format_bridge_footer(readiness=label))

    def _load_raster_pixmap_for_inspector(self, path: Path, max_side: int) -> QPixmap | None:
        """Load a raster image as a pixmap for the inspector (Pillow), or ``None`` on failure."""
        try:
            from PIL import Image
        except ImportError:
            return None
        try:
            with Image.open(path) as image:
                image.load()
                preview = image.copy()
                preview.thumbnail((max_side, max_side))
                rgba = preview.convert("RGBA")
                buf = io.BytesIO()
                rgba.save(buf, format="PNG")
                pixmap = QPixmap()
                if pixmap.loadFromData(buf.getvalue(), b"PNG") and not pixmap.isNull():
                    return pixmap
        except (OSError, ValueError, TypeError):
            return None
        return None

    def _inspector_raster_pixel_size(self, path: Path) -> tuple[int, int] | None:
        """Best-effort width × height for a raster image (Pillow preferred, Qt fallback)."""
        try:
            from PIL import Image

            with Image.open(path) as im:
                w, h = im.size
                if w > 0 and h > 0:
                    return (int(w), int(h))
        except (OSError, ValueError, TypeError):
            pass
        try:
            from PySide6.QtGui import QImage

            img = QImage(str(path))
            if not img.isNull() and img.width() > 0 and img.height() > 0:
                return (int(img.width()), int(img.height()))
        except (TypeError, ValueError):
            pass
        return None

    def _inspector_preview_pixmap(self, record: FileRecord) -> QPixmap:
        """Large preview: image file via Pillow if possible, else Blender thumb or default icon."""
        path = record.path
        if not path.is_file():
            return QPixmap()
        ext = path.suffix.lower()
        if ext in SUPPORTED_IMAGE_EXTENSIONS:
            pm = self._load_raster_pixmap_for_inspector(path, 280)
            if pm is not None and not pm.isNull():
                return pm
            # Fallback: Qt image loader (keeps UI functional if Pillow is unavailable).
            from PySide6.QtGui import QImage

            img = QImage(str(path))
            if not img.isNull():
                scaled = img.scaled(
                    280,
                    280,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                pm2 = QPixmap.fromImage(scaled)
                if not pm2.isNull():
                    return pm2
        from meshcorral.ui.layout_constants import INSPECTOR_PREVIEW_FRAME_PX

        return self._thumb_controller.large_inspector_preview(
            record, max_side=INSPECTOR_PREVIEW_FRAME_PX
        )

    def _metadata_summary_for_record(self, record: FileRecord) -> AssetMetadataSummary:
        """Return cached or base metadata summary (safe on UI thread)."""
        existing = self._metadata_registry.get(record.path)
        if existing is not None:
            return existing
        cache_bits: list[str] = []
        if self._thumb_controller.ready_cache().is_ready(record.path):
            cache_bits.append("READY")
        if self._thumb_controller.has_index(record):
            cache_bits.append("indexed")
        base = build_base_summary(
            record,
            archive_cache=self._archive_manifest_cache,
            thumbnail_render_profile=self._thumb_controller.quality_profile().display_label,
            thumb_cache_bits=", ".join(cache_bits) if cache_bits else "pending",
        )
        self._metadata_registry.put(base)
        return base

    def _ensure_geometry_metadata_thread(self) -> bool:
        """Start the geometry worker thread on first use; True when it is running."""
        thr = self._geometry_meta_thread
        if thr is None:
            return False
        try:
            if not thr.isRunning():
                thr.start()
            return True
        except RuntimeError:
            logger.debug("geometry metadata thread unavailable; skipping background stats")
            self._geometry_meta_thread = None
            return False

    def _schedule_geometry_metadata(self, record: FileRecord) -> None:
        """Queue background STL/OBJ geometry stats for the inspector selection."""
        if self._shutting_down or self._geometry_meta_runner is None:
            return
        if not is_mesh_geometry_extension(record.extension or record.path.suffix):
            return
        if not self._ensure_geometry_metadata_thread():
            return
        path_s = str(record.path)
        if self._geometry_meta_path_pending == path_s:
            return
        self._geometry_meta_path_pending = path_s
        size = int(record.size_bytes) if record.size_bytes is not None else -1
        from PySide6.QtCore import QMetaObject, Q_ARG

        QMetaObject.invokeMethod(
            self._geometry_meta_runner,
            "extract_for_path",
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(str, path_s),
            Q_ARG(int, size),
            Q_ARG(bool, True),
        )

    def _apply_render_geometry_backfill(self, source_path: Path) -> None:
        """Merge mesh stats from a native render when geometry was loaded for preview."""
        summary_obj = self._native_thumb_queue.pop_geometry_summary(source_path)
        if not isinstance(summary_obj, AssetMetadataSummary):
            return
        merged = self._metadata_registry.merge(summary_obj)
        rec = self._record_for_source_path(source_path)
        size_bytes: int | None = None
        if rec is not None and rec.size_bytes is not None:
            size_bytes = int(rec.size_bytes)
        log_metadata_snapshot(
            merged,
            size_bytes=size_bytes,
            preview_ready=self._thumb_controller.ready_cache().is_ready(source_path),
        )
        recs = self.selected_records()
        if len(recs) == 1 and recs[0].path == source_path:
            self._update_asset_inspector()

    def _on_geometry_metadata_ready(self, path_s: str, summary_obj: object) -> None:
        """Merge worker geometry results and refresh inspector when still selected."""
        if not isinstance(summary_obj, AssetMetadataSummary):
            return
        merged = self._metadata_registry.merge(summary_obj)
        path = Path(path_s)
        rec = self._record_for_source_path(path)
        size_bytes: int | None = None
        if rec is not None and rec.size_bytes is not None:
            size_bytes = int(rec.size_bytes)
        log_metadata_snapshot(
            merged,
            size_bytes=size_bytes,
            preview_ready=self._thumb_controller.ready_cache().is_ready(path),
        )
        self._geometry_meta_path_pending = ""
        recs = self.selected_records()
        if len(recs) == 1 and str(recs[0].path) == path_s:
            self._update_asset_inspector()

    def _stop_geometry_metadata_thread(self, *, wait_ms: int = 3000) -> None:
        """
        Stop the geometry metadata worker thread during shutdown.

        The thread is a child of this window, so it must be finished before Qt destroys
        the window — otherwise Qt logs ``QThread: Destroyed while thread is still
        running`` and the runner is torn down under the worker's feet.
        """
        thr = self._geometry_meta_thread
        self._geometry_meta_thread = None
        self._geometry_meta_runner = None
        if thr is None:
            return
        try:
            if not thr.isRunning():
                return
            thr.requestInterruption()
            thr.quit()
            if not thr.wait(max(0, int(wait_ms))):
                logger.info(
                    "MeshStager shutdown: geometry metadata thread did not quit within %s ms",
                    wait_ms,
                )
        except RuntimeError:
            logger.debug("geometry metadata thread already stopped")

    def _update_asset_inspector(self) -> None:
        """Fill the asset inspector from the current selection (table or gallery)."""
        records = self.selected_records()
        if not records:
            self._asset_inspector.show_empty(session_active=bool(self._current_source))
            return
        if len(records) > 1:
            mesh_n = sum(
                1 for r in records if r.path.suffix.lower() in MESH_THUMBNAIL_EXTENSIONS
            )
            self._asset_inspector.show_multi(count=len(records), mesh_count=mesh_n)
            return

        record = records[0]
        summary = self._metadata_summary_for_record(record)
        self._schedule_geometry_metadata(record)
        path = record.path
        ext_l_raw = record.extension.strip().lower()
        if ext_l_raw and not ext_l_raw.startswith("."):
            ext_l_norm = f".{ext_l_raw}"
        else:
            ext_l_norm = ext_l_raw or path.suffix.lower()

        tags, meta_body, meta_copy = self._thumb_controller.inspector_metadata_bundle(
            record
        )
        rich_copy = "\n".join(summary.copy_block_lines())
        if rich_copy.strip():
            meta_copy = f"{meta_copy}\n\n{rich_copy}".strip() if meta_copy.strip() else rich_copy
        size_s = format_file_size_display(record.size_bytes)
        mod_s = format_local_modified_display(record.modified_time)
        missing = not path.is_file()
        ext_display = (
            ext_l_norm.upper()
            if ext_l_norm.startswith(".")
            else (ext_l_norm or "—").upper()
        )

        raster_ext = ext_l_norm in SUPPORTED_IMAGE_EXTENSIONS
        mesh_thumb_ext = ext_l_norm in MESH_THUMBNAIL_EXTENSIONS

        preview_kind = preview_kind_label_for_path(ext_l_norm)
        preview_subline = ""
        preview_blocked: str | None = None

        in_img_mode = self._asset_mode == ASSET_MODE_IMAGES
        if not missing and in_img_mode and ext_l_norm not in SUPPORTED_IMAGE_EXTENSIONS:
            blocked = empty_state_spec(PREVIEW_UNAVAILABLE)
            preview_blocked = f"{blocked.title}\n{blocked.body}"

        pm = QPixmap()
        if not missing and preview_blocked is None:
            pm = self._inspector_preview_pixmap(record)

        if preview_blocked is None and raster_ext and not missing:
            preview_kind = preview_kind_label_for_path(ext_l_norm)
            if pm.isNull():
                preview_subline = "Could not load image preview"
            else:
                wh = self._inspector_raster_pixel_size(path)
                preview_subline = (
                    f"{wh[0]:,} × {wh[1]:,} px" if wh else "Dimensions unknown"
                )
        tpath = self._thumb_controller.blender_thumbnail_path(record)
        has_bthumb = tpath is not None and tpath.is_file() and not missing

        if preview_blocked is None and mesh_thumb_ext and not missing:
            preview_kind = preview_kind_label_for_path(ext_l_norm)
            if not has_bthumb:
                preview_subline = "No thumbnail on disk yet — use Generate or Retry below."
        if preview_blocked is None and not raster_ext and not mesh_thumb_ext and not missing:
            preview_subline = ext_display

        thumb_s = str(tpath) if tpath is not None else ""
        can_thumb = mesh_thumb_ext and not missing

        health = self._thumb_controller.thumb_health(record)
        visual = self._thumb_controller.visual_state(record)
        failure_info = self._thumb_controller.thumb_failure_info(record)
        failure_msg = failure_info.error_message if failure_info is not None else None
        generating, queued, decoding = self._thumb_controller.thumb_row_decode_flags(
            record
        )
        kind_none = None
        if health == ThumbHealth.FAILED_THUMBNAIL:
            kind_none = classify_bridge_error_kind(failure_msg)
        elif visual == ThumbVisualState.FAILED:
            kind_none = "corrupt"
        thumb_perf_deferred = (
            self._prime_perf_active
            and mesh_thumb_ext
            and not missing
            and health == ThumbHealth.PENDING
            and visual == ThumbVisualState.PLACEHOLDER
            and not has_bthumb
        )
        std_state = standard_copy_for_inspector(
            health=health,
            visual=visual,
            generating=generating,
            queued=queued,
            decoding=decoding,
            deferred=thumb_perf_deferred,
            bridge_error_message=failure_msg,
        )
        ux = build_preview_thumb_ux(
            health=health,
            visual=visual,
            generating=generating,
            queued=queued,
            decoding=decoding,
            can_mesh_thumbnail=can_thumb,
            has_blender_thumbnail=has_bthumb,
            bridge_error_message=failure_msg,
            thumb_perf_deferred=thumb_perf_deferred,
        )
        cache_bits: list[str] = []
        if self._thumb_controller.ready_cache().is_ready(record.path):
            cache_bits.append("READY")
        if self._thumb_controller.has_index(record):
            cache_bits.append("indexed")
        cache_status = summary.cache_status_display()
        if cache_bits and cache_status == "—":
            cache_status = ", ".join(cache_bits)
        meta_status = summary.metadata_status_display()
        meta_prov = summary.metadata_source_display()
        if summary.has_geometry_fields() and meta_prov and meta_prov != meta_status:
            meta_src = f"{meta_status} · {meta_prov}"
        else:
            meta_src = meta_status
        asset_mode_label = (
            "Images / Textures"
            if self._asset_mode == ASSET_MODE_IMAGES
            else "3D / DCC Assets"
        )
        archive_display = summary.archive_members_display()
        if archive_display == "—" and ext_l_norm in (".zip", ".7z", ".rar"):
            archive_display = "Archive container (browse via scan)"
        unsupported_reason = (
            REASON_UNSUPPORTED if health == ThumbHealth.UNSUPPORTED else ""
        )
        prof = (
            summary.thumbnail_render_profile_display()
            or self._thumb_controller.quality_profile().display_label
        )
        route_plan = route_thumbnail(
            thumbnail_path_for_record(record),
            self._settings_service,
            native_health=self._native_renderer_health,
        )
        fallback_display = (route_plan.fallback_reason or "").strip()
        if route_plan.backend == "blender" and fallback_display:
            backend_l = "Blender fallback"
        else:
            backend_l = infer_thumbnail_backend_label(prof)
        failure_display = ""
        if failure_msg:
            failure_display = failure_msg.strip().split("\n", 1)[0].strip()[:400]
        suggested = suggested_action_for_preview(
            health=health,
            visual=visual,
            can_mesh_thumbnail=can_thumb,
            has_thumbnail=has_bthumb,
            thumb_perf_deferred=thumb_perf_deferred,
            failure_kind=kind_none,
        )

        display_name = truncate_filename(record.name)
        self._asset_inspector.show_single(
            name=display_name,
            path_str=str(path),
            filename_full=record.name,
            extension=ext_display,
            size_display=size_s,
            modified_display=mod_s,
            tags=tags,
            metadata_block=meta_body,
            metadata_copy_text=meta_copy,
            pixmap=pm,
            missing_file=missing,
            can_generate_blender_thumbnail=can_thumb,
            has_blender_thumbnail=has_bthumb,
            blender_thumbnail_path=thumb_s,
            preview_kind=preview_kind,
            preview_subline=preview_subline,
            preview_blocked_message=preview_blocked,
            folder_display=record.parent_folder or "—",
            asset_mode_display=asset_mode_label,
            metadata_source_display=meta_src,
            dimensions_display=summary.dimensions_display(),
            face_count_display=summary.face_count_display(),
            vertex_count_display=summary.vertex_count_display(),
            watertight_display=summary.watertight_display(),
            mesh_density_display=summary.mesh_density_display(),
            archive_members_rich_display=archive_display,
            metadata_cache_display=summary.cache_status_display(),
            thumb_status_display=std_state.title,
            renderer_profile_display=prof,
            mesh_health_display=summary.geometry_diagnostics_display(),
            archive_member_count_display=archive_display,
            unsupported_reason_display=unsupported_reason,
            cache_status_display=cache_status,
            deferred_reason_display=summary.deferred_reason or "",
            thumbnail_state_display=std_state.title,
            preview_thumb_headline=std_state.title,
            preview_thumb_body=std_state.subtitle,
            preview_show_retry_thumbnail=ux.show_retry,
            preview_retry_button_label=ux.retry_button_label,
            thumbnail_backend_display=backend_l,
            thumbnail_failure_reason_display=failure_display,
            thumbnail_fallback_reason_display=fallback_display,
            thumbnail_suggested_action_display=suggested,
            metadata_deferred=bool((summary.deferred_reason or "").strip()),
        )

    def _inspector_open_file(self) -> None:
        self._open_selected_file()

    def _inspector_open_folder(self) -> None:
        recs = self.selected_records()
        if not recs:
            return
        p = recs[0].path
        folder = p.parent if p.is_file() else p
        try:
            subprocess.run(["explorer", str(folder)], check=False)
        except OSError as exc:
            QMessageBox.warning(self, "Explorer", f"Could not open folder: {exc}")

    def _inspector_copy_path(self) -> None:
        recs = self.selected_records()
        if not recs:
            return
        QApplication.clipboard().setText(str(recs[0].path))
        self._update_status(status_path_copied())

    def _inspector_batch_copy_paths(self) -> None:
        recs = self.selected_records()
        if not recs:
            return
        QApplication.clipboard().setText("\n".join(str(r.path) for r in recs))
        self._update_status(f"Copied {len(recs)} path(s) to the clipboard.")

    def _on_inspector_metadata_copied(self) -> None:
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(status_metadata_copied(), 4000)

    def _on_generate_missing_thumbnails_for_view(self) -> None:
        """
        Queue Blender thumbnails for visible .stl / .obj / .fbx rows that are not in the index yet.
        """
        if self._asset_mode != ASSET_MODE_3D:
            sb = self.statusBar()
            if sb is not None:
                sb.showMessage(
                    "Blender thumbnails are available in 3D Asset Mode (.stl / .obj / .fbx)",
                    6000,
                )
            return
        if not self._current_source:
            if self.statusBar() is not None:
                self.statusBar().showMessage(status_scan_folder_first(), 4000)
            return
        mesh_rows = [
            r for r in self._view_records if r.path.suffix.lower() in (".stl", ".obj", ".fbx")
        ]
        if not mesh_rows:
            sb = self.statusBar()
            if sb is not None:
                sb.showMessage("No 3D files in current view.", 6000)
            return

        if self._lazy_thumb_health.lazy_enabled():
            self._lazy_thumb_health.resolve_many(mesh_rows)

        already = 0
        queued = 0
        missing_file = 0
        if self._prime_perf_active:
            stats = self._enqueue_prime_bridge_tiers(
                include_idle=False,
                origin=JobOrigin.MANUAL_BATCH,
            )
            queued = stats.enqueued
            already = sum(1 for r in mesh_rows if self._thumb_controller.has_index(r))
        else:
            for r in mesh_rows:
                if not r.path.is_file():
                    missing_file += 1
                    continue
                if self._thumb_controller.has_index(r):
                    already += 1
                    continue
                ok, _msg, reject = self._try_enqueue_thumbnail_record(
                    r,
                    origin=JobOrigin.MANUAL_BATCH,
                    for_auto_enqueue=False,
                )
                if ok:
                    queued += 1
                elif reject == BridgeEnqueueReject.CAP:
                    break
        self._note_thumb_jobs_enqueued(queued)
        if queued and self._lazy_thumb_health.lazy_enabled():
            self._emit_thumb_health_rows(mesh_rows)
        self._on_bridge_queue_count_changed(self._bridge_queue.queue_length())
        sb = self.statusBar()
        if sb is None:
            return
        if queued:
            sb.showMessage(
                f"Queued {queued} missing 3D thumbnail(s) for the current view.",
                8000,
            )
        else:
            if missing_file:
                sb.showMessage("No thumbnails queued (files were missing on disk).", 7000)
            elif already:
                sb.showMessage(
                    "No thumbnails queued (all visible 3D files already have thumbnails).",
                    7000,
                )
            else:
                sb.showMessage("No thumbnails queued.", 5000)

    def _current_search_mode(self) -> str:
        """Current Asset Mode from the combo (always ``3d`` or ``images``)."""
        data = self._search_mode_combo.currentData()
        if data == ASSET_MODE_IMAGES:
            return ASSET_MODE_IMAGES
        return ASSET_MODE_3D

    def _empty_scan_prompt_for_mode(self) -> str:
        """Hint under source stats before the first scan."""
        return empty_state_hint_lines(empty_state_spec(FRESH_LAUNCH))

    def _update_source_mode_hint(self) -> None:
        """Show mode-specific empty copy under source stats when there is no working set."""
        if self._current_source:
            self._source_mode_hint.setText("")
            self._source_mode_hint.hide()
            return
        if self._scan_user_canceled_hint:
            self._source_mode_hint.setText(
                empty_state_hint_lines(empty_state_spec(SCAN_CANCELED))
            )
            self._source_mode_hint.show()
            return
        unavailable = (self._unavailable_source_text or "").strip()
        if unavailable:
            spec = empty_state_spec(SOURCE_UNAVAILABLE)
            self._source_mode_hint.setText(
                f"{spec.title}\n{spec.body}"
            )
            self._source_mode_hint.show()
            return
        if self._selected_source_is_valid():
            self._source_mode_hint.setText(
                empty_state_hint_lines(empty_state_spec(READY_TO_SCAN))
            )
            self._source_mode_hint.show()
            return
        self._source_mode_hint.setText(self._empty_scan_prompt_for_mode())
        self._source_mode_hint.show()

    def _update_source_label(self) -> None:
        if self._is_scanning and self._pending_scan_path:
            self._source_path_label.setText(self._pending_scan_path)
            return
        selected = (self._selected_source_path or "").strip()
        if selected:
            self._source_path_label.setText(selected)
            return
        if not self._current_source:
            unavailable = (getattr(self, "_unavailable_source_text", "") or "").strip()
            if unavailable:
                self._source_path_label.setText(unavailable)
            else:
                self._source_path_label.setText("No source selected")
            return
        self._source_path_label.setText(str(self._current_source))

    def _asset_mode_display_label(self, mode: str) -> str:
        """Human-readable Asset Mode label matching the combo entries."""
        if mode == ASSET_MODE_IMAGES:
            return "Images / Textures"
        return "3D / DCC Assets"

    def _selected_source_is_valid(self) -> bool:
        """True when ``_selected_source_path`` points at an existing directory."""
        selected = (self._selected_source_path or "").strip()
        if not selected:
            return False
        try:
            return Path(selected).is_dir()
        except OSError:
            return False

    def _persist_selected_source(self, folder: str) -> None:
        """Persist source choice and reopen an existing complete catalog."""
        folder = folder.strip()
        if not folder:
            return
        self._selected_source_path = folder
        self._last_scan_folder = folder
        self._unavailable_source_text = ""
        QSettings().setValue("paths/last_scan_folder", folder)
        self._update_source_label()
        self._refresh_source_button_states()
        QTimer.singleShot(0, self._reopen_completed_source)

    def _reopen_completed_source(self) -> None:
        """Schedule only known catalogs; first-time folders retain Scan Source UX."""
        if self._shutting_down or self._is_scanning or self._scan_launch_pending:
            return
        source = self._selected_source_path
        if not source:
            return
        cache = self._ensure_metadata_cache()
        if cache.has_complete_source(source, self._include_subfolders_checkbox.isChecked(),
                                     supported_extensions_for_asset_mode(self._asset_mode)):
            self._run_scan(source)

    def _refresh_source_button_states(self) -> None:
        """Sync Browse / Scan tooltips and Scan enabled state with selected source."""
        if not hasattr(self, "_scan_source_btn") or self._scan_source_btn is None:
            return
        if hasattr(self, "_browse_source_btn") and self._browse_source_btn is not None:
            self._browse_source_btn.setToolTip("Choose a source folder.")
            self._browse_source_btn.setEnabled(True)
        valid = self._selected_source_is_valid()
        if self._is_scanning:
            self._scan_source_btn.setToolTip("A scan is in progress. Wait for it to finish.")
        elif valid:
            self._scan_source_btn.setToolTip(
                "Scan selected source using current Asset Mode."
            )
        else:
            self._scan_source_btn.setToolTip("Choose a source folder before scanning.")
        if not self._is_scanning:
            self._scan_source_btn.setEnabled(valid)

    def _begin_idle_session(self) -> None:
        """
        Start with no active source loaded (empty gallery / table).

        Preserves ``_last_scan_folder`` / ``paths/last_scan_folder`` for Browse
        dialog start path and manual warm-reopen. Does not set
        ``_selected_source_path`` or schedule a scan.
        """
        self._selected_source_path = ""
        self._current_source = ""
        self._unavailable_source_text = ""
        self._update_source_label()
        self._refresh_source_button_states()

    def _restore_persisted_source(self) -> None:
        """
        Re-populate the Source panel from ``paths/last_scan_folder`` without auto-scanning.

        Kept for tests and callers that want to surface the recent path as the
        selected source. Fresh application launch uses :meth:`_begin_idle_session`
        instead so startup stays idle until the user Browses or Scans.

        - Existing folder: ``_selected_source_path`` is set and the label shows the path.
          ``_current_source`` (the source backing the active rows) stays empty because
          no scan has run yet at restore time.
        - Missing folder: the label shows "Last source unavailable: <path>" and both
          ``_selected_source_path`` and ``_current_source`` stay empty so all
          "no source" UI affordances remain.
        - Empty / unset: no change; the label stays at "No source selected".
        """
        last = (self._last_scan_folder or "").strip()
        self._unavailable_source_text = ""
        if not last:
            self._update_source_label()
            return
        try:
            path = Path(last)
            exists = path.exists() and path.is_dir()
        except OSError:
            exists = False
        if exists:
            self._selected_source_path = str(path)
            logger.debug("restored persisted source: %s", self._selected_source_path)
        else:
            self._unavailable_source_text = f"Last source unavailable: {last}"
            logger.info("persisted source no longer available: %s", last)
        self._update_source_label()
        self._refresh_source_button_states()

    def _on_search_text_changed(self, _text: str) -> None:
        """Restart debounce: ``_apply_filters`` runs after typing pauses (Name contains only)."""
        self._filter_search_debounce_timer.stop()
        self._filter_search_debounce_timer.start(filter_search_debounce_milliseconds())

    def _apply_filters_debounced_fire(self) -> None:
        """Single-shot timer callback after search typing pause."""
        self._apply_filters(refresh_inspector=False)

    def _filter_status_message(self, match_count: int) -> str:
        """Workflow label after a filter pass."""
        if self._warm_catalog_active and self._is_scanning:
            return "Verifying source…"
        query = (self._search_edit.text() or "").strip()
        indexed = len(self._all_records)
        workflow, suffix = format_filter_footer(
            visible=match_count,
            indexed=indexed,
            query=query,
        )
        if not query and match_count >= indexed:
            self._filter_footer_note = None
            return "Ready"
        self._filter_footer_note = suffix or None
        return workflow

    def _on_async_filter_results(self, result: object) -> None:
        """Apply a completed background filter pass (drops stale epochs)."""
        if not isinstance(result, FilterRunResult):
            return
        if result.epoch != self._async_filter_engine.current_epoch():
            return
        paths = self._selected_paths_for_selection_restore()
        self._commit_filter_view(
            result.records,
            paths=paths,
            refresh_inspector=self._filter_refresh_inspector_pending,
        )

    def _current_browse_sort_mode(self) -> str:
        """Active browse sort mode id from the header combo."""
        data = self._sort_combo.currentData()
        if data:
            return str(data)
        return DEFAULT_SORT_MODE

    def _on_browse_sort_changed(self, _index: int = 0) -> None:
        """Reorder the visible model when the user changes sort (no thumbnail regen)."""
        if self._is_initializing_ui or not self._view_records:
            return
        paths = self._selected_paths_for_selection_restore()
        sorted_view = sort_file_records(
            list(self._view_records),
            self._current_browse_sort_mode(),
        )
        self._apply_sorted_view(sorted_view, paths=paths)

    def _apply_sorted_view(
        self,
        view_records: list[FileRecord],
        *,
        paths: list[Path],
        refresh_inspector: bool = False,
    ) -> None:
        """Update table/gallery row order only (sort pass — no thumbnail enqueue)."""
        self._view_records = view_records
        self._model.set_rows(self._view_records)
        self._gallery_model.set_records(self._view_records)
        self._restore_selection_from_paths(paths)
        self._update_status(
            self._filter_status_message(len(self._view_records)),
            show_view_counts=True,
        )
        self._update_ui_state(refresh_inspector=refresh_inspector)

    def _commit_filter_view(
        self,
        view_records: list[FileRecord],
        *,
        paths: list[Path],
        refresh_inspector: bool,
    ) -> None:
        """Apply filtered rows to models in one batch (no thumbnail cache churn)."""
        sorted_records = sort_file_records(view_records, self._current_browse_sort_mode())
        self._view_records = sorted_records
        self._model.set_rows(self._view_records)
        self._gallery_model.set_records(self._view_records)
        self._restore_selection_from_paths(paths)
        if self._view_records and not self._did_initial_column_resize:
            self._table.resizeColumnsToContents()
            self._did_initial_column_resize = True
        self._apply_table_thumbnail_layout()
        self._update_status(
            self._filter_status_message(len(self._view_records)),
            show_view_counts=True,
        )
        self._schedule_viewport_thumb_pass()
        self._update_ui_state(refresh_inspector=refresh_inspector)

    def _stop_filter_search_debounce(self) -> None:
        """Cancel a pending debounced search apply (scan, reset, mode change, etc.)."""
        self._filter_search_debounce_timer.stop()

    def _update_current_view_count_label(self) -> None:
        """Header count: files currently shown in the table (after filters)."""
        visible = len(self._view_records)
        if visible == 1:
            self._current_view_count_label.setText("1 file")
        else:
            self._current_view_count_label.setText(f"{visible:,} files")

    def _update_result_summary_label(self) -> None:
        """Secondary line under the current-view header (filter / empty states)."""
        total = len(self._all_records)
        visible = len(self._view_records)

        collection_spec = self._collections.empty_spec() if visible == 0 else None
        if collection_spec is not None:
            self._view_hint_label.setText(empty_state_hint_lines(collection_spec))
            self._view_hint_label.show()
            return

        if not self._current_source:
            self._view_hint_label.hide()
            self._view_hint_label.setText("")
            return

        if total == 0:
            self._view_hint_label.setText(
                empty_state_hint_lines(empty_state_spec(NO_ASSETS_FOUND))
            )
            self._view_hint_label.show()
            return

        if visible == 0:
            spec = empty_state_spec(NO_MATCHING_RESULTS)
            extra = (
                f"The scan found {total:,} file(s) in this folder."
            )
            self._view_hint_label.setText(
                f"{spec.title}\n\n{spec.body}\n\n{extra}"
            )
            self._view_hint_label.show()
            return

        perf_msg = perf_status_message(
            self._scan_root_path(),
            total,
            self._last_scan_elapsed_s,
        )
        if perf_msg:
            self._view_hint_label.setText(perf_msg)
            self._view_hint_label.show()
            return

        self._view_hint_label.hide()
        self._view_hint_label.setText("")

    def _update_action_buttons(self) -> None:
        has_source = bool(self._current_source)
        has_visible = bool(self._view_records)
        has_selection = bool(self.selected_records())
        has_destination = bool((self._dest_edit.text() or "").strip().rstrip("\\/"))

        scan_valid = self._selected_source_is_valid()
        if self._is_scanning:
            self._scan_source_btn.setText("Scanning…")
            self._scan_source_btn.setEnabled(False)
            self._welcome_scan_btn.setText("Scanning…")
            self._welcome_scan_btn.setEnabled(False)
            self._welcome_scan_btn.setToolTip("A scan is in progress. Wait for it to finish.")
        else:
            self._scan_source_btn.setText("Scan Source")
            self._scan_source_btn.setEnabled(scan_valid)
            self._welcome_scan_btn.setText("Scan Source")
            self._welcome_scan_btn.setEnabled(scan_valid)
            self._welcome_scan_btn.setToolTip(
                "Scan the selected source folder (use Browse… in the left panel to choose one)."
            )
        self._refresh_source_button_states()

        can_export = has_source and has_visible
        self._export_top_btn.setEnabled(can_export)
        if can_export:
            self._export_top_btn.setToolTip(
                "Save the current filtered table (visible rows only) to a CSV file."
            )
        else:
            self._export_top_btn.setToolTip(
                _reason_export_disabled(has_source=has_source, has_visible=has_visible)
            )

        can_transfer = has_source and has_visible and has_selection and has_destination
        self._move_btn.setEnabled(can_transfer)
        self._copy_to_btn.setEnabled(can_transfer)
        transfer_block = _reason_transfer_buttons_disabled(
            has_source=has_source,
            has_visible=has_visible,
            has_selection=has_selection,
            has_destination=has_destination,
        )
        if can_transfer:
            self._move_btn.setToolTip(
                "Move selected files to the destination folder (dry-run preview first)."
            )
            self._copy_to_btn.setToolTip(
                "Copy selected files to the destination folder (dry-run preview first)."
            )
        else:
            self._move_btn.setToolTip(transfer_block)
            self._copy_to_btn.setToolTip(transfer_block)

        can_file_action = has_source and has_selection
        for button in (self._reveal_btn, self._copy_path_btn):
            button.setVisible(can_file_action)
            button.setEnabled(can_file_action)
            button.setMaximumHeight(16777215 if can_file_action else 0)
        file_block = _reason_file_actions_disabled(
            has_source=has_source, has_selection=has_selection
        )
        if can_file_action:
            self._reveal_btn.setToolTip(
                "Open the first selected file in File Explorer."
            )
            self._copy_path_btn.setToolTip(
                "Copy the full path of the first selected file to the clipboard."
            )
        else:
            self._reveal_btn.setToolTip(file_block)
            self._copy_path_btn.setToolTip(file_block)

    def _update_status(self, text: str, *, show_view_counts: bool = True) -> None:
        self._status_ready_label.setText(text)
        if show_view_counts:
            self._refresh_status_counts_strip()
        else:
            self._status_stats_label.setText("")

    def _refresh_source_stats_line(self) -> None:
        """Update the left-panel scan stats (count + duration) after the last scan."""
        if self._is_scanning:
            n = len(self._all_records)
            self._source_stats_label.setText(f"Indexing… {n:,} file{'s' if n != 1 else ''}")
            return
        if not self._current_source:
            self._source_stats_label.setText("—")
            return
        n = len(self._all_records)
        elapsed = self._last_scan_elapsed_s
        if elapsed is not None:
            self._source_stats_label.setText(
                f"Scanned {n:,} file{'s' if n != 1 else ''} in {elapsed:.2f}s"
            )
        else:
            self._source_stats_label.setText(
                f"{n:,} file{'s' if n != 1 else ''} in working set"
            )

    def _on_browse_source(self) -> None:
        """
        Browse Source button handler — pick or change the scan target folder.

        Updates ``_selected_source_path`` and persists to QSettings. If the folder
        already has a complete warm catalog, :meth:`_reopen_completed_source`
        schedules a warm verify (cached rows first). First-time folders still
        require an explicit Scan Source click.
        """
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select source folder or drive (e.g. E:\\)",
            self._last_scan_folder or self._selected_source_path or "",
        )
        if not folder:
            return
        self._persist_selected_source(folder)
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(
                "Source selected. Click Scan Source to scan with the current Asset Mode.",
                5000,
            )

    def _on_scan_source(self) -> None:
        """
        Scan Source button handler — scan the selected folder only.

        Requires a valid ``_selected_source_path`` (the button is disabled otherwise).
        If the stored path no longer exists, surface an unavailable message and open
        Browse so the user can pick a replacement.
        """
        timer = ScanStartupTimer()
        timer.mark("SCAN_START")
        if self._selected_source_is_valid():
            timer.mark("SCAN_VALIDATE_SOURCE")
            self._scan_launch_generation += 1
            launch_gen = self._scan_launch_generation
            self._scan_launch_pending = True
            self._update_scan_esc_shortcut()

            def on_confirmed(proceed: bool) -> None:
                if launch_gen != self._scan_launch_generation:
                    return
                if not proceed:
                    self._scan_launch_pending = False
                    self._update_scan_esc_shortcut()
                    return
                timer.mark("SCAN_LARGE_FOLDER_CHECK")
                QTimer.singleShot(
                    0,
                    lambda: self._deferred_run_scan_if_launched(
                        self._selected_source_path, launch_gen, timer
                    ),
                )

            self._confirm_large_folder_scan(
                self._selected_source_path, timer=timer, on_done=on_confirmed
            )
            return
        selected = (self._selected_source_path or "").strip()
        if selected:
            self._selected_source_path = ""
            self._unavailable_source_text = f"Selected source is unavailable: {selected}"
            self._update_source_mode_hint()
            self._update_source_label()
            self._refresh_source_button_states()
            sb = self.statusBar()
            if sb is not None:
                sb.showMessage(status_source_unavailable(), 5000)
            self._on_browse_source()

    def _on_search_mode_changed(self) -> None:
        """
        Persist Asset Mode, clear all scan results and selection, reset Type/Ext for the
        new mode, and require a fresh scan (no mixed 3D / image rows).

        During UI initialization / restore the handler does **not** clear the source,
        rows, or selection — it only keeps internal mode state and the category combo
        in sync. The post–Prime v0.7 startup path no longer impersonates a user mode
        switch.
        """
        new_mode = self._current_search_mode()
        if new_mode == self._asset_mode:
            return

        if self._is_initializing_ui:
            self._asset_mode = new_mode
            self._settings_service.set_search_mode(new_mode)
            self._rebuild_category_combo_for_asset_mode()
            return

        self._stop_filter_search_debounce()
        self._asset_mode = new_mode
        self._settings_service.set_search_mode(new_mode)

        self._search_edit.blockSignals(True)
        self._search_edit.clear()
        self._search_edit.blockSignals(False)

        self._rebuild_category_combo_for_asset_mode()

        self._thumb_filter_combo.blockSignals(True)
        self._thumb_filter_combo.setCurrentText(THUMB_FILTER_ALL)
        self._thumb_filter_combo.blockSignals(False)

        self._all_records = []
        self._view_records = []
        self._metadata_registry.clear()
        self._model.set_rows([])
        self._gallery_model.set_records([])
        # Clear *current scan source* (= source of the rows that just got cleared)
        # but preserve _selected_source_path so the user can re-scan the same folder
        # with the new mode's extension set.
        self._current_source = ""
        self._unavailable_source_text = ""
        self._last_scan_elapsed_s = None
        self._did_initial_column_resize = False
        self._rescan_after_mode_change = True
        self._scan_user_canceled_hint = False

        self._refresh_folder_options()
        self._clear_table_selection()
        self._update_source_label()
        self._refresh_source_button_states()
        self._asset_inspector.show_empty(
            session_active=bool(self._selected_source_path)
        )

        self._update_status("Ready", show_view_counts=True)
        self._update_ui_state()
        sb = self.statusBar()
        if sb is not None:
            mode_label = self._asset_mode_display_label(new_mode)
            if self._selected_source_path:
                sb.showMessage(
                    f"Asset Mode changed. Scan Source to reload this folder for "
                    f"{mode_label}.",
                    5000,
                )
            else:
                sb.showMessage(
                    f"Asset Mode changed. Choose a source folder to scan for "
                    f"{mode_label}.",
                    5000,
                )

    def _rebuild_category_combo_for_asset_mode(self) -> None:
        """Repopulate the Type and Ext controls for :attr:`_asset_mode` (e.g. after switching)."""
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        for label in ordered_category_labels_for_asset_mode(self._asset_mode):
            self.category_combo.addItem(label)
        self.category_combo.setCurrentText("All")
        self.category_combo.blockSignals(False)
        self._refresh_extension_options()

    def _scan_root_path(self) -> Path:
        """Current scan source as a path (empty path when unset)."""
        text = (self._current_source or "").strip()
        if not text:
            return Path()
        return Path(text)

    def _record_for_source_path(self, path: Path) -> FileRecord | None:
        """Find a working-set record for *path*, if present."""
        key = _norm_path_key(path)
        for record in self._all_records:
            if _norm_path_key(record.path) == key:
                return record
        return None

    def _update_prime_perf_mode(self) -> None:
        """Enable lazy thumbnail health when the working set looks large or remote."""
        root = self._scan_root_path()
        active = bool(self._current_source) and is_prime_perf_scan(
            root,
            len(self._all_records),
            self._last_scan_elapsed_s,
        )
        self._prime_perf_active = active
        self._lazy_thumb_health.set_lazy_enabled(active)
        network = is_network_like_path(root) if active else False
        self._prime_network_like = bool(network)
        self._scroll_velocity.set_network_like(self._prime_network_like)
        profile = remote_throttle_profile(network if active else False)
        self._viewport_thumb_interval_ms = int(profile.viewport_debounce_ms)
        self._thumb_controller.set_prime_perf_mode(active, network_like=network)
        if not active:
            self._thumb_controller.set_fast_scroll_suppressed(False)
            self._scroll_settle_timer.stop()
        self._bridge_queue.set_ui_quiet(active)
        self._bridge_queue.configure_backpressure(network_like=self._prime_network_like)
        self._thumb_controller.set_working_set_count(len(self._all_records))
        if active:
            self._lazy_thumb_health.clear()
            self._thumb_controller.set_record_visible_fn(self._is_record_in_visible_viewport)
            self._thumb_controller.set_visible_rows_fn(self._visible_view_row_indices)
        else:
            self._thumb_controller.set_record_visible_fn(None)
            self._thumb_controller.set_visible_rows_fn(None)
            self._thumb_batch_progress.finish()
            self._thumb_progress_timer.stop()
            self._bridge_idle_fill_timer.stop()

    def _touch_bridge_ui_activity(self) -> None:
        """Mark UI activity for idle-tier bridge fill gating (Prime v0.10)."""
        self._bridge_last_activity_monotonic = time.monotonic()

    def _sync_bridge_paint_diagnostics(self) -> None:
        """Refresh bridge queue counters in paint diagnostics."""
        if not self._prime_perf_active:
            return
        bridge_pending, bridge_running = self._bridge_queue.in_flight_load()
        diag = self._thumb_controller.paint_diagnostics()
        diag.sync_bridge_queue_stats(bridge_pending, bridge_running)
        diag.sync_native_queue_stats(self._native_thumb_queue.in_flight_count())

    def _viewport_bridge_tiers(self, *, include_idle_rows: bool) -> dict[BridgeJobTier, list[FileRecord]]:
        """Build selected/visible/preload/idle bridge tiers for the current view."""
        visible = self._visible_view_row_indices()
        total = len(self._view_records)
        prefetch_rows = directional_prefetch_row_indices(
            visible,
            total,
            direction=self._scroll_velocity.direction(),
            network_like=self._prime_network_like,
        )
        idle_rows = None
        if include_idle_rows:
            idle_rows = idle_background_row_indices(
                self._view_records,
                visible_row_indices=visible,
                prefetch_row_indices=prefetch_rows,
                selected_row=self._selected_view_row_index(),
            )
        return bridge_records_by_tier(
            self._view_records,
            visible_row_indices=visible,
            prefetch_row_indices=prefetch_rows,
            selected_row=self._selected_view_row_index(),
            idle_background_row_indices=idle_rows,
        )

    def _try_enqueue_thumbnail_record(
        self,
        record: FileRecord,
        *,
        origin: JobOrigin,
        manual_override: ThumbnailManualOverride = ThumbnailManualOverride.DEFAULT,
        for_auto_enqueue: bool = False,
        idle_tier: bool = False,
    ) -> tuple[bool, str, BridgeEnqueueReject]:
        """Route and enqueue a thumbnail job (native CPU or Blender Bridge)."""
        if for_auto_enqueue and not auto_enqueue_allowed(self._settings_service):
            return False, "Manual-only thumbnail preference", BridgeEnqueueReject.NOT_ROUTED

        source_path = thumbnail_path_for_record(record)
        if for_auto_enqueue and self._is_known_non_renderable_record(record, source_path):
            # Silent by design: this file already failed for a permanent reason.
            return (
                False,
                "Known non-renderable file; automatic thumbnail skipped.",
                BridgeEnqueueReject.NOT_ROUTED,
            )
        if not for_auto_enqueue and origin in (JobOrigin.MANUAL_SINGLE, JobOrigin.MANUAL_BATCH):
            self._forget_non_renderable_source(source_path)

        plan = route_thumbnail(
            source_path,
            self._settings_service,
            manual_override=manual_override,
            for_auto_enqueue=for_auto_enqueue,
            native_health=self._native_renderer_health,
        )
        diag = self._thumb_controller.paint_diagnostics()

        if idle_tier and plan.backend == "native":
            diag.note_blender_skipped_native_supported(1)
            return False, plan.reason, BridgeEnqueueReject.NOT_ROUTED
        if idle_tier and plan.backend == "blender" and not plan.eligible_for_blender_idle_fill:
            return False, plan.reason, BridgeEnqueueReject.NOT_ROUTED
        if plan.backend == "none":
            return False, plan.reason, BridgeEnqueueReject.NOT_ROUTED

        if (
            plan.backend == "blender"
            and plan.fallback_reason
            and not self._native_degraded_footer_shown
        ):
            self._show_native_degraded_footer_once()

        if plan.backend == "native":
            if for_auto_enqueue and is_native_supported(source_path):
                diag.note_blender_skipped_native_supported(1)
            hq = manual_override == ThumbnailManualOverride.NATIVE
            ok, msg, reject = self._native_thumb_queue.try_enqueue_native(
                source_path,
                fallback_on_fail=plan.fallback_to_blender_on_native_fail,
                for_auto_enqueue=for_auto_enqueue,
                high_quality=hq,
            )
            if ok:
                diag.note_native_jobs_enqueued(1)
                self._native_job_origins[_norm_path_key(source_path)] = origin
            elif reject == NativeEnqueueReject.CAP:
                diag.note_bridge_suppressed(1)
            elif reject == NativeEnqueueReject.DUPLICATE:
                diag.note_bridge_duplicate_skip(1)
            bridge_reject = self._map_native_reject(reject)
            self._sync_bridge_paint_diagnostics()
            diag.maybe_log_summary()
            return ok, msg, bridge_reject

        if plan.backend == "blender":
            if manual_override == ThumbnailManualOverride.BLENDER:
                diag.note_manual_blender_jobs(1)
            ok, msg, reject = self._bridge_queue.try_enqueue_thumbnail(
                source_path,
                origin=origin,
                manual_override=manual_override,
            )
            if reject == BridgeEnqueueReject.CAP:
                diag.note_bridge_suppressed(1)
            elif reject == BridgeEnqueueReject.DUPLICATE:
                diag.note_bridge_duplicate_skip(1)
            self._sync_bridge_paint_diagnostics()
            diag.maybe_log_summary()
            return ok, msg, reject

        return False, plan.reason, BridgeEnqueueReject.NOT_ROUTED

    @staticmethod
    def _map_native_reject(reject: NativeEnqueueReject) -> BridgeEnqueueReject:
        if reject == NativeEnqueueReject.DUPLICATE:
            return BridgeEnqueueReject.DUPLICATE
        if reject == NativeEnqueueReject.CAP:
            return BridgeEnqueueReject.CAP
        if reject == NativeEnqueueReject.SHUTDOWN:
            return BridgeEnqueueReject.SHUTDOWN
        if reject == NativeEnqueueReject.UNSUPPORTED:
            return BridgeEnqueueReject.NOT_ROUTED
        if reject == NativeEnqueueReject.UNAVAILABLE:
            return BridgeEnqueueReject.NOT_ROUTED
        return BridgeEnqueueReject.OK

    def _maybe_show_startup_native_degraded_hint(self) -> None:
        """Footer hint when native is unavailable but Blender can cover STL/OBJ."""
        if self._native_renderer_health.available:
            return
        if find_blender_executable(self._settings_service) is None:
            return
        self._show_native_degraded_footer_once()

    def _on_render_pipeline_status(self, message: str) -> None:
        """Show mesh render pipeline progress in the footer (background workers)."""
        from meshcorral.ui.footer_status import friendly_render_pipeline_status

        text = friendly_render_pipeline_status((message or "").strip())
        if not text:
            return
        self._status_ready_label.setText(text)
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(text, 4000)

    def _show_native_degraded_footer_once(self) -> None:
        """One-shot status when STL/OBJ route through Blender due to missing native deps."""
        if self._native_degraded_footer_shown or self._native_renderer_health.available:
            return
        self._native_degraded_footer_shown = True
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(status_native_thumbnails_blender_fallback(), 8000)

    def _try_enqueue_bridge_record(
        self,
        record: FileRecord,
        *,
        origin: JobOrigin,
        for_auto_enqueue: bool = True,
    ) -> tuple[bool, str, BridgeEnqueueReject]:
        """Enqueue one thumbnail job and record Prime v0.10 diagnostics."""
        return self._try_enqueue_thumbnail_record(
            record,
            origin=origin,
            for_auto_enqueue=for_auto_enqueue,
        )

    def _enqueue_prime_bridge_tiers(
        self,
        *,
        include_idle: bool,
        origin: JobOrigin = JobOrigin.BACKGROUND_AUTO,
    ) -> BridgeEnqueueStats:
        """Enqueue viewport-tier bridge jobs with cap and duplicate suppression."""
        tiers = self._viewport_bridge_tiers(include_idle_rows=include_idle)

        def _try_enqueue(record: FileRecord) -> tuple[bool, str, BridgeEnqueueReject]:
            return self._try_enqueue_thumbnail_record(
                record,
                origin=origin,
                for_auto_enqueue=True,
                idle_tier=include_idle,
            )

        stats = enqueue_tiered_bridge_thumbnails(
            _try_enqueue,
            tiers,
            has_thumbnail=self._thumb_controller.has_index,
            include_idle_tier=include_idle,
        )
        if stats.idle_tier_enqueued > 0:
            self._thumb_controller.paint_diagnostics().note_bridge_idle_enqueue(
                stats.idle_tier_enqueued
            )
        return stats

    def _schedule_bridge_idle_fill(self) -> None:
        """Arm idle-tier bridge fill after viewport work (Prime v0.10)."""
        if self._shutting_down or not self._prime_perf_active:
            return
        if self._asset_mode != ASSET_MODE_3D:
            return
        if not auto_enqueue_allowed(self._settings_service):
            return
        self._bridge_idle_fill_timer.start(500)

    def _run_bridge_idle_fill(self) -> None:
        """Enqueue idle-tier bridge jobs when scroll/decode/UI are quiet."""
        if self._shutting_down or not self._prime_perf_active:
            return
        if self._asset_mode != ASSET_MODE_3D:
            return
        if not auto_enqueue_allowed(self._settings_service):
            return
        if self._thumb_controller.is_fast_scroll_suppressed():
            self._schedule_bridge_idle_fill()
            return
        ui_idle_ms = (time.monotonic() - self._bridge_last_activity_monotonic) * 1000.0
        if not bridge_idle_fill_allowed(
            scroll_idle_ms=self._scroll_velocity.time_since_scroll_ms(),
            scroll_settle_ms=self._scroll_settle_delay_ms(),
            decode_inflight=self._thumb_controller.decoding_count(),
            ui_idle_ms=ui_idle_ms,
        ):
            self._schedule_bridge_idle_fill()
            return
        stats = self._enqueue_prime_bridge_tiers(include_idle=True)
        if stats.enqueued > 0:
            self._note_thumb_jobs_enqueued(stats.enqueued)

    def _is_record_in_visible_viewport(self, record: FileRecord) -> bool:
        """True when *record* is in a currently visible table/gallery row."""
        key = _norm_path_key(record.path)
        for row in self._visible_view_row_indices():
            if 0 <= row < len(self._view_records):
                if _norm_path_key(self._view_records[row].path) == key:
                    return True
        return False

    def _suppress_per_job_thumb_ui(self) -> bool:
        """Prime perf: avoid per-job footer/queue/inspector churn during batches."""
        if not self._prime_perf_active:
            return False
        if self._thumb_batch_progress.active():
            return True
        return (
            self._bridge_queue.queue_length() > 0
            or self._native_thumb_queue.in_flight_count() > 0
            or self._thumb_controller.generating_count() > 0
        )

    def _on_thumb_refresh_batch(self, path_keys: frozenset[str]) -> None:
        """Batched UI refresh for completed thumbnails (visible rows only)."""
        if self._shutting_down or not path_keys:
            return
        visible_rows = self._visible_view_row_indices()
        refreshed = emit_visible_thumb_refresh(
            view_records=self._view_records,
            path_keys=path_keys,
            visible_row_indices=visible_rows,
            table_model=self._model,
            gallery_model=self._gallery_model,
        )
        if self._lazy_thumb_health.lazy_enabled() and refreshed:
            self._lazy_thumb_health.resolve_many(refreshed)

    def _on_thumb_progress_tick(self) -> None:
        """Update coarse batch progress at most once per second."""
        if self._shutting_down:
            return
        snap = self._thumb_batch_progress.snapshot()
        if snap.active and snap.total > 0:
            self._status_thumbs_label.setText(
                format_thumbnail_footer(
                    batch_completed=snap.completed,
                    batch_total=snap.total,
                )
            )
            if not self._is_scanning:
                self._status_ready_label.setText(
                    format_loading_thumbnails_progress(
                        completed=snap.completed,
                        total=snap.total,
                    )
                )
            return
        self._thumb_progress_timer.stop()
        self._thumb_refresh_accumulator.flush_now()
        self._update_thumb_queue_status()

    def _note_thumb_jobs_enqueued(self, count: int) -> None:
        """Track batch size when prime perf queues many thumbnails."""
        if self._shutting_down or count <= 0 or not self._prime_perf_active:
            return
        if not self._thumb_batch_progress.active():
            self._thumb_batch_progress.start_batch(count)
        else:
            self._thumb_batch_progress.add_to_total(count)
        if not self._thumb_progress_timer.isActive():
            self._thumb_progress_timer.start()
        self._on_thumb_progress_tick()

    def _visible_view_row_indices(self) -> list[int]:
        return visible_row_indices_for_browse_widget(
            view_stack_index=self._view_stack.currentIndex(),
            table=self._table,
            gallery=self._gallery_list,
        )

    def viewport_epoch(self) -> int:
        """Current viewport epoch (Prime v0.7 stale-decode cancellation token)."""
        return int(self._viewport_epoch)

    def _bump_viewport_epoch(self) -> int:
        """Advance the viewport epoch so background workers can drop stale results."""
        self._viewport_epoch += 1
        return self._viewport_epoch

    def _browse_scroll_value(self) -> int:
        """Current vertical scrollbar value for the active browse view."""
        if self._view_stack.currentIndex() == 0:
            return int(self._table.verticalScrollBar().value())
        return int(self._gallery_list.verticalScrollBar().value())

    def _browse_row_height_px(self) -> int:
        """Approximate row height for velocity / prefetch heuristics."""
        if self._view_stack.currentIndex() == 0:
            return max(1, int(self._table.verticalHeader().defaultSectionSize()))
        size = self._gallery_list.gridSize()
        return max(1, int(size.height()) if size.height() > 0 else 96)

    def _selected_view_row_index(self) -> int | None:
        """Primary selected row in the active browse view, if any."""
        if self._view_stack.currentIndex() == 0:
            sm = self._table.selectionModel()
            if sm is None or not sm.hasSelection():
                return None
            idx = sm.currentIndex()
            return int(idx.row()) if idx.isValid() else None
        gsm = self._gallery_list.selectionModel()
        if gsm is None or not gsm.hasSelection():
            return None
        idx = gsm.currentIndex()
        return int(idx.row()) if idx.isValid() else None

    def _ordered_viewport_records(self) -> list[FileRecord]:
        """
        Visible-first records with v0.9 priority: selection, visible, directional preload.
        """
        visible = self._visible_view_row_indices()
        total = len(self._view_records)
        direction = self._scroll_velocity.direction()
        prefetch_rows = directional_prefetch_row_indices(
            visible,
            total,
            direction=direction,
            network_like=self._prime_network_like,
        )
        if self._prime_perf_active and prefetch_rows:
            self._thumb_controller.paint_diagnostics().note_directional_prefetch(
                len(prefetch_rows)
            )
        ordered = prioritize_viewport_records(
            self._view_records,
            prefetch_rows,
            selected_row=self._selected_view_row_index(),
        )
        cap = gallery_max_visible_build()
        if len(ordered) > cap:
            return ordered[:cap]
        return ordered

    def _scroll_settle_delay_ms(self) -> int:
        """Post-scroll idle delay before resuming thumbnail work (Prime v0.9)."""
        return int(self._scroll_velocity.settle_delay_ms())

    def _maybe_update_scroll_status(
        self,
        *,
        fast: bool | None = None,
        loading: bool = False,
    ) -> None:
        """Update status line for fast-scroll pause / resume (at most once per second)."""
        if not self._prime_perf_active:
            return
        now = time.monotonic()
        if now - self._scroll_status_last_monotonic < 1.0:
            if fast is None and not loading:
                return
            if fast is not None and fast == self._scroll_status_fast_active and not loading:
                return
        self._scroll_status_last_monotonic = now
        if fast is True:
            self._scroll_status_fast_active = True
            self._update_status(status_scrolling_thumbnails_paused(), show_view_counts=True)
            return
        if loading:
            self._scroll_status_fast_active = False
            self._update_status(status_loading_visible_thumbnails(), show_view_counts=True)
            return
        if fast is False:
            self._scroll_status_fast_active = False

    def _schedule_viewport_thumb_pass(self, *_args: object) -> None:
        """Debounce scroll/resize thumbnail health + preload to keep scrolling smooth."""
        if self._shutting_down or not self._view_records:
            return
        self._touch_bridge_ui_activity()
        self._scroll_velocity.set_row_height_px(self._browse_row_height_px())
        scroll_val = self._browse_scroll_value()
        view_idx = int(self._view_stack.currentIndex())
        state = self._scroll_velocity.update(
            scroll_val,
            network_like=self._prime_network_like,
        )
        if (
            scroll_val != self._last_viewport_scroll_for_epoch
            or view_idx != self._last_view_stack_index_for_epoch
        ):
            self._last_viewport_scroll_for_epoch = scroll_val
            self._last_view_stack_index_for_epoch = view_idx
            self._bump_viewport_epoch()
        self._viewport_thumb_timer.stop()
        if self._prime_perf_active and state.is_fast_scrolling:
            self._thumb_controller.set_fast_scroll_suppressed(True)
            self._maybe_update_scroll_status(fast=True)
            self._scroll_settle_timer.start(self._scroll_settle_delay_ms())
            return
        self._thumb_controller.set_fast_scroll_suppressed(False)
        self._scroll_settle_timer.stop()
        self._viewport_thumb_timer.start(int(self._viewport_thumb_interval_ms))

    def _on_scroll_settle_timer(self) -> None:
        """Resume visible-first thumbnail work after fast scrolling settles (Prime v0.9)."""
        if self._shutting_down:
            return
        if self._scroll_velocity.is_fast_scrolling():
            self._scroll_settle_timer.start(self._scroll_settle_delay_ms())
            return
        idle_ms = self._scroll_velocity.time_since_scroll_ms()
        delay_ms = self._scroll_settle_delay_ms()
        if idle_ms < delay_ms:
            self._scroll_settle_timer.start(max(16, delay_ms - idle_ms))
            return
        self._thumb_controller.set_fast_scroll_suppressed(False)
        self._maybe_update_scroll_status(loading=True)
        self._run_viewport_thumb_pass()

    def _run_viewport_thumb_pass(self) -> None:
        """Visible-first health resolve and thumbnail queue/decode after debounce/settle."""
        if self._warm_catalog_active and self._is_scanning:
            return
        if self._shutting_down:
            return
        self._resolve_visible_thumb_health()
        if not self._prime_perf_active:
            return
        if self._asset_mode == ASSET_MODE_3D:
            self._queue_visible_missing_thumbnails(scroll_pass=True)
        elif self._asset_mode == ASSET_MODE_IMAGES:
            self._queue_visible_raster_thumbnails(scroll_pass=True)

    def _on_viewport_thumb_timer(self) -> None:
        if self._shutting_down:
            return
        if self._prime_perf_active and self._scroll_velocity.is_fast_scrolling():
            self._thumb_controller.set_fast_scroll_suppressed(True)
            self._scroll_settle_timer.start(self._scroll_settle_delay_ms())
            return
        self._thumb_controller.set_fast_scroll_suppressed(False)
        self._run_viewport_thumb_pass()

    def _resolve_visible_thumb_health(self) -> None:
        """Resolve thumbnail health for viewport rows only (lazy mode)."""
        if not self._lazy_thumb_health.lazy_enabled():
            return
        rows = self._visible_view_row_indices()
        if not rows:
            return
        ordered = self._ordered_viewport_records()
        if not ordered:
            return
        changed = self._lazy_thumb_health.resolve_many_changed(ordered)
        if changed:
            self._emit_thumb_health_rows(changed)

    def _emit_thumb_health_rows(self, records: list[FileRecord]) -> None:
        """Refresh thumb/health columns for specific records (visible-only in prime perf)."""
        if not records:
            return
        if self._prime_perf_active:
            keys = frozenset(_norm_path_key(r.path) for r in records)
            self._on_thumb_refresh_batch(keys)
            return
        for record in records:
            key = _norm_path_key(record.path)
            self._model.emit_thumb_rows_for_path_key(key)
            self._gallery_model.emit_items_for_path_key(key)

    def _deferred_refresh_thumb_index_after_scan(self) -> None:
        """Rebuild bridge index without repainting every row (prime perf scans)."""
        if self._shutting_down:
            return
        self._prime_ready_cache_from_metadata_cache()
        self._prime_non_renderable_from_metadata_cache()
        emit_all = not self._prime_perf_active
        self._thumb_controller.refresh_index(emit_rows=emit_all)
        if self._prime_perf_active:
            self._resolve_visible_thumb_health()
            if self._asset_mode == ASSET_MODE_IMAGES:
                self._queue_visible_raster_thumbnails(scroll_pass=False)

    def _queue_visible_missing_thumbnails(self, *, scroll_pass: bool) -> None:
        """
        Enqueue missing mesh thumbnails for viewport rows (Prime v0.10 tiers).

        *scroll_pass* uses selected/visible/directional preload only; idle fill is
        scheduled separately when scroll, decode, and UI are quiet.
        """
        if self._shutting_down or self._asset_mode != ASSET_MODE_3D:
            return
        if scroll_pass and self._thumb_controller.is_fast_scroll_suppressed():
            return
        if self._prime_perf_active:
            stats = self._enqueue_prime_bridge_tiers(include_idle=False)
            if stats.enqueued > 0:
                self._note_thumb_jobs_enqueued(stats.enqueued)
            self._schedule_bridge_idle_fill()
            return
        ordered = self._ordered_viewport_records()
        if not ordered:
            return
        if scroll_pass:
            cap = SettingsService.CAP_AUTO_THUMB_UNLIMITED
        else:
            cap = effective_auto_thumbnail_cap(
                self._scan_root_path(),
                len(self._all_records),
                self._last_scan_elapsed_s,
                self._settings_service.auto_thumbnail_max_per_scan(),
                unlimited_cap=SettingsService.CAP_AUTO_THUMB_UNLIMITED,
            )
        to_queue = select_auto_thumbnail_candidates(
            ordered,
            has_thumbnail=self._thumb_controller.has_index,
            cap=cap,
            unlimited_cap=SettingsService.CAP_AUTO_THUMB_UNLIMITED,
        )
        enqueued_scroll = 0
        for record in to_queue:
            ok, _, _reject = self._try_enqueue_thumbnail_record(
                record,
                origin=JobOrigin.BACKGROUND_AUTO,
                for_auto_enqueue=True,
            )
            if ok:
                enqueued_scroll += 1
        self._note_thumb_jobs_enqueued(enqueued_scroll)

    def _queue_visible_raster_thumbnails(self, *, scroll_pass: bool) -> None:
        """
        Prime READY for visible raster rows and refresh (no pixmap decode on scan).

        *scroll_pass* uses unlimited cap; post-scan uses folder-aware cap.
        """
        if self._shutting_down or self._asset_mode != ASSET_MODE_IMAGES:
            return
        if scroll_pass and self._thumb_controller.is_fast_scroll_suppressed():
            return
        ordered = self._ordered_viewport_records()
        if not ordered:
            return
        if scroll_pass:
            cap = SettingsService.CAP_AUTO_THUMB_UNLIMITED
        else:
            cap = effective_auto_thumbnail_cap(
                self._scan_root_path(),
                len(self._all_records),
                self._last_scan_elapsed_s,
                self._settings_service.auto_thumbnail_max_per_scan(),
                unlimited_cap=SettingsService.CAP_AUTO_THUMB_UNLIMITED,
            )
        ready_cache = self._thumb_controller.ready_cache()
        to_prime = select_raster_decode_candidates(
            ordered,
            is_ready=lambda r: ready_cache.is_ready(r.path),
            cap=cap,
            unlimited_cap=SettingsService.CAP_AUTO_THUMB_UNLIMITED,
        )
        if to_prime:
            self._thumb_controller.prime_raster_ready_async(to_prime)

    def _schedule_auto_thumbnails_after_scan(self) -> None:
        """
        If enabled, queue missing Blender thumbnail jobs for .stl / .obj / .fbx on the next event-loop
        tick so the scan cursor and UI are released first.
        """
        if self._shutting_down:
            return
        if self._scan_skip_auto_thumbnails_once:
            return
        if not self._settings_service.auto_thumbnail_after_scan():
            return
        if self._asset_mode != ASSET_MODE_3D:
            return
        QTimer.singleShot(0, self._run_auto_thumbnails_after_scan)

    def _run_auto_thumbnails_after_scan(self) -> None:
        """
        Enqueue missing thumbnails for viewport rows only (never the full scan set).

        Prime v0.10 uses tiered viewport enqueue; idle-tier fill runs when UI is quiet.
        """
        if self._shutting_down:
            return
        if not self._settings_service.auto_thumbnail_after_scan():
            return
        if self._asset_mode != ASSET_MODE_3D:
            return
        n_indexed = len(self._all_records)
        if not self._view_records:
            return
        mesh_for_thumb = filter_auto_thumbnail_records(self._view_records)
        if not mesh_for_thumb:
            return
        if self._prime_perf_active:
            stats = self._enqueue_prime_bridge_tiers(include_idle=False)
            queued = stats.enqueued
            self._last_scan_thumb_queued = queued
            if queued > 0:
                self._note_thumb_jobs_enqueued(queued)
            self._schedule_bridge_idle_fill()
            tiers = self._viewport_bridge_tiers(include_idle_rows=False)
            visible_mesh = sum(len(tiers[k]) for k in ("selected", "visible", "directional_preload"))
            already = max(0, visible_mesh - queued)
            self._update_status(
                f"Indexed {n_indexed:,} files  •  Queued {queued:,} viewport thumbnail"
                f"{'s' if queued != 1 else ''}  •  {already:,} viewport already had thumbnails",
                show_view_counts=True,
            )
            self._resolve_visible_thumb_health()
            return
        cap = effective_auto_thumbnail_cap(
            self._scan_root_path(),
            n_indexed,
            self._last_scan_elapsed_s,
            self._settings_service.auto_thumbnail_max_per_scan(),
            unlimited_cap=SettingsService.CAP_AUTO_THUMB_UNLIMITED,
        )
        if self._scan_visible_thumbs_only_once:
            cap = min(cap, AUTO_QUEUE_CAP_NETWORK)
        rows = self._visible_view_row_indices()
        ordered = prioritize_visible_records(self._view_records, rows)
        to_queue = select_auto_thumbnail_candidates(
            ordered,
            has_thumbnail=self._thumb_controller.has_index,
            cap=cap,
            unlimited_cap=SettingsService.CAP_AUTO_THUMB_UNLIMITED,
        )
        queued = 0
        for record in to_queue:
            ok, _, _reject = self._try_enqueue_thumbnail_record(
                record,
                origin=JobOrigin.BACKGROUND_AUTO,
                for_auto_enqueue=True,
            )
            if ok:
                queued += 1
        self._last_scan_thumb_queued = queued
        self._note_thumb_jobs_enqueued(queued)
        visible_mesh = sum(1 for r in ordered if is_auto_thumbnail_extension(r))
        already = max(0, visible_mesh - len(to_queue))
        self._update_status(
            f"Indexed {n_indexed:,} files  •  Queued {queued:,} thumbnail"
            f"{'s' if queued != 1 else ''}  •  {already:,} visible already had thumbnails",
            show_view_counts=True,
        )
        self._resolve_visible_thumb_health()

    def _combo_filter_kwargs(self) -> dict[str, object]:
        """Combo/thumb/asset filters without the search box (query handled separately)."""
        return {
            "extension_filter": self.extension_combo.currentText(),
            "folder_filter": self.folder_combo.currentText(),
            "category_filter": self.category_combo.currentText(),
            "asset_mode": self._asset_mode,
            "thumb_health_filter": self._thumb_filter_combo.currentText(),
            "thumb_health_for": self._lazy_thumb_health.thumb_health,
            "favorite_filter": self._favorite_filter_combo.currentText(),
            "is_favorite_for": self._favorite_service.is_favorite_record,
            "collection_filter": self._collections.filter_predicate(),
            "housekeeping_filter": self._housekeeping.filter_predicate(),
        }

    def _scan_filter_kwargs(self) -> dict[str, object]:
        """Arguments for :func:`~meshcorral.services.search_service.filter_records` (scan batches)."""
        return {
            "search_text": self._search_edit.text(),
            **self._combo_filter_kwargs(),
        }

    def _ensure_metadata_cache(self) -> MetadataCache:
        """Open (or return) the persistent metadata SQLite cache."""
        if self._metadata_cache is None:
            self._metadata_cache = MetadataCache()
        return self._metadata_cache

    def _ensure_archive_manifest_cache(self) -> ArchiveManifestCache:
        """Open (or return) the persistent archive manifest SQLite cache."""
        if self._archive_manifest_cache is None:
            self._archive_manifest_cache = ArchiveManifestCache()
        return self._archive_manifest_cache

    def _record_needs_metadata_enrichment(self, rec: FileRecord, *, network_like: bool) -> bool:
        """True when a background stat pass should touch *rec* (v0.7 + v0.8)."""
        if not rec.is_metadata_enriched():
            return True
        if network_like and rec.metadata_source == "cache":
            return True
        return False

    def _update_metadata_cache_from_bridge_result(self, result: BridgeJobResult) -> None:
        """Persist thumbnail outcome into the metadata cache (v0.8)."""
        if not result.source_file:
            return
        cache = self._metadata_cache
        if cache is None:
            return
        source_root = self._current_source or self._selected_source_path or ""
        status = getattr(result.status, "value", str(result.status))
        thumb_status = "ready" if status == BridgeJobStatus.COMPLETE.value else "failed"
        thumb_path = result.thumbnail_path if thumb_status == "ready" else None
        rec = self._record_for_source_path(Path(result.source_file))
        ext = rec.extension if rec is not None else Path(result.source_file).suffix.lower()
        size = rec.size_bytes if rec is not None else None
        mtime = rec.modified_time if rec is not None else None
        cache.upsert(
            path=result.source_file,
            ext=ext,
            size_bytes=size,
            modified_time=mtime,
            file_exists=True,
            source_root=source_root,
            thumb_status=thumb_status,
            thumb_path=thumb_path,
            renderer_version="blender_bridge",
            enriched=rec.is_metadata_enriched() if rec is not None else False,
        )

    def _is_known_non_renderable_record(
        self,
        record: FileRecord,
        source_path: Path,
    ) -> bool:
        """
        True when an automatic thumbnail request must skip Blender for *record*.

        Uses the persisted negative result plus the record's scanned size/mtime, so an
        edited file falls out of the cache and is retried. No stat is issued here: the
        gate runs on every viewport enqueue pass.
        """
        if not is_tracked_non_renderable_extension(source_path):
            return False
        cache = self._metadata_cache
        if cache is None:
            return False
        entry = cache.non_renderable_thumb(source_path)
        blocked = non_renderable_blocks_auto_enqueue(
            entry,
            size_bytes=record.size_bytes,
            modified_time=record.modified_time,
        )
        if blocked:
            self._thumb_controller.mark_non_renderable(source_path)
        elif entry is not None:
            # Fingerprint moved on: drop the stale marker so Blender may try again.
            self._forget_non_renderable_source(source_path)
        return blocked

    def _forget_non_renderable_source(self, source_path: Path) -> None:
        """Clear persisted and in-memory non-renderable state for *source_path*."""
        if not is_tracked_non_renderable_extension(source_path):
            return
        self._thumb_controller.clear_non_renderable(source_path)
        cache = self._metadata_cache
        if cache is None:
            return
        if cache.clear_non_renderable_thumb(source_path):
            self._lazy_thumb_health.invalidate_key(_norm_path_key(source_path))

    def _record_non_renderable_result(self, result: BridgeJobResult) -> None:
        """
        Persist a high-confidence non-renderable verdict for a failed thumbnail job.

        Transient failures (crash, timeout, permission/IO, missing outputs, unknown
        importer exceptions) are classified as ``None`` and stay retryable.
        """
        if not result.source_file:
            return
        cache = self._metadata_cache
        if cache is None:
            return
        verdict = classify_non_renderable_result(result)
        if verdict is None:
            return
        source_path = Path(result.source_file)
        fingerprint = fingerprint_for_path(source_path)
        if fingerprint is None:
            return
        cache.record_non_renderable_thumb(
            path=source_path,
            reason=verdict.reason.value,
            detail=verdict.detail,
            size_bytes=fingerprint.size_bytes,
            modified_time=fingerprint.modified_time,
        )
        self._thumb_controller.mark_non_renderable(source_path)
        self._lazy_thumb_health.invalidate_key(_norm_path_key(source_path))

    def _prime_non_renderable_from_metadata_cache(self) -> int:
        """
        Seed the paint-safe non-renderable key set from SQLite for the current view.

        Returns how many rows are still non-renderable (fingerprint unchanged).
        """
        cache = self._metadata_cache
        if cache is None:
            return 0
        tracked = [
            r for r in self._all_records if is_tracked_non_renderable_extension(r.path)
        ]
        if not tracked:
            self._thumb_controller.set_non_renderable_keys(())
            return 0
        by_key = {_norm_path_key(r.path): r for r in tracked}
        keys: list[str] = []
        for entry in cache.non_renderable_thumbs_for_paths([r.path for r in tracked]):
            record = by_key.get(entry.path_key)
            if record is None:
                continue
            if entry.matches_fingerprint(
                size_bytes=record.size_bytes,
                modified_time=record.modified_time,
            ):
                keys.append(entry.path_key)
        self._thumb_controller.set_non_renderable_keys(keys)
        if keys:
            logger.info(
                "metadata cache primed %s known non-renderable thumbnail row(s)",
                len(keys),
            )
        return len(keys)

    def _prime_ready_cache_from_metadata_cache(self) -> int:
        """
        Seed READY thumbnail paths from SQLite before a full ``result.json`` walk.

        Returns the number of paths marked READY.
        """
        cache = self._metadata_cache
        if cache is None or not self._all_records:
            return 0
        hints = cache.iter_thumb_hints_for_paths([r.path for r in self._all_records])
        primed = 0
        for key, thumb_path in hints:
            try:
                src = Path(key)
                thumb = Path(thumb_path)
            except (TypeError, ValueError):
                continue
            if not thumb.is_file():
                continue
            if self._thumb_controller.ready_cache().mark_ready(src, thumb):
                primed += 1
        if primed > 0:
            logger.info("metadata cache primed %s READY thumbnail paths", primed)
        return primed

    def _log_cache_diagnostics(self) -> None:
        """Emit v0.8 cache diagnostics to the log (rate-limited UI uses status bar)."""
        diag = self._last_scan_cache_diag
        meta = self._metadata_cache
        archive = self._archive_manifest_cache
        if diag is None and meta is None and archive is None:
            return
        parts: list[str] = []
        if meta is not None:
            st = meta.stats()
            parts.append(f"metadata_rows={st.row_count}")
        if diag is not None:
            parts.append(
                f"scan_hits={diag.metadata_cache_hits} "
                f"scan_misses={diag.metadata_cache_misses} "
                f"hit_rate={diag.cache_hit_rate():.2f}"
            )
            parts.append(
                f"archives_reused={diag.archive_manifests_reused} "
                f"archives_rebuilt={diag.archive_manifests_rebuilt}"
            )
        if archive is not None:
            ast = archive.stats()
            parts.append(
                f"archive_manifests={ast.archive_count} archive_entries={ast.entry_count}"
            )
        if parts:
            logger.info("Prime v0.8 cache diagnostics: %s", " | ".join(parts))

    def _on_refresh_metadata_for_view(self) -> None:
        """Jobs → re-stat visible rows and refresh cache entries."""
        if not self._view_records:
            return
        cache = self._ensure_metadata_cache()
        source_root = self._current_source or self._selected_source_path or ""
        updates: dict[str, tuple[int | None, float | None]] = {}
        for rec in self._view_records:
            try:
                st = rec.path.stat()
            except OSError:
                cache.mark_missing(rec.path)
                continue
            sz = int(st.st_size)
            mt = float(st.st_mtime)
            updates[_norm_path_key(rec.path)] = (sz, mt)
            cache.upsert(
                path=rec.path,
                ext=rec.extension,
                size_bytes=sz,
                modified_time=mt,
                file_exists=True,
                source_root=source_root,
                enriched=True,
            )
        if not updates:
            return
        for idx, rec in enumerate(self._all_records):
            patch = updates.get(_norm_path_key(rec.path))
            if patch is None:
                continue
            self._all_records[idx] = rec.with_metadata(
                size_bytes=patch[0], modified_time=patch[1], metadata_source="stat"
            )
        self._model.apply_metadata_batch(updates)
        self._gallery_model.apply_metadata_batch(updates)
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(f"Refreshed metadata for {len(updates):,} visible file(s).", 5000)

    def _on_clear_metadata_cache(self) -> None:
        """Jobs → wipe the SQLite metadata cache."""
        cache = self._ensure_metadata_cache()
        removed = cache.clear_all()
        QMessageBox.information(
            self,
            "Metadata cache cleared",
            f"Removed {removed:,} cached metadata row(s).",
        )

    def _on_prune_metadata_cache(self) -> None:
        """Jobs → delete metadata cache rows older than 30 days."""
        cache = self._ensure_metadata_cache()
        removed = cache.prune_older_than(30.0)
        QMessageBox.information(
            self,
            "Metadata cache pruned",
            f"Removed {removed:,} row(s) not seen in the last 30 days.",
        )

    def _on_rebuild_archive_manifest_selection(self) -> None:
        """Jobs → force re-index of a selected ``.zip`` archive."""
        selected = self.selected_records()
        if not selected:
            QMessageBox.information(
                self,
                "No selection",
                "Select a .zip file in the table, then run this action again.",
            )
            return
        archive_cache = self._ensure_archive_manifest_cache()
        rebuilt = 0
        for rec in selected:
            if not ArchiveManifestCache.is_supported_archive(rec.path):
                continue
            result = archive_cache.force_rebuild(rec.path)
            if result is not None:
                rebuilt += 1
        if rebuilt == 0:
            QMessageBox.information(
                self,
                "Archive manifest",
                "No .zip files in the current selection were re-indexed.",
            )
            return
        QMessageBox.information(
            self,
            "Archive manifest rebuilt",
            f"Rebuilt manifest cache for {rebuilt} archive(s).",
        )

    def _schedule_metadata_enrichment_after_scan(self) -> None:
        """
        Run a background ``stat()`` pass to fill ``size_bytes`` / ``modified_time``.

        Prime v0.7 metadata-first virtualization: lightweight scans emit records
        with ``None`` metadata so the table appears instantly; this method spins
        up a worker thread that stats records in chunks (visible rows first) and
        emits batched updates to the table/gallery models.
        """
        if self._shutting_down:
            return
        root = self._scan_root_path()
        network_like = is_network_like_path(root) if str(root) else False
        records_to_enrich = [
            (_norm_path_key(rec.path), rec.path)
            for rec in self._all_records
            if self._record_needs_metadata_enrichment(rec, network_like=network_like)
        ]
        if not records_to_enrich:
            return
        visible_paths: set[str] = set()
        for row in self._visible_view_row_indices():
            if 0 <= row < len(self._view_records):
                visible_paths.add(_norm_path_key(self._view_records[row].path))
        if visible_paths:
            records_to_enrich.sort(key=lambda pair: 0 if pair[0] in visible_paths else 1)
        self._cancel_active_enrichment()

        thr = QThread(self)
        runner = MetadataEnrichmentRunner()
        runner.moveToThread(thr)
        runner.batch_ready.connect(self._on_metadata_batch_ready)
        runner.enrichment_finished.connect(self._on_enrichment_finished)
        runner.enrichment_finished.connect(thr.quit)
        # Null out our handles *before* the C++ objects are destroyed, otherwise a
        # subsequent ``_cancel_active_enrichment`` call would touch ``isRunning()``
        # on a deleted ``QThread`` and raise (shiboken: object already deleted).
        thr.finished.connect(self._on_enrichment_thread_finished)
        thr.finished.connect(runner.deleteLater)
        thr.finished.connect(thr.deleteLater)

        root = self._scan_root_path()
        network_like = is_network_like_path(root) if str(root) else False
        profile = remote_throttle_profile(network_like)
        batch_size = int(profile.enrichment_batch_size)
        pause_s = float(profile.enrichment_sleep_s)
        thr.started.connect(
            lambda: runner.execute_enrichment(records_to_enrich, batch_size, pause_s)
        )

        self._enrichment_thread = thr
        self._enrichment_runner = runner
        self._enrichment_in_progress = True
        thr.start()
        logger.debug(
            "metadata enrichment scheduled: %s paths (network_like=%s)",
            len(records_to_enrich),
            network_like,
        )

    def _on_metadata_batch_ready(self, batch: object) -> None:
        """Main thread: merge a stat batch into both models and the working set."""
        if self._shutting_down:
            return
        if not isinstance(batch, list):
            return
        updates: dict[str, tuple[int | None, float | None]] = {}
        for item in batch:
            if isinstance(item, MetadataUpdate):
                updates[item.path_key] = (item.size_bytes, item.modified_time)
        if not updates:
            return
        source_root = self._current_source or self._selected_source_path or ""
        cache = self._metadata_cache
        for idx, rec in enumerate(self._all_records):
            patch = updates.get(_norm_path_key(rec.path))
            if patch is None:
                continue
            self._all_records[idx] = rec.with_metadata(
                size_bytes=patch[0], modified_time=patch[1], metadata_source="stat"
            )
            if cache is not None:
                cache.upsert(
                    path=rec.path,
                    ext=rec.extension,
                    size_bytes=patch[0],
                    modified_time=patch[1],
                    file_exists=True,
                    source_root=source_root,
                    enriched=True,
                )
        self._model.apply_metadata_batch(updates)
        self._gallery_model.apply_metadata_batch(updates)

    def _on_enrichment_finished(self, total: int) -> None:
        """Background enrichment pass terminated (success or cancel)."""
        self._enrichment_in_progress = False
        if total > 0:
            logger.debug("metadata enrichment completed: %s rows", total)

    def _on_enrichment_thread_finished(self) -> None:
        """Drop enrichment thread/runner handles once Qt has stopped the QThread.

        Connected to ``QThread.finished``. Runs *before* the queued ``deleteLater``
        slots fire, so the next ``_cancel_active_enrichment`` won't touch a
        dangling C++ ``QThread`` (which would raise ``shiboken: Internal C++
        object already deleted``).
        """
        sender = self.sender()
        if sender is not None and sender is not self._enrichment_thread:
            return
        self._enrichment_thread = None
        self._enrichment_runner = None
        self._enrichment_in_progress = False

    def _disconnect_enrichment_signals(self) -> None:
        """Prevent late enrichment batches from touching UI during teardown."""
        runner = self._enrichment_runner
        if runner is None:
            return
        for attr, slot in (
            ("batch_ready", self._on_metadata_batch_ready),
            ("enrichment_finished", self._on_enrichment_finished),
        ):
            signal = getattr(runner, attr, None)
            if signal is None:
                continue
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError, AttributeError):
                logger.debug("enrichment signal disconnect skipped")

    def _disconnect_bridge_ui_signals(self) -> None:
        """Prevent queued bridge signals from touching UI after shutdown."""
        bridge = getattr(self, "_bridge_queue", None)
        if bridge is None:
            return
        pairs = (
            (bridge.queue_count_changed, self._on_bridge_queue_count_changed),
            (bridge.running_job_id_changed, self._on_bridge_running_job_changed),
            (bridge.running_source_path_changed, self._on_bridge_running_source_changed),
            (bridge.job_completed, self._on_thumbnail_job_completed),
        )
        for signal, slot in pairs:
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                logger.debug("bridge signal disconnect skipped")

    def _cancel_active_enrichment(self, *, wait_ms: int = 0) -> None:
        """Signal any running enrichment runner to stop and forget the handles.

        Defensive against already-deleted C++ proxies — natural completion can
        race the next scan click, leaving stale Python handles pointing at
        destroyed ``QThread`` / runner instances.

        *wait_ms* is 0 for interactive cancels (starting a new scan must not block the
        UI thread); shutdown passes a bounded wait so the thread — a child of this
        window — has actually finished before Qt destroys it.
        """
        self._disconnect_enrichment_signals()
        runner = self._enrichment_runner
        if runner is not None:
            try:
                runner.cancel()
            except RuntimeError:
                logger.debug("enrichment runner already deleted on cancel")
        thr = self._enrichment_thread
        if thr is not None:
            running = False
            try:
                running = bool(thr.isRunning())
            except RuntimeError:
                logger.debug("enrichment thread already deleted on cancel")
                running = False
            if running:
                try:
                    thr.requestInterruption()
                    thr.quit()
                    if wait_ms > 0 and not thr.wait(int(wait_ms)):
                        logger.info(
                            "MeshStager shutdown: enrichment thread did not quit within %s ms",
                            wait_ms,
                        )
                except RuntimeError:
                    logger.debug("enrichment thread quit raised after delete")
        self._enrichment_runner = None
        self._enrichment_thread = None
        self._enrichment_in_progress = False

    def _on_scan_thread_finished_cleanup(self) -> None:
        """Drop thread/runner references after the worker has stopped.

        Identity-guarded against late ``finished`` signals from a previous scan
        thread: if the sender is not the current ``self._scan_thread`` (e.g. a
        new scan has already been scheduled), do nothing. Without this guard, a
        stale ``finished`` event nulls the *new* scan's handles, Python GC then
        destroys the new runner mid-``execute_scan``, and the worker crashes
        with ``RuntimeError: Signal source has been deleted`` followed by a
        Windows stack-overrun fast-fail (``0xC0000409``).
        """
        sender = self.sender()
        if sender is not None and sender is not self._scan_thread:
            return
        runner = self._scan_runner
        self._scan_runner = None
        if runner is not None:
            try:
                runner.deleteLater()
            except RuntimeError:
                logger.debug("scan runner already deleted during cleanup")
        thr = self._scan_thread
        self._scan_thread = None
        if thr is not None:
            try:
                thr.deleteLater()
            except RuntimeError:
                logger.debug("scan thread already deleted during cleanup")

    def _restore_pre_scan_working_set(self) -> None:
        """Put back the previous indexed list if a scan fails mid-run."""
        self._all_records = list(self._pre_scan_backup_records)
        self._current_source = self._pre_scan_backup_source
        self._apply_filters(preserve_selection=False)

    def _on_escape_cancel_scan(self) -> None:
        """Escape shortcut: cancel pending scan launch or an active walk."""
        if self._abort_scan_launch():
            return
        self._request_scan_cancel()

    def _update_scan_esc_shortcut(self) -> None:
        """Enable Esc while a scan is launching, pending, or walking."""
        if not hasattr(self, "_scan_cancel_shortcut") or self._scan_cancel_shortcut is None:
            return
        active_walk = self._is_scanning and not self._scan_cancel_pending
        self._scan_cancel_shortcut.setEnabled(
            self._scan_launch_pending or active_walk
        )

    def _abort_scan_launch(self) -> bool:
        """
        Cancel a scan before the worker starts (warning dialog, deferred launch).

        Returns True when a pending launch was aborted.
        """
        had_pending = bool(self._scan_launch_pending)
        dlg = self._large_folder_warning_dialog
        if dlg is not None:
            try:
                dlg.reject()
            except RuntimeError:
                logger.debug("large-folder dialog already deleted on abort")
            self._large_folder_warning_dialog = None
        if not had_pending and dlg is None and not self._is_scanning:
            return False
        self._scan_launch_generation += 1
        self._scan_launch_pending = False
        self._update_scan_esc_shortcut()
        if self._is_scanning:
            return False
        self._apply_scan_launch_canceled_ui()
        return True

    def _apply_scan_launch_canceled_ui(self) -> None:
        """Restore UI after the user cancels before ``FolderScanRunner`` starts."""
        self._scan_user_canceled_hint = True
        self._update_source_mode_hint()
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(status_scan_canceled(), 6000)
        self._update_status(status_scan_canceled(), show_view_counts=False)
        self._update_ui_state()

    def _deferred_run_scan_if_launched(
        self,
        source_path: str,
        launch_gen: int,
        timer: ScanStartupTimer,
    ) -> None:
        """Run scan on the next event-loop tick unless launch was canceled."""
        if launch_gen != self._scan_launch_generation:
            return
        if not self._scan_launch_pending:
            return
        self._scan_launch_pending = False
        self._update_scan_esc_shortcut()
        self._run_scan(source_path, timer=timer)

    def _request_scan_cancel(self) -> None:
        """
        Request cooperative scan cancellation without blocking the UI thread.

        Safe to call from Esc; ignores repeat requests.
        """
        if not self._is_scanning or self._scan_cancel_pending:
            return
        self._scan_cancel_pending = True
        token = self._scan_cancel_token
        if token is not None:
            token.request_cancel()
        self._update_scan_cancel_ui()
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(status_canceling_scan(), 0)

    def _update_scan_cancel_ui(self) -> None:
        """Refresh footer and Esc shortcut for scan/cancel-pending state."""
        self._update_scan_esc_shortcut()
        self._update_scan_walk_status_bar()
        self._update_action_buttons()

    def _scan_event_is_stale(self) -> bool:
        """True when scan worker signals belong to a superseded or finished scan."""
        return not self._scan_accept_events

    def _on_warm_catalog_ready(self, catalog: object) -> None:
        if self._scan_event_is_stale() or self._scan_cancel_pending:
            return
        self._warm_catalog_active = True
        self._all_records = list(catalog.records)
        self._pre_scan_backup_records = list(self._all_records)
        self._pre_scan_backup_source = self._pending_scan_path
        self._current_source = self._pending_scan_path
        self._thumb_filter_combo.blockSignals(True)
        self._thumb_filter_combo.setCurrentText(self._pre_scan_thumb_filter)
        self._thumb_filter_combo.blockSignals(False)
        self._refresh_folder_options()
        self._update_prime_perf_mode()
        self._apply_filters(preserve_selection=True, refresh_inspector=False)
        self._update_status("Verifying source…", show_view_counts=True)

    def _on_warm_catalog_reconciled(self, records: object) -> None:
        if self._scan_event_is_stale():
            return
        # Object reuse identifies unchanged rows; retain their thumbnail caches.
        verified = {str(rec.path): rec for rec in records}
        for previous in self._all_records:
            if verified.get(str(previous.path)) is not previous:
                self._thumb_controller.invalidate_changed_source(previous.path)
        # One authoritative replacement; verification batches never append duplicates.
        self._all_records = list(records)

    def _on_scan_worker_batch(self, batch: object) -> None:
        """Main thread: absorb one batch of scanned records into models (filtered slice)."""
        if self._scan_event_is_stale() or self._scan_cancel_pending:
            return
        if not self._scan_first_batch_logged:
            self._scan_first_batch_logged = True
            timer = self._scan_startup_timer
            if timer is not None:
                timer.mark("FIRST_SCAN_BATCH")
        rows: list[FileRecord] = list(batch)  # type: ignore[arg-type]
        if not rows:
            return
        self._all_records.extend(rows)
        delta = filter_records(rows, **self._scan_filter_kwargs())
        self._view_records.extend(delta)
        self._model.append_records(delta)
        self._gallery_model.append_records(delta)
        session = self._scan_timing_session
        if session is not None:
            session.note_batch_processed(len(delta))
        self._update_scan_walk_status_bar()
        self._refresh_status_counts_strip()
        self._refresh_source_stats_line()

    def _on_scan_worker_failed(self, message: str) -> None:
        """Scan thread reported a hard failure (``scan_folder`` raised)."""
        if self._scan_event_is_stale():
            return
        self._scan_accept_events = False
        self._restore_pre_scan_working_set()
        self._pending_scan_path = ""
        self._last_scan_elapsed_s = None
        self._warm_catalog_active = False
        self._is_scanning = False
        self._scan_cancel_pending = False
        self._stop_scan_heartbeat_timer()
        self._scan_timing_session = None
        self._clear_scan_one_shot_overrides()
        QMessageBox.critical(self, "Scan failed", message)
        self._update_status("Scan failed.", show_view_counts=False)
        self._update_ui_state()
        thr = self._scan_thread
        if thr is not None and thr.isRunning():
            thr.quit()
            thr.wait(10_000)

    def _scan_status_while_walking(self, files_found: int, *, still_scanning: bool = False) -> str:
        """Status line fragment while a folder scan is in progress."""
        if self._scan_cancel_pending:
            return format_scan_cancel_pending_footer()
        if self._warm_catalog_active:
            return "Verifying source…"
        if still_scanning:
            return format_scan_still_scanning_footer(files_found=files_found)
        return format_scan_footer(
            files_found=files_found,
            folder_hint=self._last_scan_progress_folder,
        )

    def _update_scan_walk_status_bar(self, *, still_scanning: bool = False) -> None:
        """Reflect discovery progress vs rows already appended to models."""

        n = max(self._scan_discovery_count, len(self._all_records))
        self._status_ready_label.setText(
            self._scan_status_while_walking(n, still_scanning=still_scanning)
        )

    def _start_scan_heartbeat_timer(self) -> None:
        """Drive footer refresh and scan_timing.log heartbeats every ~1.5s."""
        self._scan_last_progress_monotonic_s = time.monotonic()
        if not self._scan_heartbeat_timer.isActive():
            self._scan_heartbeat_timer.start()

    def _stop_scan_heartbeat_timer(self) -> None:
        if self._scan_heartbeat_timer.isActive():
            self._scan_heartbeat_timer.stop()

    def _on_scan_heartbeat_tick(self) -> None:
        """Keep scan footer alive when the worker is in a slow directory tree."""
        if self._shutting_down or not self._is_scanning:
            self._stop_scan_heartbeat_timer()
            return
        now = time.monotonic()
        stale = (now - self._scan_last_progress_monotonic_s) >= self._scan_still_footer_after_s
        self._update_scan_walk_status_bar(still_scanning=stale)
        session = self._scan_timing_session
        if session is not None:
            session.log_heartbeat(ui_files_indexed=len(self._all_records))

    def _on_scan_worker_progress(self, matched: int, folder: str) -> None:
        """Worker-thread heartbeat during filesystem walk."""
        if self._scan_event_is_stale():
            return
        if not self._scan_first_progress_logged:
            self._scan_first_progress_logged = True
            timer = self._scan_startup_timer
            if timer is not None:
                timer.mark("FIRST_SCAN_PROGRESS")

        self._scan_discovery_count = max(self._scan_discovery_count, matched)
        self._last_scan_progress_folder = folder.strip() or ""
        self._scan_last_progress_monotonic_s = time.monotonic()
        session = self._scan_timing_session
        if session is not None:
            session.note_discovery(matched, self._last_scan_progress_folder)
        self._update_scan_walk_status_bar(still_scanning=False)

    def _on_scan_worker_finished_ok(self, elapsed: float, _total: int) -> None:
        """All batches delivered; align models and UI with a full filter pass (authoritative)."""
        if self._scan_event_is_stale():
            return
        self._scan_accept_events = False
        self._last_scan_elapsed_s = elapsed
        self._all_records.sort(key=scan_folder_sort_key)
        self._current_source = self._pending_scan_path
        self._last_scan_folder = self._pending_scan_path
        QSettings().setValue("paths/last_scan_folder", self._pending_scan_path)
        self._pending_scan_path = ""
        self._did_initial_column_resize = False
        self._rescan_after_mode_change = False
        self._refresh_folder_options()
        self._update_prime_perf_mode()
        self._apply_filters(preserve_selection=self._warm_catalog_active)
        if not self._warm_catalog_active:
            QTimer.singleShot(0, self._deferred_refresh_thumb_index_after_scan)
        self._schedule_auto_thumbnails_after_scan()
        self._schedule_viewport_thumb_pass()
        if not self._warm_catalog_active:
            self._schedule_metadata_enrichment_after_scan()
        self._update_result_summary_label()
        self._warm_catalog_active = False
        self._is_scanning = False
        self._scan_cancel_pending = False
        self._scan_user_canceled_hint = False
        self._filter_footer_note = None
        self._stop_scan_heartbeat_timer()
        self._scan_timing_session = None
        root = self._scan_root_path()
        network_like = is_network_like_path(root) if str(root) else False
        diag = self._last_scan_cache_diag
        from_cache_hits = diag.metadata_cache_hits if diag is not None else 0
        ready_msg = format_scan_complete_message(
            record_count=len(self._all_records),
            from_cache_hits=from_cache_hits,
            network_like=network_like,
        )
        self._log_cache_diagnostics()
        self._update_status(ready_msg, show_view_counts=True)
        self._update_scan_cancel_ui()
        self._update_ui_state()
        self._large_folder_persistence().record_scan_telemetry(
            source_path=str(self._current_source or ""),
            scan_duration_s=self._last_scan_elapsed_s,
            file_count=len(self._all_records),
            network_like=network_like,
            thumbnail_queued=self._last_scan_thumb_queued,
            cancelled=False,
        )
        self._clear_scan_one_shot_overrides()
        thr = self._scan_thread
        if thr is not None and thr.isRunning():
            thr.quit()

    def _on_scan_worker_canceled(self, elapsed: float, _total: int) -> None:
        """Cooperative scan stop: finalize partial results or restore the pre-scan set."""
        if self._scan_event_is_stale():
            return
        self._scan_accept_events = False
        self._last_scan_elapsed_s = elapsed
        source = (self._pending_scan_path or self._selected_source_path or "").strip()
        self._selected_source_path = source
        self._pending_scan_path = ""
        self._scan_cancel_pending = False
        self._warm_catalog_active = False
        self._is_scanning = False
        self._scan_user_canceled_hint = True
        self._filter_footer_note = None
        self._stop_scan_heartbeat_timer()
        self._scan_timing_session = None
        self._clear_scan_one_shot_overrides()

        if self._all_records:
            self._all_records.sort(key=scan_folder_sort_key)
            self._current_source = source
            self._last_scan_folder = source
            if source:
                QSettings().setValue("paths/last_scan_folder", source)
            self._did_initial_column_resize = False
            self._rescan_after_mode_change = False
            self._refresh_folder_options()
            self._update_prime_perf_mode()
            self._apply_filters(preserve_selection=False)
            self._update_result_summary_label()
        else:
            self._restore_pre_scan_working_set()

        self._update_source_mode_hint()
        self._update_source_label()
        self._refresh_source_button_states()
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(status_scan_canceled(), 6000)
        self._update_status(status_scan_canceled(), show_view_counts=bool(self._all_records))
        self._update_scan_cancel_ui()
        self._update_ui_state()
        root = self._scan_root_path()
        network_like = is_network_like_path(root) if str(root) else False
        self._large_folder_persistence().record_scan_telemetry(
            source_path=str(self._current_source or source or ""),
            scan_duration_s=self._last_scan_elapsed_s,
            file_count=len(self._all_records),
            network_like=network_like,
            thumbnail_queued=0,
            cancelled=True,
        )
        thr = self._scan_thread
        if thr is not None and thr.isRunning():
            thr.quit()

    def _large_folder_persistence(self) -> LargeFolderWarningPersistence:
        """QSettings accessor for large-folder warning preferences."""
        return LargeFolderWarningPersistence(
            QSettings(SettingsService.ORG_NAME, SettingsService.APP_NAME)
        )

    def _confirm_large_folder_scan(
        self,
        source_path: str,
        *,
        timer: ScanStartupTimer | None = None,
        on_done: object | None = None,
    ) -> bool | None:
        """
        Show the large-folder warning when triggers match and persistence allows it.

        When *on_done* is provided, the warning uses a non-blocking ``open()`` so the
        main window stays responsive. *on_done* receives ``proceed: bool``.

        Returns ``False`` on cancel, ``True`` when scan may proceed immediately, or
        ``None`` when waiting on the async dialog.
        """
        if self._shutting_down:
            if on_done is not None:
                on_done(False)  # type: ignore[misc]
            return False
        if timer is not None:
            timer.mark("SCAN_LARGE_FOLDER_PREFLIGHT_BEGIN")
        recursive = self._include_subfolders_checkbox.isChecked()
        allowed = supported_extensions_for_asset_mode(self._asset_mode)
        meta_cache = self._ensure_metadata_cache()
        prior_cached = meta_cache.count_for_source_root(source_path)
        persistence = self._large_folder_persistence()
        assessment = build_large_folder_assessment(
            source_path,
            recursive=recursive,
            allowed_extensions=allowed,
            settings_service=self._settings_service,
            persistence=persistence,
            prior_cached_count=prior_cached,
        )
        if timer is not None:
            timer.mark("SCAN_LARGE_FOLDER_PREFLIGHT_END")
        if not persistence.should_show_warning(assessment):
            if on_done is not None:
                on_done(True)  # type: ignore[misc]
                return None
            return True

        def apply_result(result: LargeFolderWarningResult | None) -> bool:
            if result is None:
                self._apply_scan_launch_canceled_ui()
                return False
            if result.skip_future_warnings:
                persistence.set_skip_all_warnings(True)
            if result.skip_future_remote_only:
                persistence.set_skip_remote_only(True)
            self._scan_force_lightweight_once = result.lightweight_scan
            self._scan_visible_thumbs_only_once = result.visible_thumbnails_only
            if result.action == LargeFolderWarningAction.SCAN_WITHOUT_THUMBNAILS:
                self._scan_skip_auto_thumbnails_once = True
            return True

        if on_done is None:
            if timer is not None:
                timer.mark("SCAN_WARNING_DIALOG_BEGIN")
            sync_result = LargeFolderWarningDialog.run_dialog(assessment, parent=self)
            if timer is not None:
                timer.mark("SCAN_WARNING_DIALOG_END")
            return apply_result(sync_result)

        if timer is not None:
            timer.mark("SCAN_WARNING_DIALOG_BEGIN")

        def dialog_finished(result: LargeFolderWarningResult | None) -> None:
            self._large_folder_warning_dialog = None
            if timer is not None:
                timer.mark("SCAN_WARNING_DIALOG_END")
            proceed = apply_result(result)
            on_done(proceed)  # type: ignore[misc]

        self._large_folder_warning_dialog = LargeFolderWarningDialog.open_dialog(
            assessment,
            parent=self,
            on_finished=dialog_finished,
        )
        return None

    def _clear_scan_one_shot_overrides(self) -> None:
        """Reset per-scan overrides applied from the large-folder warning."""
        self._scan_skip_auto_thumbnails_once = False
        self._scan_force_lightweight_once = False
        self._scan_visible_thumbs_only_once = False

    def _run_scan(
        self,
        source_path: str,
        *,
        timer: ScanStartupTimer | None = None,
    ) -> None:
        """Replace the working set with a new scan from the given source path (background scan)."""
        if self._shutting_down:
            return
        if self._scan_thread is not None and self._scan_thread.isRunning():
            return
        self._scan_launch_pending = False
        self._large_folder_warning_dialog = None
        startup_timer = timer or ScanStartupTimer()
        startup_timer.mark("SCAN_RUN_SCAN_BEGIN")
        self._scan_startup_timer = startup_timer
        self._warm_catalog_active = False
        self._pre_scan_thumb_filter = self._thumb_filter_combo.currentText()
        self._scan_first_batch_logged = False
        self._scan_first_progress_logged = False
        self._scan_accept_events = False
        self._scan_generation += 1
        self._last_scan_thumb_queued = 0
        self._session_thumb_failure_count = 0
        self._filter_footer_note = None
        self._scan_user_canceled_hint = False
        self._scan_cancel_pending = False
        self._scan_cancel_token = ScanCancelToken()
        startup_timer.mark("SCAN_CANCEL_ENRICHMENT_BEGIN")
        self._cancel_active_enrichment()
        startup_timer.mark("SCAN_CANCEL_ENRICHMENT_END")
        self._selected_source_path = source_path
        self._unavailable_source_text = ""
        self._refresh_source_button_states()
        self._last_viewport_scroll_for_epoch = -1
        self._last_view_stack_index_for_epoch = -1
        self._bump_viewport_epoch()
        recursive = self._include_subfolders_checkbox.isChecked()
        allowed = supported_extensions_for_asset_mode(self._asset_mode)
        self._stop_filter_search_debounce()
        self._thumb_filter_combo.blockSignals(True)
        self._thumb_filter_combo.setCurrentText(THUMB_FILTER_ALL)
        self._thumb_filter_combo.blockSignals(False)

        self._pre_scan_backup_records = list(self._all_records)
        self._pre_scan_backup_source = self._current_source
        self._is_scanning = True
        self._pending_scan_path = source_path
        self._last_scan_progress_folder = ""
        self._scan_discovery_count = 0
        self._all_records = []
        self._view_records = []
        self._prime_perf_active = False
        self._lazy_thumb_health.set_lazy_enabled(False)
        self._lazy_thumb_health.clear()
        self._model.set_rows([])
        self._gallery_model.set_records([])
        self._clear_table_selection()

        thr = QThread()
        runner = FolderScanRunner()
        runner.moveToThread(thr)
        startup_timer.mark("SCAN_WORKER_CREATED")

        scan_root = source_path
        network_like = bool(is_network_like_path(Path(source_path)))
        meta_cache = self._ensure_metadata_cache()
        prior_cached = meta_cache.count_for_source_root(source_path)
        lightweight = network_like or prior_cached >= 32
        if self._scan_force_lightweight_once:
            lightweight = True
        self._last_scan_cache_diag = ScanCacheDiagnostics()
        cache_ctx = ScanCacheContext(
            metadata_cache=meta_cache,
            source_root=source_path,
            network_optimistic=network_like,
            archive_manifest_cache=self._ensure_archive_manifest_cache(),
            scan_cache_diagnostics=self._last_scan_cache_diag,
            thumbnail_ready_cache=self._thumb_controller.ready_cache(),
        )
        cancel_token = self._scan_cancel_token
        self._scan_timing_session = ScanTimingSession(
            scan_root=scan_root,
            asset_mode=self._asset_mode,
            include_subfolders=recursive,
        )

        runner.scan_request = (
            scan_root, recursive, allowed, lightweight, cache_ctx,
            cancel_token, self._scan_timing_session,
        )
        thr.started.connect(runner.run_requested_scan)
        runner.catalog_ready.connect(self._on_warm_catalog_ready)
        runner.catalog_reconciled.connect(self._on_warm_catalog_reconciled)
        runner.batch_ready.connect(self._on_scan_worker_batch)
        runner.scan_progress.connect(self._on_scan_worker_progress)
        runner.scan_finished.connect(self._on_scan_worker_finished_ok)
        runner.scan_canceled.connect(self._on_scan_worker_canceled)
        runner.scan_failed.connect(self._on_scan_worker_failed)
        thr.finished.connect(self._on_scan_thread_finished_cleanup)

        self._scan_thread = thr
        self._scan_runner = runner
        self._scan_accept_events = True
        self._update_ui_state()
        self._update_scan_cancel_ui()
        self._update_scan_esc_shortcut()
        self._status_ready_label.setText(format_scan_footer(files_found=0))
        self._refresh_status_counts_strip()
        self._refresh_source_stats_line()
        self._start_scan_heartbeat_timer()
        thr.start()
        startup_timer.mark("SCAN_WORKER_STARTED")

    def _refresh_extension_options(self) -> None:
        """Rebuild the extension dropdown for the current type category and asset mode."""
        current_extension = self.extension_combo.currentText()
        category_name = self.category_combo.currentText()
        allowed_extensions = extensions_for_asset_category(
            self._asset_mode, category_name
        )
        allowed_set = set(allowed_extensions)

        self.extension_combo.blockSignals(True)
        self.extension_combo.clear()
        self.extension_combo.addItem("All")
        for ext in allowed_extensions:
            self.extension_combo.addItem(ext)

        if current_extension and (
            current_extension == "All" or current_extension in allowed_set
        ):
            self.extension_combo.setCurrentText(current_extension)
        else:
            self.extension_combo.setCurrentText("All")

        self.extension_combo.blockSignals(False)

    def _on_category_changed(self) -> None:
        self._refresh_extension_options()
        self._apply_filters()

    def _refresh_folder_options(self) -> None:
        """Rebuild the folder dropdown from the current scanned records."""
        current_folder = self.folder_combo.currentText()

        folder_names = sorted(
            {
                record.parent_folder
                for record in self._all_records
                if record.parent_folder.strip()
            }
        )

        self.folder_combo.blockSignals(True)
        self.folder_combo.clear()
        self.folder_combo.addItem("All Folders")
        for folder_name in folder_names:
            self.folder_combo.addItem(folder_name)

        if current_folder and current_folder in folder_names:
            self.folder_combo.setCurrentText(current_folder)
        else:
            self.folder_combo.setCurrentText("All Folders")

        self.folder_combo.blockSignals(False)

    def _selected_paths_for_selection_restore(self) -> list[Path]:
        """Ordered unique paths for rows currently selected (before a model refresh)."""
        if self._view_stack.currentIndex() == 0:
            sm = self._table.selectionModel()
            if sm is None:
                return []
            paths: list[Path] = []
            for idx in sorted(sm.selectedRows(), key=lambda i: i.row()):
                rec = self._model.record_at(idx.row())
                if rec is not None:
                    paths.append(rec.path)
            return list(dict.fromkeys(paths))
        gsm = self._gallery_list.selectionModel()
        if gsm is None:
            return []
        paths_g: list[Path] = []
        for idx in sorted(gsm.selectedIndexes(), key=lambda i: i.row()):
            rec = self._gallery_model.record_at(idx.row())
            if rec is not None:
                paths_g.append(rec.path)
        return list(dict.fromkeys(paths_g))

    def _restore_selection_from_paths(self, paths: list[Path]) -> None:
        """Re-select rows by file path after the view model changes (same record, new row)."""
        tsm = self._table.selectionModel()
        if tsm is not None:
            tsm.clearSelection()
        gsm = self._gallery_list.selectionModel()
        if gsm is not None:
            gsm.clearSelection()
        if not paths or not self._view_records:
            return
        want = {safe_resolve_path(p) for p in paths}
        gflags = QItemSelectionModel.SelectionFlag.Select
        tflags = (
            QItemSelectionModel.SelectionFlag.Select
            | QItemSelectionModel.SelectionFlag.Rows
        )
        for row, rec in enumerate(self._view_records):
            if safe_resolve_path(rec.path) not in want:
                continue
            if self._view_stack.currentIndex() == 0:
                if tsm is not None:
                    tsm.select(self._model.index(row, 0), tflags)
            else:
                if gsm is not None:
                    gsm.select(self._gallery_model.index(row), gflags)

    def _apply_filters(
        self, *, preserve_selection: bool = True, refresh_inspector: bool = True
    ) -> None:
        paths: list[Path] = []
        if preserve_selection:
            paths = self._selected_paths_for_selection_restore()
        else:
            self._clear_table_selection()

        query_text = self._search_edit.text()
        combo_kwargs = self._combo_filter_kwargs()
        combo_kwargs["collections_for"] = self._collections.search_provider()
        self._filter_refresh_inspector_pending = refresh_inspector

        if len(self._all_records) >= ASYNC_FILTER_THRESHOLD:
            status = "Searching…" if (query_text or "").strip() else "Filtering…"
            self._update_status(status, show_view_counts=True)

        result = self._async_filter_engine.request_filter(
            self._all_records,
            combo_kwargs,
            query_text,
            metadata_registry=self._metadata_registry,
            user_tags_for=self._user_tags_for_record,
        )
        if result.pending:
            return

        self._commit_filter_view(
            result.records,
            paths=paths if preserve_selection else [],
            refresh_inspector=refresh_inspector,
        )

    def _browse_destination(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select destination folder")
        if folder:
            self._dest_edit.setText(folder)

    def _selected_source_paths(self) -> list[Path]:
        """Paths for selected rows that are still in the filtered view (never hidden rows)."""
        records = self.selected_records()
        return list(dict.fromkeys(r.path for r in records))

    def selected_records(self) -> list[FileRecord]:
        """Selected rows in the current filtered view (same visibility rules as paths)."""
        visible = {safe_resolve_path(r.path) for r in self._view_records}
        if self._view_stack.currentIndex() == 0:
            selection = self._table.selectionModel()
            if selection is None:
                return []
            rows = sorted({idx.row() for idx in selection.selectedRows()})
            model = self._model
            record_at = model.record_at
        else:
            selection = self._gallery_list.selectionModel()
            if selection is None:
                return []
            rows = sorted({idx.row() for idx in selection.selectedIndexes()})
            record_at = self._gallery_model.record_at
        ordered: list[FileRecord] = []
        for row in rows:
            record = record_at(row)
            if record is None:
                continue
            if safe_resolve_path(record.path) not in visible:
                continue
            ordered.append(record)
        seen: set[Path] = set()
        unique: list[FileRecord] = []
        for record in ordered:
            key = safe_resolve_path(record.path)
            if key in seen:
                continue
            seen.add(key)
            unique.append(record)
        return unique

    def _selected_first_path(self) -> Path | None:
        sources = self._selected_source_paths()
        return sources[0] if sources else None

    def _destination_path_from_edit(self) -> Path:
        """Normalized destination path from the destination line edit."""
        raw = (self._dest_edit.text() or "").strip().rstrip("\\/")
        return normalize_path(raw)

    def _refresh_destination_field_style(self) -> None:
        """Lightweight validation hint on the destination field (no modal)."""
        text = (self._dest_edit.text() or "").strip().rstrip("\\/")
        if not text:
            self._dest_edit.setStyleSheet("")
            self._dest_edit.setToolTip("")
            return
        try:
            dest = normalize_path(text)
            require_destination_baseline(dest, "Destination folder")
            self._dest_edit.setStyleSheet("border: 1px solid #5a8f5a;")
            self._dest_edit.setToolTip("Destination folder is usable for move/copy.")
        except (ValueError, OSError) as exc:
            self._dest_edit.setStyleSheet("border: 1px solid #c07070;")
            self._dest_edit.setToolTip(str(exc))

    def _on_destination_text_changed(self) -> None:
        self._refresh_destination_field_style()
        self._update_ui_state()

    def _on_file_selection_changed(self) -> None:
        """Lightweight UI refresh immediately; inspector/metadata debounced on gallery scroll."""
        self._update_ui_state(refresh_inspector=False)
        delay_ms = gallery_scroll_debounce_ms()
        if delay_ms <= 0:
            self._on_selection_inspector_debounced()
            return
        self._selection_inspector_debounce.stop()
        self._selection_inspector_debounce.start(delay_ms)

    def _on_selection_inspector_debounced(self) -> None:
        """Refresh inspector, tags, and favorites after selection stops changing."""
        if self._shutting_down:
            return
        self._update_asset_inspector()
        self._refresh_tag_editor_for_selection()
        self._refresh_favorite_toggle_for_selection()
        self._collections.refresh_selection()
        self._housekeeping.refresh_selection()

    def _update_move_summary(self) -> None:
        # Match move_service.build_move_plan: one plan row per unique path.
        raw = self._selected_source_paths()
        selected_count = len(raw)
        sources = list(dict.fromkeys(raw))

        dest_text = (self._dest_edit.text() or "").strip().rstrip("\\/")
        dest_label = dest_text if dest_text else "Not set"

        ready_count = 0
        conflict_count = 0

        if not dest_text or not raw:
            self.move_summary_selected.setText(f"Selected: {selected_count}")
            self.move_summary_destination.setText(f"Destination: {dest_label}")
            self.move_summary_ready.setText("Ready: 0")
            self.move_summary_conflicts.setText("Conflicts: 0")
            self.move_summary_ready.setStyleSheet("")
            self.move_summary_conflicts.setStyleSheet("")
            return

        try:
            dest_dir = normalize_path(dest_text)
            require_destination_baseline(dest_dir, "Destination folder")
            plan = self._mover.build_move_plan(sources, dest_dir)
        except (OSError, ValueError):
            conflict_count = len(sources)
        else:
            for item in plan:
                if item.status == MoveService.STATUS_OK:
                    ready_count += 1
                else:
                    conflict_count += 1

        self.move_summary_selected.setText(f"Selected: {selected_count}")
        self.move_summary_destination.setText(f"Destination: {dest_label}")
        self.move_summary_ready.setText(f"Ready: {ready_count}")
        self.move_summary_conflicts.setText(f"Conflicts: {conflict_count}")
        self.move_summary_ready.setStyleSheet(
            "color: #7cc97c;" if ready_count > 0 else ""
        )
        self.move_summary_conflicts.setStyleSheet(
            "color: #e07878;" if conflict_count > 0 else ""
        )

    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Deterministic shutdown coordinator (pre-Prime v0.8 hardening).

        Bounded waits only — never block indefinitely. Logs ``shutdown initiated``
        and ``shutdown complete`` so support can confirm a clean teardown path.
        """
        logger.info("MeshStager shutdown initiated")
        self._shutdown_app(reason="closeEvent")
        logger.info("MeshStager shutdown complete")
        super().closeEvent(event)

    def _shutdown_app(self, *, reason: str) -> None:
        """
        Idempotent teardown driver shared by ``closeEvent`` (and tests).

        Safe to call multiple times; subsequent invocations are no-ops once
        ``_shutting_down`` is set.
        """
        if self._shutting_down:
            return
        self._shutting_down = True
        logger.debug("MeshStager shutdown driver (reason=%s)", reason)

        for attr in (
            "_viewport_thumb_timer",
            "_scroll_settle_timer",
            "_bridge_idle_fill_timer",
            "_filter_search_debounce_timer",
            "_thumb_progress_timer",
        ):
            timer = getattr(self, attr, None)
            if timer is None:
                continue
            try:
                timer.stop()
            except (RuntimeError, AttributeError) as exc:
                logger.debug("timer stop failed (%s): %s", attr, exc)

        try:
            self._thumb_refresh_accumulator.cancel_pending()
        except (RuntimeError, AttributeError) as exc:
            logger.debug("thumb refresh accumulator cancel failed: %s", exc)

        self._cancel_active_enrichment(wait_ms=2_000)
        self._stop_geometry_metadata_thread()

        housekeeping = getattr(self, "_housekeeping", None)
        if housekeeping is not None:
            housekeeping.close()

        collections = getattr(self, "_collections", None)
        if collections is not None:
            collections.close()

        tag_svc = getattr(self, "_tag_service", None)
        if tag_svc is not None:
            try:
                tag_svc.close()
            except (RuntimeError, AttributeError) as exc:
                logger.debug("tag service close failed: %s", exc)

        fav_svc = getattr(self, "_favorite_service", None)
        if fav_svc is not None:
            try:
                fav_svc.close()
            except (RuntimeError, AttributeError) as exc:
                logger.debug("favorite service close failed: %s", exc)

        token = getattr(self, "_scan_cancel_token", None)
        if token is not None:
            try:
                token.request_cancel()
            except (RuntimeError, AttributeError) as exc:
                logger.debug("scan cancel token request failed on shutdown: %s", exc)

        thr_scan = getattr(self, "_scan_thread", None)
        if isinstance(thr_scan, QThread):
            try:
                running = thr_scan.isRunning()
            except RuntimeError:
                running = False
            if running:
                try:
                    thr_scan.quit()
                    if not thr_scan.wait(2_000):
                        logger.info("MeshStager shutdown: scan thread did not quit within 2 s")
                except (RuntimeError, AttributeError) as exc:
                    logger.debug("scan thread shutdown failed: %s", exc)

        controller = getattr(self, "_thumb_controller", None)
        decode_remaining = 0
        if controller is not None:
            if hasattr(controller, "decoding_count"):
                try:
                    decode_remaining = int(controller.decoding_count())
                except (RuntimeError, AttributeError):
                    decode_remaining = 0
            if hasattr(controller, "request_shutdown"):
                try:
                    controller.request_shutdown(timeout_ms=1500)
                except (RuntimeError, AttributeError) as exc:
                    logger.debug("thumb controller shutdown failed: %s", exc)

        bridge = getattr(self, "_bridge_queue", None)
        bridge_pending = 0
        bridge_active = 0
        if bridge is not None:
            try:
                if hasattr(bridge, "pending_count"):
                    bridge_pending = int(bridge.pending_count())
                elif hasattr(bridge, "queue_length"):
                    bridge_pending = int(bridge.queue_length())
            except (RuntimeError, AttributeError):
                bridge_pending = 0
            try:
                if hasattr(bridge, "active_count"):
                    bridge_active = int(bridge.active_count())
            except (RuntimeError, AttributeError):
                bridge_active = 0
            self._disconnect_bridge_ui_signals()
            try:
                if hasattr(bridge, "request_stop"):
                    bridge.request_stop()
                if hasattr(bridge, "cancel_pending"):
                    bridge.cancel_pending()
                elif hasattr(bridge, "cancel_all_queued"):
                    bridge.cancel_all_queued()
            except (RuntimeError, AttributeError) as exc:
                logger.debug("bridge cancel/request_stop failed: %s", exc)
            try:
                bridge.shutdown(timeout=2.0, active_job_wait_s=3.0, close_enqueue=True)
            except (RuntimeError, AttributeError, TypeError) as exc:
                logger.debug("bridge shutdown failed: %s", exc)

        native_queue = getattr(self, "_native_thumb_queue", None)
        native_in_flight = 0
        if native_queue is not None:
            try:
                native_in_flight = int(native_queue.in_flight_count())
            except (RuntimeError, AttributeError):
                native_in_flight = 0
            try:
                native_queue.shutdown()
            except (RuntimeError, AttributeError) as exc:
                logger.debug("native thumbnail queue shutdown failed: %s", exc)

        if bridge_pending > 0 or bridge_active > 0 or decode_remaining > 0 or native_in_flight > 0:
            logger.info(
                "MeshStager shutdown: remaining workers "
                "(bridge_pending=%s bridge_active=%s decode=%s native=%s)",
                bridge_pending,
                bridge_active,
                decode_remaining,
                native_in_flight,
            )

        self._persist_workspace_layout()

        try:
            settings = QSettings()
            settings.setValue("paths/last_destination", (self._dest_edit.text() or "").strip())
            # Prefer the user's *selected* source (survives Asset Mode switches) over
            # the *current rows* source, so a mode-switched session still restores
            # the folder the user last picked.
            persist_target = (
                self._selected_source_path or self._current_source
            ).strip()
            if persist_target:
                settings.setValue("paths/last_scan_folder", persist_target)
            if not (self.windowState() & Qt.WindowMinimized):
                settings.setValue(_KEY_WINDOW_GEOMETRY, self.saveGeometry())
                is_max = bool(self.windowState() & Qt.WindowMaximized)
                settings.setValue(_KEY_WINDOW_STATE, 1 if is_max else 0)
            settings.sync()
        except (RuntimeError, AttributeError, OSError) as exc:
            logger.debug("QSettings flush failed during shutdown: %s", exc)

    def _clear_table_selection(self) -> None:
        """Clear row selection after a transfer to avoid stale indices."""
        sm = self._table.selectionModel()
        if sm is not None:
            sm.clearSelection()
        gsm = self._gallery_list.selectionModel()
        if gsm is not None:
            gsm.clearSelection()

    def _present_transfer_outcome(
        self,
        *,
        is_copy: bool,
        success_count: int,
        skipped_count: int,
        items: list[MovePlan],
        msg_lines: list[str],
        dest_display: str,
    ) -> None:
        """Show a success summary or explicit failure reasons (no silent empty runs)."""
        verb = "Copied" if is_copy else "Moved"
        past = "copied" if is_copy else "moved"
        ok_n, blocked_n, error_n = _transfer_counts(items)

        report_path: Path | None = None
        if error_n > 0:
            report_path = self._write_transfer_report(
                is_copy=is_copy,
                items=items,
                msg_lines=msg_lines,
            )

        if success_count > 0:
            file_word = "file" if success_count == 1 else "files"
            body = f"{verb} {success_count} {file_word} to\n{dest_display}"
            if skipped_count > 0:
                skip_word = "file" if skipped_count == 1 else "files"
                body += (
                    f"\n\n{skipped_count} other {skip_word} were not {past}. "
                    "Typical causes: Blocked or Error in the preview, a runtime disk error, or a "
                    "file that disappeared between preview and execution."
                )
            if report_path is None:
                QMessageBox.information(self, f"{verb} complete", body)
            else:
                self._show_transfer_report_dialog(
                    title=f"{verb} complete (with issues)",
                    summary=body + f"\n\nFailed: {error_n}  •  Blocked/skipped: {blocked_n}",
                    dest_display=dest_display,
                    report_path=report_path,
                )
            return

        if report_path is not None:
            self._show_transfer_report_dialog(
                title=f"{verb} did not complete",
                summary=f"No files were {past}.\n\nFailed: {error_n}  •  Blocked/skipped: {blocked_n}",
                dest_display=dest_display,
                report_path=report_path,
            )
            return
        issues = _issue_lines_for_transfer(items, msg_lines, limit=10)
        if not issues:
            issues = [
                "No files were transferred. Check the preview for blocked rows or "
                "invalid paths.",
            ]
        body = "\n".join(issues)
        QMessageBox.warning(
            self,
            f"{verb} did not complete",
            f"No files were {past}.\n\n{body}",
        )

    def _write_transfer_report(
        self,
        *,
        is_copy: bool,
        items: list[MovePlan],
        msg_lines: list[str],
    ) -> Path | None:
        """Write a short text report for transfer issues; returns the report path, if created."""
        try:
            report_dir = USER_DATA_DIR / "reports"
            report_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return None

        ts = time.strftime("%Y%m%d_%H%M%S")
        kind = "copy" if is_copy else "move"
        path = report_dir / f"transfer_{kind}_{ts}.txt"
        try:
            lines: list[str] = []
            lines.append(f"MeshStager transfer report ({kind})")
            lines.append(f"Created: {time.strftime('%Y-%m-%d %H:%M:%S')}")
            lines.append("")
            if msg_lines:
                lines.append("Per-row results:")
                lines.extend(msg_lines)
            else:
                lines.append("Per-row results:")
                for item in items:
                    lines.append(
                        f"{item.status} | {item.message} | {item.source_path} -> {item.destination_path}"
                    )
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            return None
        return path

    def _show_transfer_report_dialog(
        self,
        *,
        title: str,
        summary: str,
        dest_display: str,
        report_path: Path,
    ) -> None:
        """Show a calm summary with one-click access to report and destination."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle(title)
        box.setText(summary)

        btn_open_report = None
        if report_path.is_file():
            btn_open_report = box.addButton("Open report", QMessageBox.ButtonRole.ActionRole)
        btn_open_dest = box.addButton("Open destination folder", QMessageBox.ButtonRole.ActionRole)
        btn_copy = box.addButton("Copy summary", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Close)

        def _on_clicked(button) -> None:  # type: ignore[no-untyped-def]
            if button == btn_open_dest:
                # Best effort: dest_display may be shortened; re-use the user-entered destination.
                try:
                    dest_dir = self._destination_path_from_edit()
                except ValueError:
                    dest_dir = Path(dest_display)
                open_folder_in_explorer(dest_dir, self, title="Open destination folder")
            elif btn_open_report is not None and button == btn_open_report:
                open_file_with_default_app(report_path, self, title="Open report")
            elif button == btn_copy:
                copy_to_clipboard(summary)
                if self.statusBar() is not None:
                    self.statusBar().showMessage("Copied summary to the clipboard.", 4000)

        box.buttonClicked.connect(_on_clicked)
        box.exec()

    def _on_table_double_clicked(self, index: QModelIndex) -> None:
        """Open the file for the double-clicked row (same path as the context menu)."""
        if not index.isValid():
            return
        record = self._model.record_at(index.row())
        if record is None:
            return
        self._open_with_preferred_dcc_or_default(record.path)

    def _reset_filters(self) -> None:
        """Clear filter controls without modifying scanned records."""
        self._stop_filter_search_debounce()
        self._search_edit.blockSignals(True)
        self._search_edit.clear()
        self._search_edit.blockSignals(False)
        self.category_combo.blockSignals(True)
        self.extension_combo.blockSignals(True)
        self.folder_combo.blockSignals(True)
        self._thumb_filter_combo.blockSignals(True)
        self._favorite_filter_combo.blockSignals(True)
        self.category_combo.setCurrentText("All")
        self._refresh_extension_options()
        # Refresh re-enables extension signals; keep combos quiet until all values are set.
        self.extension_combo.blockSignals(True)
        self.extension_combo.setCurrentText("All")
        self.folder_combo.setCurrentText("All Folders")
        self._thumb_filter_combo.setCurrentText(THUMB_FILTER_ALL)
        self._favorite_filter_combo.setCurrentText(FAVORITE_FILTER_ALL)
        self._collections.sidebar.reset()
        self._housekeeping.sidebar.reset()
        self.category_combo.blockSignals(False)
        self.extension_combo.blockSignals(False)
        self.folder_combo.blockSignals(False)
        self._thumb_filter_combo.blockSignals(False)
        self._favorite_filter_combo.blockSignals(False)
        self._apply_filters()

    def _copy_selected_files(self) -> None:
        """Copy selected files to the destination folder with a dry-run preview."""
        sources = self._selected_source_paths()
        if not sources:
            QMessageBox.information(self, "Copy", "No files selected.")
            return

        dest_raw = (self._dest_edit.text() or "").strip().rstrip("\\/")
        if not dest_raw:
            QMessageBox.information(self, "Copy", "Destination folder is required.")
            return

        try:
            dest_dir = self._destination_path_from_edit()
        except ValueError as exc:
            QMessageBox.information(self, "Copy", str(exc))
            return
        try:
            plan = self._mover.build_move_plan(
                sources,
                dest_dir,
                ready_message="Ready to copy.",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Copy preview failed", str(exc))
            return

        _debug_print_plan_preview(dest_dir, sources, plan)

        preview = MovePreviewDialog(parent=self, plan=plan, is_copy=True)
        code = preview.exec()
        if DEBUG_MODE:
            print("DEBUG dialog accepted:", code == QDialog.DialogCode.Accepted)
        if code != QDialog.DialogCode.Accepted:
            self._update_status("Copy cancelled.", show_view_counts=False)
            self._update_ui_state()
            return

        if DEBUG_MODE:
            print("DEBUG about to execute transfer (copy)")
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            copied_count, msg_lines, result = self._mover.execute_copy_plan(plan)
        finally:
            QApplication.restoreOverrideCursor()

        if DEBUG_MODE:
            print("DEBUG success_count:", copied_count)
            print("DEBUG messages:", msg_lines)
            for item in result[:10]:
                print(
                    "DEBUG item:",
                    item.status,
                    item.message,
                    item.source_path,
                    "->",
                    item.destination_path,
                )

        not_copied = sum(1 for p in result if p.status != MoveService.STATUS_COPIED)
        dest_display = _shorten_path_display(dest_dir)
        self._present_transfer_outcome(
            is_copy=True,
            success_count=copied_count,
            skipped_count=not_copied,
            items=result,
            msg_lines=msg_lines,
            dest_display=dest_display,
        )
        self._apply_filters(preserve_selection=False)
        if copied_count > 0:
            self._update_status(f"Copied {copied_count} file(s).", show_view_counts=False)
        else:
            self._update_status(
                "Copy finished with no successful copies.",
                show_view_counts=False,
            )
        self._update_ui_state()

    def _move_selected(self) -> None:
        sources = self._selected_source_paths()
        if not sources:
            QMessageBox.information(self, "Move Selected", "No files selected.")
            return

        dest_raw = (self._dest_edit.text() or "").strip().rstrip("\\/")
        if not dest_raw:
            QMessageBox.information(
                self, "Move Selected", "Destination folder is required."
            )
            return

        try:
            dest_dir = self._destination_path_from_edit()
        except ValueError as exc:
            QMessageBox.information(self, "Move Selected", str(exc))
            return
        try:
            plan = self._mover.build_move_plan(sources, dest_dir)
        except Exception as exc:
            QMessageBox.critical(self, "Move preview failed", str(exc))
            return

        _debug_print_plan_preview(dest_dir, sources, plan)

        preview = MovePreviewDialog(parent=self, plan=plan, is_copy=False)
        code = preview.exec()
        if DEBUG_MODE:
            print("DEBUG dialog accepted:", code == QDialog.DialogCode.Accepted)
        if code != QDialog.DialogCode.Accepted:
            self._update_status("Move cancelled.", show_view_counts=False)
            self._update_ui_state()
            return

        if self._settings_service.confirm_before_move():
            reply = QMessageBox.question(
                self,
                "Confirm Move",
                "Move selected file(s) to the destination folder?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._update_status("Move cancelled.", show_view_counts=False)
                self._update_ui_state()
                return

        if DEBUG_MODE:
            print("DEBUG about to execute transfer (move)")
        try:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            moved_count, msg_lines, moved = self._mover.execute_move_plan(plan)
        finally:
            QApplication.restoreOverrideCursor()

        if DEBUG_MODE:
            print("DEBUG success_count:", moved_count)
            print("DEBUG messages:", msg_lines)
            for item in moved[:10]:
                print(
                    "DEBUG item:",
                    item.status,
                    item.message,
                    item.source_path,
                    "->",
                    item.destination_path,
                )

        not_moved = sum(1 for p in moved if p.status != MoveService.STATUS_MOVED)
        dest_display = _shorten_path_display(dest_dir)
        self._present_transfer_outcome(
            is_copy=False,
            success_count=moved_count,
            skipped_count=not_moved,
            items=moved,
            msg_lines=msg_lines,
            dest_display=dest_display,
        )

        moved_sources = {
            safe_resolve_path(Path(p.source_path))
            for p in moved
            if p.status == MoveService.STATUS_MOVED
        }
        if moved_sources:
            self._all_records = [
                r
                for r in self._all_records
                if safe_resolve_path(r.path) not in moved_sources
            ]
        self._apply_filters(preserve_selection=False)
        if moved_count > 0:
            self._update_status(f"Moved {moved_count} file(s).", show_view_counts=False)
        else:
            self._update_status(
                "Move finished with no successful moves.",
                show_view_counts=False,
            )
        self._update_ui_state()

    def _export_view(self) -> None:
        if not self._view_records:
            QMessageBox.information(self, "Export CSV", "No rows to export.")
            return

        default_path = str(EXPORT_DIR / "meshstager_export.csv")

        filename, _filter = QFileDialog.getSaveFileName(
            self,
            "Export CSV",
            default_path,
            "CSV Files (*.csv)",
        )
        if not filename:
            return
        n = len(self._view_records)
        try:
            self._exporter.export_csv(
                self._view_records,
                Path(filename),
                metadata_registry=self._metadata_registry,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", str(exc))
            return
        row_word = "row" if n == 1 else "rows"
        self._update_status(status_export_complete())
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(status_export_complete(), 5000)
        QMessageBox.information(
            self,
            "Export CSV",
            f"Exported {n:,} visible {row_word} to:\n{filename}",
        )

    def _about(self) -> None:
        AboutDialog(parent=self).exec()

    def _context_action_enabled(self, spec: ContextActionSpec) -> bool:
        records = self.selected_records()
        has_selection = bool(records)
        has_source = bool(self._current_source)

        if spec.requires_selection and not has_selection:
            return False
        if spec.requires_source and not has_source:
            return False
        n = len(records)
        if spec.selection_count_min is not None and n < spec.selection_count_min:
            return False
        if spec.selection_count_max is not None and n > spec.selection_count_max:
            return False
        if self._asset_mode != ASSET_MODE_3D and spec.key in (
            "blender_thumbnail",
            "blender_thumbnails_batch",
            "open_thumb_job_folder",
        ):
            return False
        if spec.key == "open_in_blender":
            if not has_selection or len(records) != 1:
                return False
            rec = records[0]
            exe = find_blender_executable(self._settings_service)
            if exe is None:
                return False
            return rec.path.suffix.lower() in {".blend"}
        if spec.key == "open_in_maya":
            if not has_selection or len(records) != 1:
                return False
            rec = records[0]
            exe = find_maya_executable(self._settings_service)
            if exe is None:
                return False
            return rec.path.suffix.lower() in {".ma", ".mb"}
        if spec.key == "open_in_preferred_dcc":
            if not has_selection or len(records) != 1:
                return False
            if self._asset_mode != ASSET_MODE_3D:
                return False
            rec = records[0]
            ext = rec.path.suffix.lower()
            pref = self._settings_service.preferred_dcc()
            profile = (
                get_dcc_profile(pref)
                if pref != "auto"
                else dcc_profile_for_extension(ext)
            )
            if profile is None or not profile.capabilities.can_open:
                return False
            if ext not in profile.supported_extensions:
                return False
            exe = configured_executable_for_profile(profile, self._settings_service)
            return exe is not None
        if spec.key == "open_thumb_job_folder":
            if not has_selection or len(records) != 1:
                return False
            out_dir = self._thumb_controller.failure_output_dir(records[0])
            return out_dir is not None
        return True

    def _dcc_open_disabled_tooltip(self, spec_key: str) -> str:
        if spec_key == "open_in_maya":
            return "Maya is not configured. Set the Maya executable path in Settings."
        if spec_key == "open_in_blender":
            return "Blender is not configured. Set the Blender executable path in Settings."
        if spec_key == "open_in_preferred_dcc":
            return "Preferred DCC is not available for this file. Check Settings → Preferred DCC."
        return ""

    def _open_file_path(self, path: Path) -> None:
        """Open a file with the OS default application; surface failures in the UI."""
        if not path.is_file():
            QMessageBox.warning(
                self, "Open File", "The selected file no longer exists."
            )
            return

        try:
            ok = QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(path.resolve()))
            )
        except Exception as exc:
            QMessageBox.warning(
                self, "Open File", f"Could not open file.\n{exc}"
            )
            return

        if not ok:
            QMessageBox.warning(
                self,
                "Open File",
                "Windows could not open this file. There may be no default application "
                "assigned.",
            )

    def _open_with_preferred_dcc_or_default(self, path: Path) -> None:
        """
        Route open to the user’s preferred DCC when possible; otherwise fall back to the OS default.
        """
        if self._asset_mode != ASSET_MODE_3D:
            self._open_file_path(path)
            return
        if not path.is_file():
            self._open_file_path(path)
            return

        preferred = self._settings_service.preferred_dcc()
        ext = path.suffix.lower()
        profile = get_dcc_profile(preferred) if preferred != "auto" else dcc_profile_for_extension(ext)
        if profile is None or not profile.capabilities.can_open:
            self._open_file_path(path)
            return
        if ext not in profile.supported_extensions:
            self._open_file_path(path)
            return
        exe = configured_executable_for_profile(profile, self._settings_service)
        if exe is None:
            self._open_file_path(path)
            return
        try:
            subprocess.Popen([str(exe), str(path)], close_fds=True)  # noqa: S603,S607
            return
        except OSError:
            self._open_file_path(path)

    def _open_selected_file(self) -> None:
        records = self.selected_records()
        if not records:
            return
        self._open_file_path(records[0].path)

    def _set_blender_job_status(self, state: str, detail: str = "") -> None:
        """Show Queued / Running / Complete / Failed on the Bridge footer line."""
        if state == "Idle" and not detail:
            self._refresh_blender_readiness_label()
            return
        resolved = find_blender_executable(self._settings_service)
        readiness = describe_blender_readiness(self._settings_service, resolved)
        self._status_blender_label.setText(
            format_bridge_footer(
                readiness=readiness,
                job_state=state,
                job_detail=detail,
            )
        )

    def _generate_blender_thumbnail(self) -> None:
        """Run the proof-of-concept headless thumbnail job (STL/OBJ, non-destructive)."""
        if self._asset_mode != ASSET_MODE_3D:
            sb = self.statusBar()
            if sb is not None:
                sb.showMessage(
                    "Blender thumbnails are available in 3D Asset Mode (.stl / .obj / .fbx)",
                    5000,
                )
            return
        records = self.selected_records()
        if len(records) != 1:
            QMessageBox.information(
                self,
                "Blender Thumbnail",
                "Select exactly one file in the current view (table or gallery).",
            )
            return
        path = records[0].path
        if is_ignored_path(path):
            QMessageBox.information(
                self,
                "Blender Thumbnail",
                "This file looks like a hidden/system metadata artifact and will be ignored.\n\n"
                f"File: {path.name}",
            )
            return
        if path.suffix.lower() not in (".stl", ".obj", ".fbx"):
            QMessageBox.information(
                self,
                "Blender Thumbnail",
                "This proof of concept only supports .stl, .obj, and .fbx files.\n"
                f"Current file: {path.name}",
            )
            return
        ok, err, _reject = self._try_enqueue_thumbnail_record(
            records[0],
            origin=JobOrigin.MANUAL_SINGLE,
            manual_override=ThumbnailManualOverride.DEFAULT,
        )
        if not ok:
            QMessageBox.warning(
                self,
                "Blender Thumbnail",
                err,
            )
            return
        n = self._bridge_queue.queue_length()
        if self.statusBar() is not None:
            self.statusBar().showMessage(
                f"Thumbnail job queued (bridge queue: {n}). It will run in the background.",
                5000,
            )

    def _regenerate_thumbnail_native(self) -> None:
        """Regenerate the selected mesh thumbnail using the native CPU renderer."""
        records = self.selected_records()
        if len(records) != 1:
            return
        if not self._native_renderer_health.available:
            QMessageBox.warning(
                self,
                "Native renderer unavailable",
                self._native_renderer_health.manual_native_warning,
            )
            return
        self._try_enqueue_thumbnail_record(
            records[0],
            origin=JobOrigin.MANUAL_SINGLE,
            manual_override=ThumbnailManualOverride.NATIVE,
        )

    def _regenerate_thumbnail_blender(self) -> None:
        """Regenerate the selected mesh thumbnail using Blender Bridge."""
        records = self.selected_records()
        if len(records) != 1:
            return
        self._try_enqueue_thumbnail_record(
            records[0],
            origin=JobOrigin.MANUAL_SINGLE,
            manual_override=ThumbnailManualOverride.BLENDER,
        )

    def _queue_blender_thumbnails_selected(self) -> None:
        """Queue thumbnail jobs for all selected .stl / .obj / .fbx files; skip the rest with a summary."""
        if self._asset_mode != ASSET_MODE_3D:
            sb = self.statusBar()
            if sb is not None:
                sb.showMessage(
                    "Blender thumbnails are available in 3D Asset Mode (.stl / .obj / .fbx)",
                    5000,
                )
            return
        records = self.selected_records()
        if len(records) < 2:
            return
        mesh_ext = frozenset({".stl", ".obj", ".fbx"})
        total_selected = len(records)
        skipped_type = 0
        skipped_ignored = 0
        for r in records:
            if is_ignored_path(r.path):
                skipped_ignored += 1
                continue
            if r.path.suffix.lower() not in mesh_ext:
                skipped_type += 1
        mesh_paths = [
            r.path
            for r in records
            if (not is_ignored_path(r.path)) and r.path.suffix.lower() in mesh_ext
        ]
        skipped_missing = sum(1 for p in mesh_paths if not p.is_file())
        to_queue = [p for p in mesh_paths if p.is_file()]

        if not to_queue:
            QMessageBox.information(
                self,
                "Blender Thumbnails",
                f"No .stl, .obj, or .fbx files to queue (or files are missing).\n\n"
                f"Selected rows: {total_selected}\n"
                f"Skipped (hidden/system metadata): {skipped_ignored}\n"
                f"Skipped (unsupported file type): {skipped_type}\n"
                f"Skipped (file not found on disk): {skipped_missing}",
            )
            return

        queued = 0
        blender_error = ""
        for p in to_queue:
            rec = self._record_for_source_path(p)
            if rec is None:
                continue
            ok, err, reject = self._try_enqueue_thumbnail_record(
                rec,
                origin=JobOrigin.MANUAL_BATCH,
                manual_override=ThumbnailManualOverride.BLENDER,
            )
            if not ok:
                blender_error = err
                break
            queued += 1

        not_enqueued = len(to_queue) - queued
        after = self._bridge_queue.queue_length()
        lines: list[str] = [f"Queued: {queued}"]
        if skipped_ignored:
            lines.append(f"Skipped (hidden/system metadata): {skipped_ignored}")
        if skipped_type:
            lines.append(
                f"Skipped (unsupported file type, not .stl/.obj/.fbx): {skipped_type}"
            )
        if skipped_missing:
            lines.append(f"Skipped (file not found on disk): {skipped_missing}")
        if not_enqueued > 0:
            if blender_error:
                lines.append(f"Not enqueued (stopped after error): {not_enqueued}")
            else:
                lines.append(f"Not enqueued: {not_enqueued}")
        if blender_error:
            lines.append("")
            lines.append(blender_error)
        lines.append(f"Queue size now: {after}")

        QMessageBox.information(
            self,
            "Blender Thumbnails",
            "\n".join(lines),
        )
        if self.statusBar() is not None and queued:
            self.statusBar().showMessage(
                f"Blender: {queued} thumbnail job(s) queued (Queue: {after}).",
                6000,
            )

    def _on_bridge_queue_count_changed(self, n: int) -> None:
        """Update header label and menu actions for queue depth."""
        if self._shutting_down:
            return
        self._sync_bridge_paint_diagnostics()
        # Keep the header clean; show queue depth directly on the Jobs button.
        self._blender_jobs_header_btn.setText("Jobs" if n <= 0 else f"Jobs ({n})")
        self._cancel_all_pending_action.setEnabled(n > 0)
        if self._suppress_per_job_thumb_ui():
            self._refresh_status_counts_strip()
            return
        try:
            queued = [
                (r.source_path.resolve() if r.source_path is not None else None)
                for r in self._bridge_queue.pending_jobs()
            ]
            queued2 = [p for p in queued if p is not None]
        except OSError:
            queued2 = []
        self._thumb_controller.set_queued_source_paths(queued2)
        self._update_thumb_queue_status()
        self._refresh_status_counts_strip()

    def _on_bridge_running_job_changed(self, job_id) -> None:  # type: ignore[no-untyped-def]
        """Show which job id is running in the status line (or clear when idle)."""
        if self._shutting_down:
            return
        if self._suppress_per_job_thumb_ui():
            return
        if job_id is None or job_id == "":
            if self._bridge_queue.queue_length() == 0:
                self._set_blender_job_status("Idle", "")
        else:
            self._set_blender_job_status("Running", str(job_id)[:20])
        self._update_thumb_queue_status()

    def _on_bridge_running_source_changed(self, path) -> None:  # type: ignore[no-untyped-def]
        """Update which file is actively generating a thumbnail (for card state)."""
        if self._shutting_down:
            return
        if self._suppress_per_job_thumb_ui():
            return
        try:
            p = Path(path) if path else None
        except (TypeError, ValueError):
            p = None
        self._thumb_controller.set_generating_source_path(p)
        self._update_thumb_queue_status()

    def _update_thumb_queue_status(self) -> None:
        """Footer status: bridge thumb jobs vs async decode jobs (Prime v0.5)."""
        self._status_thumbs_label.setText(
            format_thumbnail_footer(
                generating=self._thumb_controller.generating_count(),
                queued=self._thumb_controller.queued_count(),
                decoding=self._thumb_controller.decoding_count(),
            )
        )

    def _on_thumbnail_job_completed(self, result: BridgeJobResult) -> None:
        """
        Thumbnail job finished (native CPU or Blender Bridge): severity-aware UX.

        Background and batch failures are non-blocking: the Jobs panel/history,
        the failed thumbnail card, and a footer toast carry the failure forward.
        Manual single-file failures still raise the diagnostic modal because the
        user is actively waiting on that exact result.
        """
        if self._shutting_down:
            return
        if (
            result.status == BridgeJobStatus.COMPLETE
            and result.source_file
            and (result.job_type or "").strip() == "native_thumbnail"
        ):
            try:
                self._apply_render_geometry_backfill(Path(result.source_file))
            except (TypeError, ValueError, OSError) as exc:
                logger.debug("render geometry backfill skipped: %s", exc)
        t0 = time.perf_counter()
        origin = self._bridge_queue.pop_job_origin_for_job_id(result.job_id)
        if origin is None and result.source_file:
            origin = self._native_job_origins.pop(_norm_path_key(result.source_file), None)
        if (
            result.status == BridgeJobStatus.FAILED
            and result.fallback_reason
            and result.source_file
        ):
            rec = self._record_for_source_path(Path(result.source_file))
            if rec is not None:
                src = thumbnail_path_for_record(rec)
                fail_plan = route_thumbnail(
                    src,
                    self._settings_service,
                    for_auto_enqueue=True,
                )
                if fail_plan.fallback_to_blender_on_native_fail:
                    self._thumb_controller.paint_diagnostics().note_blender_fallback_jobs(1)
                    self._try_enqueue_thumbnail_record(
                        rec,
                        origin=origin or JobOrigin.BACKGROUND_AUTO,
                        manual_override=ThumbnailManualOverride.BLENDER,
                        for_auto_enqueue=False,
                    )
        suppress_ui = self._prime_perf_active and origin in (
            JobOrigin.BACKGROUND_AUTO,
            JobOrigin.MANUAL_BATCH,
        )

        self._thumb_controller.on_job_result(result, refresh_ui=not suppress_ui)
        self._update_metadata_cache_from_bridge_result(result)
        self._record_non_renderable_result(result)
        if result.source_file:
            src_key = _norm_path_key(result.source_file)
            self._lazy_thumb_health.invalidate_key(src_key)
            if suppress_ui:
                self._thumb_refresh_accumulator.add_path_key(src_key)
            else:
                rec = self._record_for_source_path(Path(result.source_file))
                if rec is not None:
                    self._lazy_thumb_health.resolve(rec)
                    self._emit_thumb_health_rows([rec])

        if suppress_ui:
            self._thumb_batch_progress.note_completion()
            if not self._thumb_progress_timer.isActive():
                self._thumb_progress_timer.start()
            if result.status == BridgeJobStatus.FAILED:
                logger.warning(
                    "Bridge thumbnail job %s failed (origin=%s, source=%s): %s",
                    result.job_id,
                    origin.value if origin is not None else "unknown",
                    result.source_file or "—",
                    (result.error_message or "no error message").splitlines()[0]
                    if result.error_message
                    else "no error message",
                )
            if result.status != BridgeJobStatus.CANCELLED:
                self._on_thumb_progress_tick()
            return

        self._update_thumb_queue_status()
        t1 = time.perf_counter()
        self._update_asset_inspector()
        t2 = time.perf_counter()

        if result.status == BridgeJobStatus.CANCELLED:
            return
        sb = self.statusBar()
        if result.status == BridgeJobStatus.COMPLETE and result.thumbnail_path:
            self._set_blender_job_status("Complete", "done")
            if sb is not None:
                sb.showMessage(
                    status_thumbnail_ready(Path(result.thumbnail_path).name),
                    5000,
                )
        else:
            self._handle_bridge_job_failure(result, origin)
        if _TIMING_LOGS:
            logger.info(
                "TIMING _on_bridge_job_completed: %.2fms (thumb: %.2fms, inspector: %.2fms) status=%s",
                (time.perf_counter() - t0) * 1000.0,
                (t1 - t0) * 1000.0,
                (t2 - t1) * 1000.0,
                getattr(result.status, "value", str(result.status)),
            )

    def _handle_bridge_job_failure(
        self,
        result: BridgeJobResult,
        origin: JobOrigin | None,
    ) -> None:
        """
        Apply the severity-aware failure policy for a failed bridge job.

        Always logs the failure and updates the status footer + Jobs panel state.
        Only raises the diagnostic modal for :attr:`JobOrigin.MANUAL_SINGLE` —
        background and batch failures stay non-blocking so large gallery scans
        do not interrupt browsing with popups.
        """
        self._set_blender_job_status("Failed", "")
        self._session_thumb_failure_count += 1
        self._refresh_status_counts_strip()

        src_name = ""
        if result.source_file:
            try:
                src_name = Path(result.source_file).name
            except (TypeError, ValueError):
                src_name = ""
        footer = format_thumbnail_failure_footer(
            source_filename=src_name,
            error_message=result.error_message,
        )

        # Logging is always preserved (per spec): never suppress the failure trail.
        # The Jobs panel reads result.json on disk, so the full message stays
        # available there even when the modal is suppressed.
        logger.warning(
            "Bridge thumbnail job %s failed (origin=%s, source=%s): %s",
            result.job_id,
            origin.value if origin is not None else "unknown",
            result.source_file or "—",
            (result.error_message or "no error message").splitlines()[0]
            if result.error_message
            else "no error message",
        )

        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(footer, 8000)

        if result.status == BridgeJobStatus.FAILED and thumbnail_failure_should_show_modal(origin):
            self._show_blender_failure_help(result)

    def _show_blender_failure_help(self, result: BridgeJobResult) -> None:
        """
        Show a calm, actionable failure dialog with one-click log/output actions.

        Throttled to avoid popups when many jobs fail in a batch.
        """
        now = time.monotonic()
        if now - self._last_blender_failure_dialog_s < 5.0:
            return
        self._last_blender_failure_dialog_s = now

        src = (result.source_file or "").strip()
        src_name = Path(src).name if src else "the selected file"
        err = (result.error_message or "Blender reported a failure.").strip()
        if len(err) > 500:
            err = err[:497] + "…"

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Thumbnail job failed")
        box.setText(
            f"MeshStager could not finish a thumbnail for {src_name}. "
            "Details are in the log and the Jobs panel."
        )
        box.setInformativeText(err)

        output_dir = Path(result.output_dir) if result.output_dir else None
        log_path = Path(result.log_path) if result.log_path else None

        btn_open_log = None
        if log_path is not None and log_path.is_file():
            btn_open_log = box.addButton("Open log.txt", QMessageBox.ButtonRole.ActionRole)
        btn_open_out = None
        if output_dir is not None and output_dir.is_dir():
            btn_open_out = box.addButton(
                "Open output folder", QMessageBox.ButtonRole.ActionRole
            )
        btn_copy = None
        if err:
            btn_copy = box.addButton(
                "Copy error message", QMessageBox.ButtonRole.ActionRole
            )
        box.addButton(QMessageBox.StandardButton.Close)

        def _on_clicked(button) -> None:  # type: ignore[no-untyped-def]
            if btn_open_log is not None and button == btn_open_log and log_path is not None:
                open_file_with_default_app(log_path, self, title="Open log")
            elif btn_open_out is not None and button == btn_open_out and output_dir is not None:
                open_folder_in_explorer(output_dir, self, title="Open output folder")
            elif btn_copy is not None and button == btn_copy:
                copy_to_clipboard(err)
                if self.statusBar() is not None:
                    self.statusBar().showMessage("Copied error message to the clipboard.", 4000)

        box.buttonClicked.connect(_on_clicked)
        box.setModal(False)
        box.show()
        self._active_error_boxes.append(box)
        box.finished.connect(lambda _=0, b=box: self._active_error_boxes.remove(b) if b in self._active_error_boxes else None)

    def _on_refresh_thumbnails(self) -> None:
        """Re-scan bridge ``result.json`` files and reload table thumbnail icons."""
        n = self._thumb_controller.refresh_index()
        self._update_asset_inspector()
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(
                f"Thumbnails: index refreshed ({n} source file(s) with Blender output).",
                5000,
            )

    def _on_clear_thumbnail_cache(self) -> None:
        """Clear in-memory thumbnail cache (keeps Blender index and job outputs)."""
        self._thumb_controller.clear_thumbnail_cache()
        self._update_asset_inspector()
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage("Thumbnails: cache cleared.", 5000)

    @staticmethod
    def _prompt_bridge_cleanup_age_key(parent: QWidget, title: str) -> tuple[str, bool]:
        """Ask which age band to include; returns a key for :func:`min_age_seconds_for_ui_choice`."""
        pairs = [
            ("Older than 7 days", "7"),
            ("Older than 30 days", "30"),
            ("Older than 90 days", "90"),
            ("Everything matching this filter…", "all"),
        ]
        labels = [p[0] for p in pairs]
        lookup = {p[0]: p[1] for p in pairs}
        picked, ok = QInputDialog.getItem(
            parent,
            title,
            "Age:",
            labels,
            1,
            False,
        )
        if not ok:
            return "", False
        key = lookup[picked]
        return key, True

    def _run_manual_bridge_cleanup(
        self,
        mode: BridgeCleanupManualMode,
        *,
        title: str,
    ) -> None:
        age_key, ok = MainWindow._prompt_bridge_cleanup_age_key(self, title)
        if not ok:
            return

        min_age = min_age_seconds_for_ui_choice(age_key)

        bp = resolve_bridge_paths()
        root = bridge_runtime_root()
        now_ts = time.time()
        summary = plan_manual_cleanup(
            bp,
            bridge_root=root,
            mode=mode,
            now_ts=now_ts,
            min_age_seconds=min_age,
        )
        if not summary.paths:
            QMessageBox.information(
                self,
                title,
                "Nothing matched these filters. Bridge storage is already tidy for this choice.",
            )
            return

        human_sz = format_byte_size_human(summary.estimated_bytes)
        lines = [
            "Will remove:",
            "",
            f"- {summary.job_ids_distinct_count} jobs",
            f"- {len(summary.paths)} files/folders",
            f"- {human_sz} reclaimed",
            "",
            "Source folders and user files are never touched.",
            "",
            "Continue?",
        ]
        reply = QMessageBox.question(
            self,
            title,
            "\n".join(lines),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        result = execute_cleanup(summary, bridge_root=root)
        refreshed = self._thumb_controller.refresh_index()
        self._update_asset_inspector()
        freed = format_byte_size_human(result.freed_bytes_logged)
        parts = [
            f"Removed {result.deleted} bridge item(s)",
            f"freed about {freed}",
        ]
        if result.errors:
            parts.append(f"{result.errors} skipped (in use or protected)")
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(
                "Bridge cleanup • " + " • ".join(parts) + f" (thumbnails refreshed: {refreshed}).",
                12000,
            )

    def _on_bridge_cleanup_clean_old_jobs(self) -> None:
        self._run_manual_bridge_cleanup(
            BridgeCleanupManualMode.CLEAN_OLD_BRIDGE_OUTPUT_JOBS,
            title="Clean old thumbnail jobs",
        )

    def _on_bridge_cleanup_failed_only(self) -> None:
        self._run_manual_bridge_cleanup(
            BridgeCleanupManualMode.FAILED_BRIDGE_JOBS_ONLY,
            title="Delete failed thumbnail jobs",
        )

    def _on_bridge_cleanup_completed_only(self) -> None:
        self._run_manual_bridge_cleanup(
            BridgeCleanupManualMode.COMPLETED_BRIDGE_JOBS_ONLY,
            title="Delete completed thumbnail jobs",
        )

    def _on_bridge_open_storage_folder(self) -> None:
        root = bridge_runtime_root()
        try:
            resolve_bridge_paths()
            root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            QMessageBox.warning(self, "Bridge storage", str(exc))
            return
        url = QUrl.fromLocalFile(str(root))
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(self, "Bridge storage", "Could not open the folder in Explorer.")

    def _maybe_autotrim_bridge_storage_at_startup(self) -> None:
        """Quietly remove very old bridge artifacts based on Settings (no modal)."""
        days = self._settings_service.bridge_history_keep_days()
        if days == int(SettingsService.BRIDGE_HISTORY_FOREVER_DAYS):
            return

        bp = resolve_bridge_paths()
        root = bridge_runtime_root()
        summary = plan_startup_retention(bp, bridge_root=root, retention_days=int(days))
        if not summary.paths:
            logger.info(
                "Bridge retention: nothing eligible (keep_last_days=%s).",
                days,
            )
            return

        result = execute_cleanup(summary, bridge_root=root)
        _ = self._thumb_controller.refresh_index()
        self._update_asset_inspector()
        freed = format_byte_size_human(result.freed_bytes_logged)
        msg = (
            f"Removed {summary.job_ids_distinct_count} old job bundle(s)"
            + (f"; {result.errors} item(s) skipped" if result.errors else "")
            + f" • Freed ~{freed}"
        )
        sb = self.statusBar()
        if sb is not None:
            sb.showMessage(f"Bridge storage: trimmed • {msg}", 9000)
        logger.info("Bridge retention: %s", msg)

    def _open_blender_job_history_dialog(self) -> None:
        """Show recent Blender Bridge jobs (from output folders; no Blender required)."""
        BlenderJobHistoryDialog(self).exec()

    def _open_blender_pending_queue_dialog(self) -> None:
        """Show jobs still waiting in the in-memory + pending folder queue."""
        BlenderQueueDialog(self._bridge_queue, self).exec()
        self._on_bridge_queue_count_changed(self._bridge_queue.queue_length())

    def _cancel_all_blender_pending(self) -> None:
        """Cancel every job still waiting (not the one currently in Blender)."""
        n = self._bridge_queue.cancel_all_queued()
        if n:
            if self.statusBar() is not None:
                self.statusBar().showMessage(
                    f"Cancelled {n} pending Blender job(s).", 5000
                )
        else:
            QMessageBox.information(
                self,
                "Cancel all",
                "There is nothing in the queue to cancel.",
            )

    def _build_file_context_menu(self) -> QMenu:
        menu = QMenu(self)
        for spec in FILE_CONTEXT_ACTIONS:
            if spec.separator_before:
                menu.addSeparator()
            action = QAction(spec.label, self)
            base_enabled = self._context_action_enabled(spec)
            action.setEnabled(base_enabled)
            if (
                spec.key in ("open_in_maya", "open_in_blender", "open_in_preferred_dcc")
                and not base_enabled
            ):
                tt = self._dcc_open_disabled_tooltip(spec.key)
                if tt:
                    action.setToolTip(tt)
                    action.setStatusTip(tt)
            handler = getattr(self, spec.handler_name, None)
            if handler is not None:
                action.triggered.connect(handler)
            else:
                action.setEnabled(False)
            menu.addAction(action)
        self._collections.add_context_actions(menu)
        return menu

    def _open_in_blender(self) -> None:
        records = self.selected_records()
        if len(records) != 1:
            return
        exe = find_blender_executable(self._settings_service)
        if exe is None:
            QMessageBox.information(
                self,
                "Blender",
                "Blender is not configured. Set the Blender executable path in Settings.",
            )
            return
        path = records[0].path
        try:
            subprocess.Popen([str(exe), str(path)], close_fds=True)  # noqa: S603,S607
        except OSError as exc:
            QMessageBox.warning(self, "Blender", f"Could not launch Blender.\n{exc}")

    def _open_in_maya(self) -> None:
        records = self.selected_records()
        if len(records) != 1:
            return
        exe = find_maya_executable(self._settings_service)
        if exe is None:
            QMessageBox.information(
                self,
                "Maya",
                "Maya is not configured. Set the Maya executable path in Settings.",
            )
            return
        path = records[0].path
        try:
            subprocess.Popen([str(exe), str(path)], close_fds=True)  # noqa: S603,S607
        except OSError as exc:
            QMessageBox.warning(self, "Maya", f"Could not launch Maya.\n{exc}")

    def _open_in_preferred_dcc(self) -> None:
        """Open the selected file using the Preferred DCC routing rule (or fall back to OS default)."""
        records = self.selected_records()
        if len(records) != 1:
            return
        self._open_with_preferred_dcc_or_default(records[0].path)

    def _show_table_context_menu(self, pos) -> None:  # type: ignore[no-untyped-def]
        menu = self._build_file_context_menu()
        global_pos = self._table.viewport().mapToGlobal(pos)
        menu.exec(global_pos)

    def _open_thumb_job_folder(self) -> None:
        """Open the Blender bridge output folder for the last failed thumbnail job on this file."""
        records = self.selected_records()
        if len(records) != 1:
            return
        out_dir = self._thumb_controller.failure_output_dir(records[0])
        if out_dir is None:
            QMessageBox.information(
                self,
                "Thumbnail job folder",
                "No failed thumbnail job folder is recorded for this file, or it was removed.",
            )
            return
        open_folder_in_explorer(out_dir, self, title="Thumbnail job folder")

    def _reveal_selected(self) -> None:
        path = self._selected_first_path()
        if path is None:
            QMessageBox.information(
                self,
                "Reveal in Explorer",
                "Select one or more files in the table first.",
            )
            return
        self._reveal_in_explorer(path)

    def _copy_selected_path(self) -> None:
        path = self._selected_first_path()
        if path is None:
            QMessageBox.information(
                self,
                "Copy Selected Path",
                "Select one or more files in the table first.",
            )
            return
        QApplication.clipboard().setText(str(path))
        self._update_status(status_path_copied())

    def _reveal_in_explorer(self, path: Path) -> None:
        try:
            if path.exists():
                subprocess.run(["explorer", "/select,", str(path)], check=False)
            else:
                QMessageBox.warning(
                    self,
                    "Reveal in Explorer",
                    "The selected file is no longer at this path. "
                    "Opening its parent folder instead.",
                )
                subprocess.run(["explorer", str(path.parent)], check=False)
        except Exception as exc:
            QMessageBox.warning(self, "Explorer", f"Could not open Explorer: {exc}")
