"""In-memory READY state for bridge and raster thumbnails (paint path never validates disk)."""

from __future__ import annotations

import threading
from pathlib import Path

from meshcorral.app.bridge.job_models import BridgeJobResult, BridgeJobStatus
from meshcorral.app.bridge.thumb_index import _norm_path_key


def validate_raster_source_ready(source_path: str | Path) -> bool:
    """
    Return True when a raster source file exists and can be decoded off the UI thread.

    Performs at most one ``Path.is_file()`` check — call only off the paint path.
    """
    if not source_path or not str(source_path).strip():
        return False
    try:
        return Path(source_path).is_file()
    except OSError:
        return False


def validate_bridge_thumbnail_ready(
    *,
    status: str,
    thumbnail_path: str | None,
) -> bool:
    """
    Return True when a bridge job produced a usable on-disk thumbnail.

    Performs at most one ``Path.is_file()`` check — call only off the UI paint path.
    """
    if str(status).lower() != BridgeJobStatus.COMPLETE.value:
        return False
    if not thumbnail_path or not str(thumbnail_path).strip():
        return False
    try:
        return Path(thumbnail_path).is_file()
    except OSError:
        return False


class ThumbnailReadyCache:
    """
    Tracks assets whose thumbnail source is known-good without re-statting on paint.

    Bridge geometry maps source → ``thumbnail.png`` path. Raster images map source →
    the same source path (self-thumb) after a single off-paint existence check.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._ready_keys: set[str] = set()
        self._thumb_paths: dict[str, str] = {}

    def clear(self) -> None:
        """Drop all READY entries (e.g. full index rebuild)."""
        with self._lock:
            self._ready_keys.clear()
            self._thumb_paths.clear()

    def mark_ready(self, asset_path: Path, thumbnail_path: Path) -> bool:
        """
        Mark *asset_path* READY when *thumbnail_path* exists on disk.

        Returns True when the entry was stored.
        """
        if not validate_bridge_thumbnail_ready(
            status=BridgeJobStatus.COMPLETE.value,
            thumbnail_path=str(thumbnail_path),
        ):
            return False
        return self._store_ready(asset_path, thumbnail_path)

    def mark_ready_raster(self, asset_path: Path) -> bool:
        """
        Mark a raster source READY after validating the file exists (once, off paint).

        The decode path is the asset itself; no ``QPixmap``/``QImage`` is created here.
        """
        if not validate_raster_source_ready(asset_path):
            return False
        return self._store_ready(asset_path, asset_path)

    def _store_ready(self, asset_path: Path, thumbnail_path: Path) -> bool:
        key = _norm_path_key(asset_path)
        with self._lock:
            self._ready_keys.add(key)
            self._thumb_paths[key] = str(thumbnail_path)
        return True

    def mark_from_job_result(self, result: BridgeJobResult) -> bool:
        """Mark READY from a finished bridge job (validates once)."""
        if not result.source_file:
            return False
        src = Path(result.source_file)
        if not result.thumbnail_path:
            self.mark_not_ready(src)
            return False
        ok = self.mark_ready(src, Path(result.thumbnail_path))
        if not ok:
            self.mark_not_ready(src)
        return ok

    def mark_not_ready(self, asset_path: Path) -> None:
        """Remove READY state for *asset_path*."""
        key = _norm_path_key(asset_path)
        with self._lock:
            self._ready_keys.discard(key)
            self._thumb_paths.pop(key, None)

    def is_ready(self, asset_path: Path) -> bool:
        """Return True if *asset_path* was marked READY (no disk access)."""
        key = _norm_path_key(asset_path)
        with self._lock:
            return key in self._ready_keys

    def get_thumbnail_path(self, asset_path: Path) -> str | None:
        """
        Return the cached absolute thumbnail path for a READY asset.

        Does not touch the filesystem.
        """
        key = _norm_path_key(asset_path)
        with self._lock:
            if key not in self._ready_keys:
                return None
            return self._thumb_paths.get(key)

    def ready_count(self) -> int:
        with self._lock:
            return len(self._ready_keys)
