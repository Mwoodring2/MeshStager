"""
Known non-renderable thumbnail policy for FBX assets.

Some FBX files import cleanly into Blender but can never produce a thumbnail: rigs with
only an armature, camera/light-only scenes, empty scenes, and ASCII FBX (unsupported by
the bundled importer). Re-queueing those files on every browse pass costs about a second
each with no possible gain.

This module holds the *pure* half of the fix: classifying a finished bridge job into a
high-confidence "non renderable" verdict, plus the staleness rule that lets Blender try
again once the file itself changes. Persistence lives in
:class:`~meshcorral.services.metadata_cache.MetadataCache`; UI wiring lives in
:mod:`meshcorral.ui.main_window`.

Only high-confidence cases are recorded. Transient problems (Blender crash, timeout,
permission/IO errors, missing outputs, unknown importer exceptions) must stay retryable.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from meshcorral.app.bridge.job_models import BridgeJobResult, BridgeJobStatus

logger = logging.getLogger(__name__)

# Only FBX is tracked today: STL/OBJ/native routing behavior must not change.
TRACKED_EXTENSIONS: frozenset[str] = frozenset({".fbx"})

# Object types that can legitimately exist in a mesh-free scene we will never render.
_NON_RENDERABLE_OBJECT_TYPES: frozenset[str] = frozenset(
    {"ARMATURE", "CAMERA", "LIGHT", "EMPTY"}
)

# ``blender_worker/scripts/thumbnail_render.py`` writes this on a zero-mesh import.
_ZERO_MESH_RE = re.compile(
    r"imported\s+(?P<total>\d+)\s+objects?,\s*0\s+meshes\.\s*types:\s*\[(?P<types>[^\]]*)\]",
    re.IGNORECASE,
)
_EMPTY_SCENE_BREAKDOWN: str = "none"

_FBX_IMPORT_FAILURE_MARKER: str = "fbx import failed"
_ASCII_ERROR_MARKERS: tuple[str, ...] = ("ascii fbx", "ascii .fbx", "is in ascii format")

# Any of these in the error text means "retry later", never "give up permanently".
_TRANSIENT_MARKERS: tuple[str, ...] = (
    "blender exited with code",
    "did not write result.json",
    "invalid result.json",
    "failed to start blender",
    "blender executable not found",
    "worker script is missing",
    "traceback (most recent call last)",
    "timed out",
    "timeout",
    "permission denied",
    "access is denied",
    "permissionerror",
    "oserror",
    "network",
    "source file not found",
    "could not clear scene",
    "render failed",
    "camera setup failed",
    "was not found in the output directory",
)

_NATIVE_JOB_TYPE: str = "native_thumbnail"

_BINARY_FBX_MAGIC: bytes = b"Kaydara FBX Binary"
_ASCII_SNIFF_BYTES: int = 2048

# Filesystem mtimes round-trip through SQLite as doubles; tolerate float noise only.
_MTIME_EPSILON: float = 1e-6


class NonRenderableReason(str, Enum):
    """Why a file is known to be non-renderable (stored verbatim in SQLite)."""

    NO_MESH_OBJECTS = "fbx_no_mesh_objects"
    ASCII_UNSUPPORTED = "fbx_ascii_unsupported"


@dataclass(frozen=True, slots=True)
class NonRenderableVerdict:
    """A high-confidence classification of a failed thumbnail job."""

    reason: NonRenderableReason
    detail: str


@dataclass(frozen=True, slots=True)
class FileFingerprint:
    """Identity used to invalidate a negative result (size plus mtime)."""

    size_bytes: int
    modified_time: float


@dataclass(frozen=True, slots=True)
class NonRenderableThumbEntry:
    """One persisted negative thumbnail result (``thumb_negative_cache`` row)."""

    path: str
    path_key: str
    ext: str
    reason: str
    detail: str | None
    size_bytes: int
    modified_time: float
    recorded_at: float

    def matches_fingerprint(
        self,
        *,
        size_bytes: int | None,
        modified_time: float | None,
    ) -> bool:
        """
        True when *size_bytes* and *modified_time* still match the recorded identity.

        Unknown stat values never match, so a file with no known size/mtime is retried
        rather than silently suppressed.
        """
        if size_bytes is None or modified_time is None:
            return False
        if int(size_bytes) != int(self.size_bytes):
            return False
        return abs(float(modified_time) - float(self.modified_time)) <= _MTIME_EPSILON

    def reason_enum(self) -> NonRenderableReason | None:
        """Parse :attr:`reason` back into :class:`NonRenderableReason` when recognized."""
        try:
            return NonRenderableReason(self.reason)
        except ValueError:
            return None


def is_tracked_non_renderable_extension(path: Path) -> bool:
    """True when *path* is a format covered by the negative thumbnail cache."""
    return Path(path).suffix.lower() in TRACKED_EXTENSIONS


def fingerprint_for_path(path: Path) -> FileFingerprint | None:
    """Stat *path* for size and mtime; ``None`` when the file cannot be stat'd."""
    try:
        stat_result = Path(path).stat()
    except OSError as exc:
        logger.debug("Non-renderable fingerprint unavailable for %s: %s", path, exc)
        return None
    return FileFingerprint(
        size_bytes=int(stat_result.st_size),
        modified_time=float(stat_result.st_mtime),
    )


