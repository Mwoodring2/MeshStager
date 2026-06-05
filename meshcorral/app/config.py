from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "MeshStager"
LEGACY_APP_NAME = "Roundup"
APP_VERSION = "0.1.0-rc1"

# Developer diagnostics (transfer / plan preview). Keep False for releases.
DEBUG_MODE = False
APP_ORG_NAME = "MeshCorral"
APP_ORG_DOMAIN = "meshcorral.local"

# --- Asset type scan modes (mutually exclusive when scanning) ---
ASSET_MODE_3D = "3d"
ASSET_MODE_IMAGES = "images"

# --- Auto-detected asset families (extension-only, no metadata parsing) ---
GEOMETRY_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".stl",
        ".obj",
        ".fbx",
        ".ply",
        ".glb",
        ".gltf",
        ".3mf",
        ".dae",
        ".abc",
    }
)

# DCC project / scene files (discovery + filtering only; no opening/parsing here).
DCC_SCENE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".blend",
        ".ma",
        ".mb",
        ".ztl",
        ".zpr",
        ".c4d",
        ".max",
        ".hip",
        ".hiplc",
        ".spp",
        ".sbs",
        ".sbsar",
    }
)

# Materials / support sidecars and DCC-adjacent project data.
SUPPORT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".mtl",
        ".mat",
        ".json",
        ".xml",
        ".xmp",
        ".usd",
        ".usda",
        ".usdc",
        ".usdz",
    }
)

# Image/texture scan set; also used for raster preview attempts.
SUPPORTED_IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".png",
        ".jpg",
        ".jpeg",
        ".tif",
        ".tiff",
        ".tga",
        ".bmp",
        ".webp",
        ".psd",
        ".exr",
        ".hdr",
    }
)

# Strict 3D/DCC scan set for 3D mode (geometry + scenes + support).
SUPPORTED_3D_EXTENSIONS: frozenset[str] = frozenset(
    set(GEOMETRY_EXTENSIONS) | set(DCC_SCENE_EXTENSIONS) | set(SUPPORT_EXTENSIONS)
)

# Aliases for preview panel (same membership as scan sets).
IMAGE_PREVIEW_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS
THREE_D_PREVIEW_EXTENSIONS = SUPPORTED_3D_EXTENSIONS

# Blender bridge + inspector: mesh formats that can produce a generated thumbnail today.
MESH_THUMBNAIL_EXTENSIONS: frozenset[str] = frozenset({".stl", ".obj", ".fbx"})

OPTIONAL_TEXTURE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".tga", ".exr", ".hdr",
}

CUSTOM_EXTENSIONS = {
    ".ets",
}

# v1 default scan set (full “legacy” union; used when scanner gets no allowed set / tests).
ALL_SUPPORTED_EXTENSIONS = (
    set(GEOMETRY_EXTENSIONS)
    | set(DCC_SCENE_EXTENSIONS)
    | set(SUPPORT_EXTENSIONS)
    | CUSTOM_EXTENSIONS
)

FILE_TYPE_CATEGORIES = {
    "All": ALL_SUPPORTED_EXTENSIONS,
    "Geometry": set(GEOMETRY_EXTENSIONS),
    "DCC Scene": set(DCC_SCENE_EXTENSIONS),
    "Support": set(SUPPORT_EXTENSIONS),
    "Custom": CUSTOM_EXTENSIONS,
}


def supported_extensions_for_asset_mode(mode: str) -> set[str]:
    """Return the extension set scanned for the given asset mode."""
    if mode == ASSET_MODE_IMAGES:
        return set(SUPPORTED_IMAGE_EXTENSIONS)
    if mode == ASSET_MODE_3D:
        return set(SUPPORTED_3D_EXTENSIONS)
    return set(SUPPORTED_3D_EXTENSIONS)


def file_type_category_map_for_asset_mode(mode: str) -> dict[str, set[str]]:
    """
    Type-filter categories for the current asset mode.

    3D mode uses category slices intersected with :data:`SUPPORTED_3D_EXTENSIONS`.
    Images mode exposes ``All`` and ``Image`` (same underlying set for clarity).
    """
    if mode == ASSET_MODE_IMAGES:
        s = set(SUPPORTED_IMAGE_EXTENSIONS)
        return {"All": s, "Image": s}

    return {
        "All": set(SUPPORTED_3D_EXTENSIONS),
        "Geometry": set(GEOMETRY_EXTENSIONS),
        "DCC Scene": set(DCC_SCENE_EXTENSIONS),
        "Support": set(SUPPORT_EXTENSIONS),
    }


def ordered_category_labels_for_asset_mode(mode: str) -> list[str]:
    """Stable ordering of Type combo labels for ``mode``."""
    m = file_type_category_map_for_asset_mode(mode)
    if mode == ASSET_MODE_IMAGES:
        return [k for k in ["All", "Image"] if k in m]
    order = ["All", "Geometry", "DCC Scene", "Support"]
    return [k for k in order if k in m]


def extensions_for_asset_category(mode: str, category_name: str) -> list[str]:
    """Sorted extension list for a Type row in the given asset mode."""
    m = file_type_category_map_for_asset_mode(mode)
    exts = m.get(category_name) or m["All"]
    return sorted(exts)


def extensions_for_category(category_name: str) -> list[str]:
    """
    Return a sorted list of extensions for the given category (legacy, full scan set).

    Unknown categories safely fall back to all supported extensions.
    """
    allowed = FILE_TYPE_CATEGORIES.get(category_name, FILE_TYPE_CATEGORIES["All"])
    return sorted(allowed)


def read_branded_env(suffix: str, default: str = "") -> str:
    """
    Read ``MESHSTAGER_{suffix}`` with legacy ``ROUNDUP_{suffix}`` fallback.

    Keeps existing QA scripts working while preferring the new product prefix.
    """
    for prefix in ("MESHSTAGER", "ROUNDUP"):
        raw = os.environ.get(f"{prefix}_{suffix}", "").strip()
        if raw:
            return raw
    return default


def read_branded_env_flag(suffix: str, *, default: bool = False) -> bool:
    """Truthy env flag using :func:`read_branded_env`."""
    raw = read_branded_env(suffix, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on"}


def _init_user_data_dir() -> Path:
    from meshcorral.app.data_migration import run_startup_data_migration

    return run_startup_data_migration(
        org_name="WoodringTools",
        app_name=APP_NAME,
        legacy_app_name=LEGACY_APP_NAME,
    )


if os.name == "nt":
    USER_DATA_DIR = _init_user_data_dir()
else:
    USER_DATA_DIR = Path.home() / f".{APP_NAME.lower()}"
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

LOG_DIR = USER_DATA_DIR / "logs"
EXPORT_DIR = USER_DATA_DIR / "exports"

for _path in (LOG_DIR, EXPORT_DIR):
    _path.mkdir(parents=True, exist_ok=True)

DEFAULT_RECURSIVE_SCAN = True
