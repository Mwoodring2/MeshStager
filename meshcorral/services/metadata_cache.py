"""Persistent SQLite metadata cache (Prime Performance v0.8).

Caches stat metadata and thumbnail hints so repeat scans avoid redundant
filesystem probing and full ``result.json`` walks.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.app.config import USER_DATA_DIR

logger = logging.getLogger(__name__)

SCHEMA_VERSION: int = 1
DEFAULT_CACHE_DIR = USER_DATA_DIR / "cache"
DEFAULT_DB_PATH = DEFAULT_CACHE_DIR / "metadata_cache.sqlite"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS asset_metadata_cache (
    path TEXT PRIMARY KEY,
    path_key TEXT NOT NULL,
    ext TEXT NOT NULL DEFAULT '',
    size_bytes INTEGER,
    modified_time REAL,
    file_exists INTEGER NOT NULL DEFAULT 1,
    source_root TEXT NOT NULL DEFAULT '',
    last_seen REAL NOT NULL,
    last_enriched REAL,
    metadata_json TEXT,
    thumb_status TEXT,
    thumb_path TEXT,
    renderer_version TEXT
);
CREATE INDEX IF NOT EXISTS idx_asset_metadata_path_key
    ON asset_metadata_cache (path_key);
CREATE INDEX IF NOT EXISTS idx_asset_metadata_source_root
    ON asset_metadata_cache (source_root);
CREATE INDEX IF NOT EXISTS idx_asset_metadata_ext
    ON asset_metadata_cache (ext);
CREATE INDEX IF NOT EXISTS idx_asset_metadata_last_seen
    ON asset_metadata_cache (last_seen);
CREATE TABLE IF NOT EXISTS cache_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass(frozen=True, slots=True)
class CachedAssetMetadata:
    """One row from ``asset_metadata_cache``."""

    path: str
    path_key: str
    ext: str
    size_bytes: int | None
    modified_time: float | None
    file_exists: bool
    source_root: str
    last_seen: float
    last_enriched: float | None
    metadata_json: str | None
    thumb_status: str | None
    thumb_path: str | None
    renderer_version: str | None

    def is_usable_for_hydrate(self, *, network_optimistic: bool) -> bool:
        """
        Whether scan may copy cached stat fields onto a :class:`FileRecord`.

        Remote/lightweight mode may hydrate optimistically; local callers may
        still schedule enrichment to confirm stat when rows are visible.
        """
        if not self.file_exists:
            return False
        if self.size_bytes is None or self.modified_time is None:
            return False
        if network_optimistic:
            return True
        return True


@dataclass(frozen=True, slots=True)
class MetadataCacheStats:
    """Aggregate counters for diagnostics."""

    row_count: int
    last_prune_removed: int


def default_metadata_cache_path() -> Path:
    """Return the default on-disk path for the metadata cache database."""
    return DEFAULT_DB_PATH


class MetadataCache:
    """
    Thread-safe SQLite store for per-asset metadata and thumbnail hints.

    Uses ``check_same_thread=False`` so scan/enrichment worker threads may read.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path or DEFAULT_DB_PATH)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._migrate()
        self._last_prune_removed: int = 0

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def _migrate(self) -> None:
        with self._conn:
            self._conn.executescript(_CREATE_SQL)
            cur = self._conn.execute(
                "SELECT value FROM cache_meta WHERE key = 'schema_version'"
            )
            row = cur.fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO cache_meta (key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )

    @staticmethod
    def _row_to_cached(row: sqlite3.Row) -> CachedAssetMetadata:
        return CachedAssetMetadata(
            path=str(row["path"]),
            path_key=str(row["path_key"]),
            ext=str(row["ext"] or ""),
            size_bytes=row["size_bytes"],
            modified_time=row["modified_time"],
            file_exists=bool(row["file_exists"]),
            source_root=str(row["source_root"] or ""),
            last_seen=float(row["last_seen"]),
            last_enriched=row["last_enriched"],
            metadata_json=row["metadata_json"],
            thumb_status=row["thumb_status"],
            thumb_path=row["thumb_path"],
            renderer_version=row["renderer_version"],
        )

    def get(self, path: str | Path) -> CachedAssetMetadata | None:
        """Return cached metadata for *path*, or ``None`` if absent."""
        key = _norm_path_key(path)
        cur = self._conn.execute(
            "SELECT * FROM asset_metadata_cache WHERE path_key = ? LIMIT 1",
            (key,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_cached(row)

    def get_many(self, paths: list[str | Path]) -> dict[str, CachedAssetMetadata]:
        """Batch lookup keyed by normalized path key."""
        if not paths:
            return {}
        keys = [_norm_path_key(p) for p in paths]
        placeholders = ",".join("?" * len(keys))
        cur = self._conn.execute(
            f"SELECT * FROM asset_metadata_cache WHERE path_key IN ({placeholders})",
            keys,
        )
        out: dict[str, CachedAssetMetadata] = {}
        for row in cur.fetchall():
            cached = self._row_to_cached(row)
            out[cached.path_key] = cached
        return out

    def upsert(
        self,
        *,
        path: str | Path,
        ext: str = "",
        size_bytes: int | None = None,
        modified_time: float | None = None,
        file_exists: bool = True,
        source_root: str = "",
        metadata_json: str | None = None,
        thumb_status: str | None = None,
        thumb_path: str | None = None,
        renderer_version: str | None = None,
        enriched: bool = False,
    ) -> None:
        """Insert or replace one cache row."""
        now = time.time()
        p = Path(path)
        path_s = str(p)
        key = _norm_path_key(p)
        last_enriched = now if enriched else None
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO asset_metadata_cache (
                    path, path_key, ext, size_bytes, modified_time, file_exists,
                    source_root, last_seen, last_enriched, metadata_json,
                    thumb_status, thumb_path, renderer_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    path_key = excluded.path_key,
                    ext = excluded.ext,
                    size_bytes = excluded.size_bytes,
                    modified_time = excluded.modified_time,
                    file_exists = excluded.file_exists,
                    source_root = excluded.source_root,
                    last_seen = excluded.last_seen,
                    last_enriched = COALESCE(excluded.last_enriched, last_enriched),
                    metadata_json = excluded.metadata_json,
                    thumb_status = COALESCE(excluded.thumb_status, thumb_status),
                    thumb_path = COALESCE(excluded.thumb_path, thumb_path),
                    renderer_version = COALESCE(excluded.renderer_version, renderer_version)
                """,
                (
                    path_s,
                    key,
                    ext,
                    size_bytes,
                    modified_time,
                    1 if file_exists else 0,
                    source_root,
                    now,
                    last_enriched,
                    metadata_json,
                    thumb_status,
                    thumb_path,
                    renderer_version,
                ),
            )

    def upsert_many(self, records: list[CachedAssetMetadata]) -> None:
        """Batch upsert pre-built :class:`CachedAssetMetadata` rows."""
        if not records:
            return
        now = time.time()
        rows: list[tuple[Any, ...]] = []
        for rec in records:
            rows.append(
                (
                    rec.path,
                    rec.path_key,
                    rec.ext,
                    rec.size_bytes,
                    rec.modified_time,
                    1 if rec.file_exists else 0,
                    rec.source_root,
                    now,
                    rec.last_enriched or (now if rec.size_bytes is not None else None),
                    rec.metadata_json,
                    rec.thumb_status,
                    rec.thumb_path,
                    rec.renderer_version,
                )
            )
        with self._conn:
            self._conn.executemany(
                """
                INSERT INTO asset_metadata_cache (
                    path, path_key, ext, size_bytes, modified_time, file_exists,
                    source_root, last_seen, last_enriched, metadata_json,
                    thumb_status, thumb_path, renderer_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    path_key = excluded.path_key,
                    ext = excluded.ext,
                    size_bytes = excluded.size_bytes,
                    modified_time = excluded.modified_time,
                    file_exists = excluded.file_exists,
                    source_root = excluded.source_root,
                    last_seen = excluded.last_seen,
                    last_enriched = COALESCE(excluded.last_enriched, last_enriched),
                    metadata_json = excluded.metadata_json,
                    thumb_status = COALESCE(excluded.thumb_status, thumb_status),
                    thumb_path = COALESCE(excluded.thumb_path, thumb_path),
                    renderer_version = COALESCE(excluded.renderer_version, renderer_version)
                """,
                rows,
            )

    def upsert_from_file_record(
        self,
        record: Any,
        *,
        source_root: str = "",
        enriched: bool = False,
        thumb_status: str | None = None,
        thumb_path: str | None = None,
        renderer_version: str | None = None,
    ) -> None:
        """Persist fields from a :class:`~meshcorral.models.file_record.FileRecord`."""
        self.upsert(
            path=record.path,
            ext=getattr(record, "extension", "") or "",
            size_bytes=getattr(record, "size_bytes", None),
            modified_time=getattr(record, "modified_time", None),
            file_exists=True,
            source_root=source_root,
            thumb_status=thumb_status,
            thumb_path=thumb_path,
            renderer_version=renderer_version,
            enriched=enriched,
        )

    def mark_missing(self, path: str | Path) -> None:
        """Mark *path* as absent on disk (``file_exists=0``)."""
        key = _norm_path_key(path)
        now = time.time()
        with self._conn:
            self._conn.execute(
                """
                UPDATE asset_metadata_cache
                SET file_exists = 0, last_seen = ?
                WHERE path_key = ?
                """,
                (now, key),
            )

    def prune_older_than(self, days: float) -> int:
        """Delete rows not seen in *days* days. Returns rows removed."""
        cutoff = time.time() - float(days) * 86400.0
        with self._conn:
            cur = self._conn.execute(
                "DELETE FROM asset_metadata_cache WHERE last_seen < ?",
                (cutoff,),
            )
            removed = int(cur.rowcount or 0)
        self._last_prune_removed = removed
        logger.info("metadata cache pruned %s rows older than %.0f days", removed, days)
        return removed

    def clear_all(self) -> int:
        """Remove every cached row. Returns rows deleted."""
        with self._conn:
            cur = self._conn.execute("DELETE FROM asset_metadata_cache")
            removed = int(cur.rowcount or 0)
        logger.info("metadata cache cleared (%s rows)", removed)
        return removed

    def count_for_source_root(self, source_root: str) -> int:
        """Return how many cached rows are tagged with *source_root*."""
        root = str(source_root).strip()
        if not root:
            return 0
        cur = self._conn.execute(
            "SELECT COUNT(*) FROM asset_metadata_cache WHERE source_root = ?",
            (root,),
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0

    def stats(self) -> MetadataCacheStats:
        """Return row count and last prune removal count."""
        cur = self._conn.execute("SELECT COUNT(*) FROM asset_metadata_cache")
        row = cur.fetchone()
        count = int(row[0]) if row else 0
        return MetadataCacheStats(row_count=count, last_prune_removed=self._last_prune_removed)

    def iter_thumb_hints_for_paths(
        self, paths: list[str | Path]
    ) -> list[tuple[str, str]]:
        """
        Return ``(path_key, thumb_path)`` pairs with a cached ready thumbnail path.

        Used to prime :class:`~meshcorral.ui.thumbnail_ready_cache.ThumbnailReadyCache`
        without scanning every ``result.json``.
        """
        found = self.get_many(paths)
        hints: list[tuple[str, str]] = []
        for key, cached in found.items():
            if not cached.thumb_path:
                continue
            status = (cached.thumb_status or "").strip().lower()
            if status in ("", "ready", "complete", "has_thumbnail"):
                hints.append((key, cached.thumb_path))
        return hints


__all__ = [
    "CachedAssetMetadata",
    "MetadataCache",
    "MetadataCacheStats",
    "SCHEMA_VERSION",
    "default_metadata_cache_path",
]
