"""
Prime v1.0 — thumbnail routing policy (native CPU default for local mesh formats).

Selects native CPU, Blender Bridge, or no thumbnail path from file extension,
user preference, and optional manual override.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal

from meshcorral.app.bridge.blender_locator import find_blender_executable
from meshcorral.models.file_record import FileRecord
from meshcorral.services.environment.native_renderer_health import (
    NativeRendererHealth,
    get_native_renderer_health,
)
from meshcorral.services.settings_service import SettingsService
from meshcorral.services.thumbnails.native_thumbnail_backend import NativeThumbnailBackend

ThumbnailBackendChoice = Literal["native", "blender", "none"]

_NATIVE_CPU_EXTENSIONS: frozenset[str] = frozenset({".stl", ".obj", ".ply", ".glb", ".gltf"})
_BLENDER_PREFERRED_EXTENSIONS: frozenset[str] = frozenset({".fbx", ".blend"})
_BLENDER_ONLY_EXTENSIONS: frozenset[str] = frozenset({".blend"})
_OPEN_ONLY_EXTENSIONS: frozenset[str] = frozenset({".ma", ".mb"})

_NATIVE_BACKEND = NativeThumbnailBackend()


class ThumbnailRendererPreference(str, Enum):
    """User setting for automatic thumbnail backend selection."""

    AUTO_RECOMMENDED = "auto_recommended"
    NATIVE_FIRST = "native_first"
    BLENDER_FIRST = "blender_first"
    MANUAL_ONLY = "manual_only"


class ThumbnailManualOverride(str, Enum):
    """Explicit user action override (regenerate menu / inspector)."""

    DEFAULT = "default"
    NATIVE = "native"
    BLENDER = "blender"


@dataclass(frozen=True, slots=True)
class ThumbnailRoutePlan:
    """Resolved routing plan for one source file."""

    backend: ThumbnailBackendChoice
    reason: str
    allow_auto_enqueue: bool
    eligible_for_blender_idle_fill: bool
    thumbnail_backend: str
    thumbnail_render_profile: str
    fallback_to_blender_on_native_fail: bool
    fallback_reason: str | None = None


def _ext(path: Path) -> str:
    return path.suffix.lower().strip()


def thumbnail_path_for_record(record: FileRecord) -> Path:
    """
    Resolve the path used for routing/enqueue from a :class:`FileRecord`.

    Uses ``record.path.suffix`` when present; otherwise ``record.extension``.
    """
    path = Path(record.path)
    if _ext(path):
        return path
    ext = (record.extension or "").lower().strip()
    if not ext:
        return path
    if not ext.startswith("."):
        ext = f".{ext}"
    return path.with_suffix(ext)


def native_cpu_extensions() -> frozenset[str]:
    """Extensions handled by the CPU-native renderer."""
    return _NATIVE_CPU_EXTENSIONS


def blender_preferred_extensions() -> frozenset[str]:
    """Formats where Blender is preferred when configured."""
    return _BLENDER_PREFERRED_EXTENSIONS


def blender_only_extensions() -> frozenset[str]:
    """Formats that only Blender can thumbnail today."""
    return _BLENDER_ONLY_EXTENSIONS


def open_only_extensions() -> frozenset[str]:
    """DCC scene formats with open-only support (no thumbnails)."""
    return _OPEN_ONLY_EXTENSIONS


def is_native_supported(path: Path) -> bool:
    """True when the native CPU backend supports *path*."""
    return _NATIVE_BACKEND.supports(path)


def native_env_force_disabled() -> bool:
    """Emergency override: ``ROUNDUP_NATIVE_THUMBS=0`` disables native routing."""
    raw = os.environ.get("ROUNDUP_NATIVE_THUMBS", "").strip().lower()
    return raw in ("0", "false", "no", "off")


def preference_from_settings(settings: SettingsService) -> ThumbnailRendererPreference:
    """Read renderer preference from settings (invalid → auto recommended)."""
    raw = settings.thumbnail_renderer_preference()
    try:
        return ThumbnailRendererPreference(raw)
    except ValueError:
        return ThumbnailRendererPreference.AUTO_RECOMMENDED


def auto_enqueue_allowed(settings: SettingsService) -> bool:
    """False when preference is manual-only (background queue disabled)."""
    return preference_from_settings(settings) != ThumbnailRendererPreference.MANUAL_ONLY


def native_runtime_available(
    path: Path,
    *,
    native_health: NativeRendererHealth | None = None,
) -> bool:
    """True when native routing may run for *path* (format + deps + env)."""
    health = native_health if native_health is not None else get_native_renderer_health()
    return (
        is_native_supported(path)
        and not native_env_force_disabled()
        and health.available
    )


def route_thumbnail(
    source_path: Path,
    settings: SettingsService,
    *,
    manual_override: ThumbnailManualOverride = ThumbnailManualOverride.DEFAULT,
    for_auto_enqueue: bool = False,
    native_health: NativeRendererHealth | None = None,
) -> ThumbnailRoutePlan:
    """
    Resolve backend selection for *source_path*.

    Parameters
    ----------
    for_auto_enqueue:
        When True, ``manual_only`` preference yields ``backend=none``.
    """
    path = Path(source_path)
    ext = _ext(path)
    preference = preference_from_settings(settings)
    blender_ok = find_blender_executable(settings) is not None
    health = native_health if native_health is not None else get_native_renderer_health()
    format_native = is_native_supported(path) and not native_env_force_disabled()
    native_ok = format_native and health.available
    native_unavailable = format_native and not health.available

    if manual_override == ThumbnailManualOverride.NATIVE:
        if native_ok:
            return _native_plan("manual native override", allow_auto=True, idle=False)
        if native_unavailable:
            return _none_plan(health.manual_native_warning)
        return _none_plan("native override requested but format unsupported")

    if manual_override == ThumbnailManualOverride.BLENDER:
        if blender_ok and ext not in _OPEN_ONLY_EXTENSIONS:
            return _blender_plan("manual blender override", allow_auto=True, idle=False)
        return _none_plan("blender override requested but blender unavailable")

    if preference == ThumbnailRendererPreference.MANUAL_ONLY:
        if for_auto_enqueue:
            return _none_plan("manual-only preference blocks auto enqueue")
        preference = ThumbnailRendererPreference.AUTO_RECOMMENDED

    if ext in _OPEN_ONLY_EXTENSIONS:
        return _none_plan(f"{ext} is open-only (no thumbnail)")

    if ext in _BLENDER_ONLY_EXTENSIONS:
        if blender_ok:
            return _blender_plan(
                f"{ext} requires blender",
                allow_auto=True,
                idle=True,
            )
        return _none_plan(f"{ext} requires blender (not configured)")

    if preference == ThumbnailRendererPreference.BLENDER_FIRST:
        if blender_ok and ext not in _OPEN_ONLY_EXTENSIONS:
            return _blender_plan(
                "blender-first preference",
                allow_auto=True,
                idle=ext in _BLENDER_PREFERRED_EXTENSIONS or ext in _NATIVE_CPU_EXTENSIONS,
            )
        if native_ok:
            return _native_plan(
                "blender-first but blender unavailable; native fallback",
                allow_auto=True,
                idle=False,
                fallback_blender=False,
            )
        if native_unavailable:
            return _none_plan(health.settings_message)
        return _none_plan("no backend available")

    if ext in _BLENDER_PREFERRED_EXTENSIONS:
        if blender_ok:
            return _blender_plan(
                f"{ext} blender-preferred",
                allow_auto=True,
                idle=True,
            )
        if native_unavailable and ext in _NATIVE_CPU_EXTENSIONS:
            return _none_plan(health.settings_message)
        return _none_plan(f"{ext} requires blender (not configured)")

    if native_unavailable and ext in _NATIVE_CPU_EXTENSIONS:
        if blender_ok:
            return _blender_plan(
                f"{ext} native unavailable; blender fallback",
                allow_auto=True,
                idle=True,
                fallback_reason=health.diagnostics_fallback_reason,
            )
        return _none_plan(health.settings_message)

    if native_ok:
        fallback = (
            preference == ThumbnailRendererPreference.NATIVE_FIRST
            and blender_ok
            and ext in _NATIVE_CPU_EXTENSIONS
        ) or (
            preference == ThumbnailRendererPreference.AUTO_RECOMMENDED
            and blender_ok
            and ext in _NATIVE_CPU_EXTENSIONS
        )
        return _native_plan(
            f"{ext} native default",
            allow_auto=True,
            idle=False,
            fallback_blender=fallback,
        )

    if blender_ok:
        return _blender_plan(
            f"{ext} native unsupported; blender fallback",
            allow_auto=True,
            idle=True,
        )

    return _none_plan("no backend available")


def should_skip_blender_for_native_supported(
    source_path: Path,
    settings: SettingsService,
    *,
    for_auto_enqueue: bool = True,
) -> bool:
    """
    True when a Blender enqueue would be skipped because native owns this format.

    Used for Prime diagnostics (``blender_jobs_skipped_native_supported``).
    """
    plan = route_thumbnail(
        source_path,
        settings,
        for_auto_enqueue=for_auto_enqueue,
    )
    return plan.backend == "native" and is_native_supported(source_path)


def _native_plan(
    reason: str,
    *,
    allow_auto: bool,
    idle: bool,
    fallback_blender: bool = True,
) -> ThumbnailRoutePlan:
    return ThumbnailRoutePlan(
        backend="native",
        reason=reason,
        allow_auto_enqueue=allow_auto,
        eligible_for_blender_idle_fill=idle,
        thumbnail_backend="cpu_native",
        thumbnail_render_profile="cpu_native",
        fallback_to_blender_on_native_fail=fallback_blender,
    )


def _blender_plan(
    reason: str,
    *,
    allow_auto: bool,
    idle: bool,
    fallback_reason: str | None = None,
) -> ThumbnailRoutePlan:
    return ThumbnailRoutePlan(
        backend="blender",
        reason=reason,
        allow_auto_enqueue=allow_auto,
        eligible_for_blender_idle_fill=idle,
        thumbnail_backend="blender",
        thumbnail_render_profile="blender",
        fallback_to_blender_on_native_fail=False,
        fallback_reason=fallback_reason,
    )


def _none_plan(reason: str) -> ThumbnailRoutePlan:
    return ThumbnailRoutePlan(
        backend="none",
        reason=reason,
        allow_auto_enqueue=False,
        eligible_for_blender_idle_fill=False,
        thumbnail_backend="none",
        thumbnail_render_profile="none",
        fallback_to_blender_on_native_fail=False,
    )
