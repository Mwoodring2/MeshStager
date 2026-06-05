"""Asset family detection (extension-only).

Roundup v0.1 treats "compatibility" as safe discovery, filtering, organizing, moving/copying,
exporting, and clear classification. We intentionally do not parse proprietary formats.
"""

from __future__ import annotations

from pathlib import Path

from meshcorral.app.config import (
    DCC_SCENE_EXTENSIONS,
    GEOMETRY_EXTENSIONS,
    SUPPORT_EXTENSIONS,
    SUPPORTED_IMAGE_EXTENSIONS,
)
from meshcorral.app.dcc.dcc_profiles import (
    DCC_EXTENSION_KIND_LABEL,
    dcc_id_for_extension,
    dcc_profile_for_id,
)

ASSET_FAMILY_GEOMETRY = "Geometry"
ASSET_FAMILY_DCC_SCENE = "DCC Scene"
ASSET_FAMILY_SUPPORT = "Support"
ASSET_FAMILY_IMAGE = "Image"
ASSET_FAMILY_UNKNOWN = "Unknown"


def _normalize_ext(path_or_ext: str) -> str:
    raw = (path_or_ext or "").strip()
    if not raw:
        return ""
    if raw.startswith(".") and len(raw) > 1:
        return raw.lower()
    # Accept either filename or extension without dot.
    suffix = Path(raw).suffix
    if suffix:
        return suffix.lower()
    return f".{raw.lower()}"


def detect_asset_family(path_or_ext: str) -> str:
    """Detect family from a filename or extension.

    Returns one of:
    - ``Geometry``
    - ``DCC Scene``
    - ``Support``
    - ``Image``
    - ``Unknown``
    """

    ext = _normalize_ext(path_or_ext)
    if not ext:
        return ASSET_FAMILY_UNKNOWN
    if ext in SUPPORTED_IMAGE_EXTENSIONS:
        return ASSET_FAMILY_IMAGE
    if ext in GEOMETRY_EXTENSIONS:
        return ASSET_FAMILY_GEOMETRY
    if ext in DCC_SCENE_EXTENSIONS:
        return ASSET_FAMILY_DCC_SCENE
    if ext in SUPPORT_EXTENSIONS:
        return ASSET_FAMILY_SUPPORT
    return ASSET_FAMILY_UNKNOWN


def preview_kind_label_for_family(family: str) -> str:
    """Short inspector label for a family (panel subtitle line)."""

    f = (family or "").strip()
    if f == ASSET_FAMILY_IMAGE:
        return "IMAGE"
    if f == ASSET_FAMILY_GEOMETRY:
        return "3D ASSET"
    if f == ASSET_FAMILY_DCC_SCENE:
        return "DCC SCENE"
    if f == ASSET_FAMILY_SUPPORT:
        return "SUPPORT FILE"
    return "FILE"


def preview_kind_label_for_path(path_or_ext: str) -> str:
    """
    Inspector subtitle label for a filename or extension.

    For DCC scene family, tries to use a more specific label, e.g.:
    ``BLENDER SCENE`` / ``MAYA SCENE`` / ``ZBRUSH TOOL``.
    """
    ext = _normalize_ext(path_or_ext)
    family = detect_asset_family(ext)
    base = preview_kind_label_for_family(family)
    if family != ASSET_FAMILY_DCC_SCENE:
        return base
    dcc_id = dcc_id_for_extension(ext)
    if dcc_id is None:
        return base
    profile = dcc_profile_for_id(dcc_id)
    if profile is None:
        return base
    kind = DCC_EXTENSION_KIND_LABEL.get(ext, "SCENE")
    return f"{profile.display_name.upper()} {kind}"

