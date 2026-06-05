"""Thumbnail backend interfaces and shared models for Roundup."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from meshcorral.services.metadata.asset_metadata_summary import AssetMetadataSummary


class ThumbnailBackendId(str, Enum):
    """Stable backend identifiers for routing and result metadata."""

    NATIVE = "native"
    BLENDER = "blender"


@dataclass(frozen=True, slots=True)
class ThumbnailResult:
    """Result of a thumbnail attempt (backend-agnostic)."""

    backend_id: ThumbnailBackendId
    source_file: Path
    output_dir: Path | None
    thumbnail_path: Path | None
    ok: bool
    error_message: str | None = None
    log_path: Path | None = None
    geometry_summary: "AssetMetadataSummary | None" = None


class ThumbnailBackend:
    """Backend that can generate a thumbnail for some file types."""

    backend_id: ThumbnailBackendId

    def supports(self, path: Path) -> bool:
        """Return True if this backend can attempt thumbnails for *path*."""
        raise NotImplementedError

    def generate(self, path: Path, output_dir: Path, *, max_px: int = 512) -> ThumbnailResult:
        """
        Generate a thumbnail for *path* into *output_dir*.

        Implementations must be best-effort and never raise for expected file errors; failures
        should be reported via a non-ok :class:`ThumbnailResult`.
        """
        raise NotImplementedError