def fbx_is_ascii(path: Path) -> bool | None:
    """
    Sniff whether *path* is an ASCII FBX file.

    Returns ``True`` for confirmed ASCII FBX, ``False`` for binary FBX or anything that
    does not look like ASCII FBX, and ``None`` when the header cannot be read (unknown,
    so callers must not record a negative result).
    """
    try:
        with Path(path).open("rb") as handle:
            head = handle.read(_ASCII_SNIFF_BYTES)
    except OSError as exc:
        logger.debug("ASCII FBX probe failed for %s: %s", path, exc)
        return None
    if not head:
        return None
    if head.startswith(_BINARY_FBX_MAGIC):
        return False
    try:
        text = head.decode("ascii")
    except UnicodeDecodeError:
        return False
    return "FBX" in text.upper()


def has_transient_failure_marker(error_message: str) -> bool:
    """True when the error text names a retryable condition (crash, timeout, IO, …)."""
    lowered = (error_message or "").lower()
    return any(marker in lowered for marker in _TRANSIENT_MARKERS)


def classify_non_renderable_result(result: BridgeJobResult) -> NonRenderableVerdict | None:
    """
    Classify a finished bridge job as permanently non-renderable, or ``None``.

    A verdict is only returned for FBX sources whose Blender thumbnail job failed with
    either a zero-mesh import made up solely of armature/camera/light/empty objects, or
    an ASCII FBX the importer cannot read. Everything else — including unknown importer
    exceptions — returns ``None`` so the file stays retryable.
    """
    if result.status != BridgeJobStatus.FAILED:
        return None
    if (result.job_type or "").strip().lower() == _NATIVE_JOB_TYPE:
        return None
    source = (result.source_file or "").strip()
    if not source:
        return None
    path = Path(source)
    if not is_tracked_non_renderable_extension(path):
        return None
    message = (result.error_message or "").strip()
    if not message or has_transient_failure_marker(message):
        return None

    zero_mesh = _ZERO_MESH_RE.search(message)
    if zero_mesh is not None:
        types_text = zero_mesh.group("types").strip()
        if not _breakdown_is_non_renderable(types_text):
            return None
        return NonRenderableVerdict(
            reason=NonRenderableReason.NO_MESH_OBJECTS,
            detail=f"objects={zero_mesh.group('total')} types=[{types_text}]",
        )

    if _is_ascii_fbx_failure(message, path):
        return NonRenderableVerdict(
            reason=NonRenderableReason.ASCII_UNSUPPORTED,
            detail="ASCII FBX is not supported by the Blender importer",
        )
    return None


def non_renderable_blocks_auto_enqueue(
    entry: NonRenderableThumbEntry | None,
    *,
    size_bytes: int | None,
    modified_time: float | None,
) -> bool:
    """
    True when an automatic thumbnail request must skip Blender for this file.

    Manual requests never consult this helper, and a changed size or mtime makes the
    recorded entry stale so Blender is allowed to try again.
    """
    if entry is None:
        return False
    return entry.matches_fingerprint(size_bytes=size_bytes, modified_time=modified_time)


def _breakdown_is_non_renderable(types_text: str) -> bool:
    """True when a ``TYPE:count`` breakdown holds only known non-renderable types."""
    text = types_text.strip()
    if not text or text.lower() == _EMPTY_SCENE_BREAKDOWN:
        return True
    for chunk in text.split(","):
        name = chunk.split(":", 1)[0].strip().upper()
        if not name or name not in _NON_RENDERABLE_OBJECT_TYPES:
            return False
    return True


def _is_ascii_fbx_failure(message: str, path: Path) -> bool:
    """True when an FBX import failure is explained by the file being ASCII FBX."""
    lowered = message.lower()
    if _FBX_IMPORT_FAILURE_MARKER not in lowered:
        return False
    if any(marker in lowered for marker in _ASCII_ERROR_MARKERS):
        return True
    return fbx_is_ascii(path) is True


__all__ = [
    "FileFingerprint",
    "NonRenderableReason",
    "NonRenderableThumbEntry",
    "NonRenderableVerdict",
    "TRACKED_EXTENSIONS",
    "classify_non_renderable_result",
    "fbx_is_ascii",
    "fingerprint_for_path",
    "has_transient_failure_marker",
    "is_tracked_non_renderable_extension",
    "non_renderable_blocks_auto_enqueue",
]
