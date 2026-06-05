"""Pre-scan assessment for large / server folder warnings (Roundup)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings

from meshcorral.services.archive_manifest_cache import ArchiveManifestCache
from meshcorral.services.settings_service import SettingsService
from meshcorral.utils.path_perf import SLOW_SCAN_ELAPSED_SECONDS, is_network_like_path
from meshcorral.utils.scan_ignores import IGNORED_DIRNAMES, is_ignored_file, is_ignored_path

logger = logging.getLogger(__name__)

# Default trigger: estimated matching assets before scan.
DEFAULT_FILE_COUNT_WARNING_THRESHOLD: int = 2500

# Archive-heavy when at least this many .zip files are seen in the preflight walk.
ARCHIVE_HEAVY_ZIP_THRESHOLD: int = 12

# Directory tree depth (root = 0) that suggests a very deep hierarchy.
DEEP_DIRECTORY_DEPTH_THRESHOLD: int = 10

# Cap preflight walk so the warning dialog stays responsive.
PREFLIGHT_MAX_FILES_TO_COUNT: int = 2600


@dataclass(frozen=True, slots=True)
class FolderScopeEstimate:
    """Fast pre-scan counts used to decide whether to show the warning."""

    matching_file_count: int
    exceeds_file_threshold: bool
    archive_zip_count: int
    max_directory_depth: int
    preflight_truncated: bool


@dataclass(frozen=True, slots=True)
class LargeFolderAssessment:
    """Inputs for :class:`~meshcorral.ui.large_folder_warning_dialog.LargeFolderWarningDialog`."""

    source_path: str
    network_like: bool
    estimate: FolderScopeEstimate
    prior_slow_folder: bool
    auto_thumbnails_enabled: bool
    prior_cached_count: int
    would_use_lightweight: bool
    file_count_threshold: int
    thumbnail_mode_label: str
    cache_mode_label: str

    @property
    def should_warn(self) -> bool:
        """Return True when any trigger condition is active."""
        return bool(self.trigger_reasons())

    def trigger_reasons(self) -> tuple[str, ...]:
        """Human-readable reasons the warning would be shown."""
        reasons: list[str] = []
        est = self.estimate
        if est.exceeds_file_threshold:
            reasons.append("large_file_count")
        if self.network_like:
            reasons.append("network_path")
        if est.archive_zip_count >= ARCHIVE_HEAVY_ZIP_THRESHOLD:
            reasons.append("archive_heavy")
        if est.max_directory_depth >= DEEP_DIRECTORY_DEPTH_THRESHOLD:
            reasons.append("deep_tree")
        if self.prior_slow_folder:
            reasons.append("prior_slow_scan")
        if self.network_like and self.auto_thumbnails_enabled:
            reasons.append("auto_thumbs_on_remote")
        return tuple(reasons)


@dataclass(frozen=True, slots=True)
class LargeFolderWarningPersistence:
    """QSettings-backed persistence for large-folder warnings."""

    KEY_SKIP_ALL = "warnings/skip_large_folder_warning"
    KEY_SKIP_REMOTE_ONLY = "warnings/skip_large_folder_warning_for_remote_only"
    KEY_SLOW_REGISTRY = "warnings/slow_folder_registry"
    KEY_LAST_TELEMETRY = "warnings/last_scan_telemetry"

    settings: QSettings

    def skip_all_warnings(self) -> bool:
        """When True, never show the large-folder warning."""
        return _read_bool(self.settings, self.KEY_SKIP_ALL, False)

    def set_skip_all_warnings(self, value: bool) -> None:
        """Persist global skip for large-folder warnings."""
        self.settings.setValue(self.KEY_SKIP_ALL, bool(value))

    def skip_remote_only(self) -> bool:
        """When True, skip warnings only for network-like paths."""
        return _read_bool(self.settings, self.KEY_SKIP_REMOTE_ONLY, False)

    def set_skip_remote_only(self, value: bool) -> None:
        """Persist remote-only skip (local large folders may still warn)."""
        self.settings.setValue(self.KEY_SKIP_REMOTE_ONLY, bool(value))

    def should_show_warning(self, assessment: LargeFolderAssessment) -> bool:
        """Apply user skip preferences to *assessment*."""
        if not assessment.should_warn:
            return False
        if self.skip_all_warnings():
            return False
        if self.skip_remote_only() and assessment.network_like:
            return False
        return True

    def is_slow_folder(self, source_path: str) -> bool:
        """Return True when a prior scan marked this folder as slow."""
        key = slow_folder_key(source_path)
        registry = _load_slow_registry(self.settings)
        return key in registry

    def record_scan_telemetry(
        self,
        *,
        source_path: str,
        scan_duration_s: float | None,
        file_count: int,
        network_like: bool,
        thumbnail_queued: int,
        cancelled: bool,
    ) -> None:
        """
        Store last-scan telemetry and update slow-folder registry for future heuristics.

        Future passes can use this data to pre-flag folders without blocking scans.
        """
        payload: dict[str, Any] = {
            "source_path": source_path,
            "scan_duration_s": scan_duration_s,
            "file_count": file_count,
            "network_like": network_like,
            "thumbnail_queued": thumbnail_queued,
            "cancelled": cancelled,
        }
        try:
            self.settings.setValue(self.KEY_LAST_TELEMETRY, json.dumps(payload))
        except (TypeError, ValueError):
            logger.debug("telemetry json encode failed", exc_info=True)
        if cancelled:
            return
        if scan_duration_s is None:
            return
        try:
            elapsed = float(scan_duration_s)
        except (TypeError, ValueError):
            return
        if elapsed < SLOW_SCAN_ELAPSED_SECONDS:
            return
        if file_count < 200 and not network_like:
            return
        registry = _load_slow_registry(self.settings)
        key = slow_folder_key(source_path)
        registry[key] = {
            "last_elapsed_s": elapsed,
            "file_count": int(file_count),
            "network_like": bool(network_like),
        }
        _save_slow_registry(self.settings, registry)


def slow_folder_key(source_path: str) -> str:
    """Normalize a scan root for slow-folder registry lookups."""
    if is_network_like_path(Path(source_path)):
        return str(source_path).casefold()
    try:
        return str(Path(source_path).resolve()).casefold()
    except OSError:
        return str(source_path).casefold()


def _read_bool(settings: QSettings, key: str, default: bool) -> bool:
    value = settings.value(key, default)
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _load_slow_registry(settings: QSettings) -> dict[str, dict[str, Any]]:
    raw = settings.value(LargeFolderWarningPersistence.KEY_SLOW_REGISTRY, "")
    if not raw:
        return {}
    try:
        data = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def _save_slow_registry(settings: QSettings, registry: dict[str, dict[str, Any]]) -> None:
    try:
        settings.setValue(
            LargeFolderWarningPersistence.KEY_SLOW_REGISTRY,
            json.dumps(registry),
        )
    except (TypeError, ValueError):
        logger.debug("slow registry save failed", exc_info=True)


def network_preflight_scope_estimate() -> FolderScopeEstimate:
    """
    Placeholder estimate for network/UNC paths.

    Deep preflight walks are skipped on the UI thread; the scan worker discovers
    file counts. ``network_path`` and related triggers still apply via
    :func:`build_large_folder_assessment`.
    """
    return FolderScopeEstimate(
        matching_file_count=0,
        exceeds_file_threshold=False,
        archive_zip_count=0,
        max_directory_depth=0,
        preflight_truncated=True,
    )


def preflight_folder_scope(
    root: Path,
    *,
    recursive: bool,
    allowed_extensions: set[str] | frozenset[str],
    file_count_threshold: int = DEFAULT_FILE_COUNT_WARNING_THRESHOLD,
    archive_heavy_threshold: int = ARCHIVE_HEAVY_ZIP_THRESHOLD,
    max_depth_threshold: int = DEEP_DIRECTORY_DEPTH_THRESHOLD,
    max_files_to_count: int = PREFLIGHT_MAX_FILES_TO_COUNT,
) -> FolderScopeEstimate:
    """
    Walk *root* briefly to estimate scan weight without starting a full scan.

    Counting stops once *max_files_to_count* matching files are seen.
    """
    allow = set(allowed_extensions)
    matching = 0
    archives = 0
    max_depth = 0
    truncated = False
    threshold = max(1, int(file_count_threshold))

    def consider_file(path: Path, depth: int) -> None:
        nonlocal matching, archives, max_depth, truncated
        if depth > max_depth:
            max_depth = depth
        if is_ignored_file(path) or is_ignored_path(path):
            return
        if ArchiveManifestCache.is_supported_archive(path):
            archives += 1
        suffix = path.suffix.lower().strip()
        if not suffix or suffix not in allow:
            return
        matching += 1
        if matching >= max_files_to_count:
            truncated = True

    try:
        root_resolved = root.expanduser()
    except OSError:
        root_resolved = root

    if not recursive:
        try:
            with os.scandir(root_resolved) as entries:
                for entry in entries:
                    if truncated:
                        break
                    try:
                        if not entry.is_file(follow_symlinks=False):
                            continue
                    except OSError:
                        continue
                    consider_file(Path(entry.path), 0)
        except OSError:
            logger.debug("preflight non-recursive failed for %s", root_resolved, exc_info=True)
        exceeds = matching >= threshold
        return FolderScopeEstimate(
            matching_file_count=matching,
            exceeds_file_threshold=exceeds,
            archive_zip_count=archives,
            max_directory_depth=max_depth,
            preflight_truncated=truncated,
        )

    stack: list[tuple[Path, int]] = [(root_resolved, 0)]
    while stack and not truncated:
        dir_path, depth = stack.pop()
        if depth > max_depth:
            max_depth = depth
        try:
            with os.scandir(dir_path) as entries:
                subdirs: list[tuple[Path, int]] = []
                for entry in entries:
                    if truncated:
                        break
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name not in IGNORED_DIRNAMES:
                                subdirs.append((Path(entry.path), depth + 1))
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                    except OSError:
                        continue
                    consider_file(Path(entry.path), depth)
                for sub in reversed(subdirs):
                    stack.append(sub)
        except OSError:
            logger.debug("preflight scandir failed for %s", dir_path, exc_info=True)
    exceeds = matching >= threshold
    return FolderScopeEstimate(
        matching_file_count=matching,
        exceeds_file_threshold=exceeds,
        archive_zip_count=archives,
        max_directory_depth=max_depth,
        preflight_truncated=truncated,
    )


def build_large_folder_assessment(
    source_path: str,
    *,
    recursive: bool,
    allowed_extensions: set[str] | frozenset[str],
    settings_service: SettingsService,
    persistence: LargeFolderWarningPersistence,
    prior_cached_count: int,
    file_count_threshold: int = DEFAULT_FILE_COUNT_WARNING_THRESHOLD,
) -> LargeFolderAssessment:
    """Build a pre-scan assessment for *source_path*."""
    root = Path(source_path)
    network_like = is_network_like_path(root)
    if network_like:
        estimate = network_preflight_scope_estimate()
        logger.debug(
            "large-folder assessment: skipped UI preflight for network path %s",
            source_path,
        )
    else:
        estimate = preflight_folder_scope(
            root,
            recursive=recursive,
            allowed_extensions=allowed_extensions,
            file_count_threshold=file_count_threshold,
        )
    would_lightweight = network_like or prior_cached_count >= 32
    thumb_px = settings_service.thumbnail_display_pixels()
    browse_mode = settings_service.browse_view_mode()
    thumb_label = f"{browse_mode} view, {thumb_px}px thumbnails"
    cache_label = "lightweight scan (metadata-first)" if would_lightweight else "full stat pass"
    return LargeFolderAssessment(
        source_path=source_path,
        network_like=network_like,
        estimate=estimate,
        prior_slow_folder=persistence.is_slow_folder(source_path),
        auto_thumbnails_enabled=settings_service.auto_thumbnail_after_scan(),
        prior_cached_count=prior_cached_count,
        would_use_lightweight=would_lightweight,
        file_count_threshold=file_count_threshold,
        thumbnail_mode_label=thumb_label,
        cache_mode_label=cache_label,
    )


def recommended_dialog_defaults(
    assessment: LargeFolderAssessment,
) -> tuple[bool, bool, bool]:
    """
    Return default checkbox states: visible_thumbs_only, lightweight_scan, background_metadata.

    Network paths auto-enable visible-thumbs-only and lightweight when not already active.
    """
    visible = assessment.network_like
    lightweight = assessment.network_like and not assessment.would_use_lightweight
    background = True
    return visible, lightweight, background
