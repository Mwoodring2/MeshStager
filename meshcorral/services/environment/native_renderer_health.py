"""
Native CPU thumbnail renderer dependency health (Prime v1.0 RC).

Runs once per process (cached) so missing NumPy/Pillow/trimesh is detected at startup
instead of producing one failed job per STL/OBJ.
"""

from __future__ import annotations

import importlib.util
import time
from dataclasses import dataclass
from typing import Final

from meshcorral.app.bridge.blender_locator import describe_blender_readiness, find_blender_executable
from meshcorral.services.settings_service import SettingsService

_DEPENDENCY_LABELS: Final[dict[str, str]] = {
    "numpy": "NumPy",
    "trimesh": "trimesh",
    "pillow": "Pillow",
    "scipy": "SciPy",
}

_CACHED_HEALTH: NativeRendererHealth | None = None


@dataclass(frozen=True, slots=True)
class NativeRendererHealth:
    """Result of a native renderer dependency probe."""

    available: bool
    missing_dependencies: tuple[str, ...]
    detail: str
    checked_at: float
    can_render_stl_obj: bool
    fallback_backend: str

    @property
    def settings_message(self) -> str:
        """Short copy for the Settings dialog."""
        if self.available:
            return "Native renderer ready"
        if not self.missing_dependencies:
            return "Native renderer unavailable"
        labels = [_DEPENDENCY_LABELS.get(d, d) for d in self.missing_dependencies]
        if len(labels) == 1:
            return f"Native renderer unavailable: missing {labels[0]}"
        joined = ", ".join(labels[:-1]) + f", and {labels[-1]}"
        return f"Native renderer unavailable: missing {joined}"

    @property
    def jobs_message(self) -> str:
        """Copy for Jobs history / failure details."""
        if self.available:
            return ""
        if not self.missing_dependencies:
            return "Native renderer unavailable."
        labels = [_DEPENDENCY_LABELS.get(d, d) for d in self.missing_dependencies]
        if len(labels) == 1:
            return f"Native renderer unavailable. Missing dependency: {labels[0]}."
        joined = ", ".join(labels)
        return f"Native renderer unavailable. Missing dependencies: {joined}."

    @property
    def diagnostics_fallback_reason(self) -> str:
        """Inspector diagnostics fallback line."""
        if self.available:
            return ""
        if not self.missing_dependencies:
            return "Native renderer unavailable"
        labels = [_DEPENDENCY_LABELS.get(d, d) for d in self.missing_dependencies]
        if len(labels) == 1:
            return f"Native renderer unavailable: missing {labels[0]}"
        return f"Native renderer unavailable: missing {', '.join(labels)}"

    @property
    def footer_blender_fallback_message(self) -> str:
        """One-shot status bar when routing STL/OBJ through Blender or slower fallback."""
        return "Native thumbnails unavailable · Using slower fallback path"

    @property
    def manual_native_warning(self) -> str:
        """Warning when the user requests native render while unavailable."""
        base = self.settings_message
        return f"{base}. Install dependencies or use Blender fallback."


@dataclass(frozen=True, slots=True)
class StartupEnvironmentSummary:
    """Lightweight startup health lines for Settings / diagnostics."""

    native_renderer: str
    blender: str
    metadata_cache: str
    thumbnail_cache: str


def _probe_import(module_name: str, *, package_key: str) -> str | None:
    """
    Return *package_key* when *module_name* cannot be imported.

    Uses importlib only (no repeated per-job imports during rendering).
    """
    if importlib.util.find_spec(module_name) is None:
        return package_key
    return None


def check_native_renderer_health(*, force: bool = False) -> NativeRendererHealth:
    """
    Probe native renderer dependencies once and cache the result.

    Checks NumPy, trimesh, SciPy, Pillow, and that the native backend module loads.

    SciPy is required because trimesh may use sparse-matrix paths at runtime even when
    the trimesh package itself imports successfully.
    """
    global _CACHED_HEALTH
    if _CACHED_HEALTH is not None and not force:
        return _CACHED_HEALTH

    missing: list[str] = []
    for mod, key in (
        ("numpy", "numpy"),
        ("trimesh", "trimesh"),
        ("scipy", "scipy"),
        ("PIL", "pillow"),
    ):
        miss = _probe_import(mod, package_key=key)
        if miss is not None:
            missing.append(miss)

    backend_ok = importlib.util.find_spec(
        "meshcorral.services.thumbnails.native_thumbnail_backend"
    ) is not None
    if not backend_ok:
        missing.append("native_backend")

    available = len(missing) == 0
    if available:
        detail = "Native CPU renderer ready for STL/OBJ."
        fallback = "native"
    else:
        labels = [_DEPENDENCY_LABELS.get(d, d) for d in missing]
        detail = f"Native CPU renderer unavailable ({', '.join(labels)})."
        fallback = "blender"

    health = NativeRendererHealth(
        available=available,
        missing_dependencies=tuple(missing),
        detail=detail,
        checked_at=time.monotonic(),
        can_render_stl_obj=available,
        fallback_backend=fallback,
    )
    _CACHED_HEALTH = health
    return health


def get_native_renderer_health() -> NativeRendererHealth:
    """Return cached native health, probing on first access."""
    return check_native_renderer_health()


def reset_native_renderer_health_cache() -> None:
    """Clear cached health (tests only)."""
    global _CACHED_HEALTH
    _CACHED_HEALTH = None


def check_startup_environment(settings: SettingsService) -> StartupEnvironmentSummary:
    """Summarize native, Blender, and cache readiness for Settings."""
    native = get_native_renderer_health()
    native_line = "Ready" if native.available else "Unavailable"
    blender_exe = find_blender_executable(settings)
    blender_line = describe_blender_readiness(settings, blender_exe)
    return StartupEnvironmentSummary(
        native_renderer=native_line,
        blender=blender_line,
        metadata_cache="Ready",
        thumbnail_cache="Ready",
    )
