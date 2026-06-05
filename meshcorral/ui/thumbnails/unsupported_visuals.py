"""Prime v1.0 — intentional per-format placeholder identity."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.ui.preview_state_copy import PREVIEW_DEFERRED_CARD_SHORT

_LARGE_FILE_BYTES: int = 512 * 1024 * 1024


class UnsupportedVisualKind(str, Enum):
    """Semantic placeholder families (unsupported still looks designed)."""

    ZTL = "ztl"
    MA = "ma"
    MB = "mb"
    PSD = "psd"
    EXR = "exr"
    ZIP = "zip"
    ARCHIVE = "archive"
    DCC = "dcc"
    MESH = "mesh"
    IMAGE = "image"
    UNKNOWN = "unknown"
    CORRUPT = "corrupt"
    LARGE_FILE = "large_file"
    DEFERRED = "deferred"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class UnsupportedVisualIdentity:
    """Colors and short title for a format card."""

    kind: UnsupportedVisualKind
    title: str
    base_rgb: tuple[int, int, int]
    badge: str


def _ext_key(extension: str) -> str:
    e = (extension or "").strip().lower()
    if e.startswith("."):
        return e
    if e:
        return f".{e}"
    return ""


def classify_extension(extension: str) -> UnsupportedVisualKind:
    """Map a file extension to a visual family."""
    e = _ext_key(extension)
    if e in (".ztl",):
        return UnsupportedVisualKind.ZTL
    if e in (".ma",):
        return UnsupportedVisualKind.MA
    if e in (".mb",):
        return UnsupportedVisualKind.MB
    if e in (".psd", ".psb"):
        return UnsupportedVisualKind.PSD
    if e in (".exr", ".hdr"):
        return UnsupportedVisualKind.EXR
    if e in (".zip", ".7z", ".rar"):
        return UnsupportedVisualKind.ZIP
    if e in (".blend",):
        return UnsupportedVisualKind.DCC
    if e in (".fbx", ".obj", ".stl", ".ply", ".glb", ".gltf"):
        return UnsupportedVisualKind.MESH
    if e in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp", ".gif"):
        return UnsupportedVisualKind.IMAGE
    return UnsupportedVisualKind.UNKNOWN


_IDENTITY: dict[UnsupportedVisualKind, UnsupportedVisualIdentity] = {
    UnsupportedVisualKind.ZTL: UnsupportedVisualIdentity(
        UnsupportedVisualKind.ZTL, "ZTL", (122, 66, 66), "SCULPT"
    ),
    UnsupportedVisualKind.MA: UnsupportedVisualIdentity(
        UnsupportedVisualKind.MA, "MA", (54, 112, 142), "DCC"
    ),
    UnsupportedVisualKind.MB: UnsupportedVisualIdentity(
        UnsupportedVisualKind.MB, "MB", (54, 112, 142), "DCC"
    ),
    UnsupportedVisualKind.PSD: UnsupportedVisualIdentity(
        UnsupportedVisualKind.PSD, "PSD", (98, 78, 128), "LAYER"
    ),
    UnsupportedVisualKind.EXR: UnsupportedVisualIdentity(
        UnsupportedVisualKind.EXR, "EXR", (68, 98, 118), "HDR"
    ),
    UnsupportedVisualKind.ZIP: UnsupportedVisualIdentity(
        UnsupportedVisualKind.ZIP, "ZIP", (88, 98, 72), "ARCHIVE"
    ),
    UnsupportedVisualKind.ARCHIVE: UnsupportedVisualIdentity(
        UnsupportedVisualKind.ARCHIVE, "ARCH", (88, 98, 72), "ARCHIVE"
    ),
    UnsupportedVisualKind.DCC: UnsupportedVisualIdentity(
        UnsupportedVisualKind.DCC, "BLEND", (86, 68, 140), "DCC"
    ),
    UnsupportedVisualKind.MESH: UnsupportedVisualIdentity(
        UnsupportedVisualKind.MESH, "MESH", (72, 108, 96), "3D"
    ),
    UnsupportedVisualKind.IMAGE: UnsupportedVisualIdentity(
        UnsupportedVisualKind.IMAGE, "IMG", (92, 108, 82), "2D"
    ),
    UnsupportedVisualKind.UNKNOWN: UnsupportedVisualIdentity(
        UnsupportedVisualKind.UNKNOWN, "NO PREVIEW", (90, 90, 96), "—"
    ),
    UnsupportedVisualKind.CORRUPT: UnsupportedVisualIdentity(
        UnsupportedVisualKind.CORRUPT, "Corrupt", (142, 68, 68), "!"
    ),
    UnsupportedVisualKind.LARGE_FILE: UnsupportedVisualIdentity(
        UnsupportedVisualKind.LARGE_FILE, "LARGE", (108, 92, 62), "BIG"
    ),
    UnsupportedVisualKind.DEFERRED: UnsupportedVisualIdentity(
        UnsupportedVisualKind.DEFERRED, PREVIEW_DEFERRED_CARD_SHORT, (88, 94, 108), "···"
    ),
    UnsupportedVisualKind.FAILED: UnsupportedVisualIdentity(
        UnsupportedVisualKind.FAILED, "Failed", (128, 82, 76), "FAILED"
    ),
    UnsupportedVisualKind.TIMEOUT: UnsupportedVisualIdentity(
        UnsupportedVisualKind.TIMEOUT, "Timed out", (118, 98, 68), "RETRY"
    ),
}


def identity_rgb_sum(identity: UnsupportedVisualIdentity) -> int:
    """Sum of RGB channels (tests: calmer deferred vs stronger corrupt/failed)."""
    r, g, b = identity.base_rgb
    return int(r) + int(g) + int(b)


def resolve_unsupported_visual(
    extension: str,
    *,
    health: ThumbHealth | None = None,
    visual: ThumbVisualState | None = None,
    size_bytes: int = 0,
    deferred: bool = False,
    bridge_error_message: str | None = None,
) -> UnsupportedVisualIdentity:
    """
    Pick visual identity for a non-ready thumbnail card.

    *deferred* is used for Prime visible-first placeholders (not broken, waiting).
    """
    if deferred:
        return _IDENTITY[UnsupportedVisualKind.DEFERRED]
    if visual == ThumbVisualState.FAILED and health == ThumbHealth.FAILED_THUMBNAIL:
        from meshcorral.ui.thumbnails.thumbnail_ux_copy import classify_bridge_error_kind

        if classify_bridge_error_kind(bridge_error_message) == "timeout":
            return _IDENTITY[UnsupportedVisualKind.TIMEOUT]
        return _IDENTITY[UnsupportedVisualKind.FAILED]
    if visual == ThumbVisualState.FAILED:
        return _IDENTITY[UnsupportedVisualKind.CORRUPT]
    if health == ThumbHealth.FAILED_THUMBNAIL:
        return _IDENTITY[UnsupportedVisualKind.FAILED]
    if size_bytes >= _LARGE_FILE_BYTES:
        return _IDENTITY[UnsupportedVisualKind.LARGE_FILE]
    if health == ThumbHealth.UNSUPPORTED:
        kind = classify_extension(extension)
        return _IDENTITY.get(kind, _IDENTITY[UnsupportedVisualKind.UNKNOWN])
    kind = classify_extension(extension)
    return _IDENTITY.get(kind, _IDENTITY[UnsupportedVisualKind.UNKNOWN])


def format_card_title(extension: str, *, identity: UnsupportedVisualIdentity | None = None) -> str:
    """Short uppercase title for the card face (extension-first, not generic FILE)."""
    e = _ext_key(extension)
    ext_label = e[1:].upper()[:8] if e.startswith(".") else (e.upper()[:8] if e else "")
    if identity is not None:
        if identity.kind == UnsupportedVisualKind.UNKNOWN and ext_label:
            return ext_label
        if identity.kind == UnsupportedVisualKind.DEFERRED:
            return identity.title
        return identity.title
    if not ext_label:
        return "—"
    return ext_label
