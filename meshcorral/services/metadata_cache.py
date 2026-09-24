"""Persistent SQLite metadata cache (Prime Performance v0.8).

Caches stat metadata and thumbnail hints so repeat scans avoid redundant
filesystem probing and full ``result.json`` walks.
"""

from __future__ import annotations

import json
import logging
from contextlib import closing
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TYPE_CHECKING
from collections.abc import Callable, Iterable

if TYPE_CHECKING:
    from meshcorral.models.file_record import FileRecord

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.app.config import USER_DATA_DIR
from meshcorral.services.thumbnails.nonrenderable_thumbs import NonRenderableThumbEntry

logger = logging.getLogger(__name__)

SCHEMA_VERSION: int = 3
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
CREATE TABLE IF NOT EXISTS source_catalog_state (
    source_root TEXT PRIMARY KEY,
    recursive INTEGER NOT NULL,
    extensions_signature TEXT NOT NULL,
    last_completed_scan REAL NOT NULL,
    cached_record_count INTEGER NOT NULL,
    snapshot_complete INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS source_catalog_members (
    source_root TEXT NOT NULL,
    path TEXT NOT NULL,
    PRIMARY KEY (source_root, path)
);
CREATE TABLE IF NOT EXISTS cache_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS thumb_negative_cache (
    path_key TEXT PRIMARY KEY,
    path TEXT NOT NULL,
    ext TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL,
    detail TEXT,
    size_bytes INTEGER NOT NULL,
    modified_time REAL NOT NULL,
    recorded_at REAL NOT NULL
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


@dataclass(frozen=True, slots=True)
class SourceCatalog:
    records: list[FileRecord]
    thumbnail_hints: list[tuple[str, str]]


def catalog_root_key(root: str | Path) -> str:
    """Lexical identity only: cache reads must not probe a remote filesystem."""
    return os.path.normcase(os.path.abspath(os.fspath(root)))


def extensions_signature(extensions: Iterable[str] | None) -> str:
    from meshcorral.app.config import ALL_SUPPORTED_EXTENSIONS
    values = ALL_SUPPORTED_EXTENSIONS if extensions is None else extensions
    return json.dumps(sorted({str(ext).lower() for ext in values}), separators=(",", ":"))


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

    def has_complete_source(self, source_root: str | Path, recursive: bool,
                            extensions: Iterable[str] | None) -> bool:
        """Small indexed state lookup; no per-asset query or filesystem stat."""
        with closing(sqlite3.connect(str(self._db_path))) as conn, conn:
            return conn.execute(
                "SELECT 1 FROM source_catalog_state WHERE source_root=? AND recursive=? "
                "AND extensions_signature=? AND snapshot_complete=1",
                (catalog_root_key(source_root), int(recursive), extensions_signature(extensions)),
            ).fetchone() is not None

    def get_records_for_source_root(self, source_root: str | Path, recursive: bool,
                                    extensions: Iterable[str] | None) -> SourceCatalog | None:
        """One joined SELECT, then lightweight construction and Python's scan sort.

        Each caller owns its connection. Membership lives separately from mutable
        enrichment rows so overlapping roots and canceled scans cannot mix catalogs.
        """
        from meshcorral.models.file_record import FileRecord
        with closing(sqlite3.connect(str(self._db_path))) as conn, conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT a.*, s.cached_record_count FROM source_catalog_state s "
                "LEFT JOIN source_catalog_members m ON m.source_root=s.source_root "
                "LEFT JOIN asset_metadata_cache a ON a.path=m.path "
                "WHERE s.source_root=? AND s.recursive=? AND s.extensions_signature=? "
                "AND s.snapshot_complete=1",
                (catalog_root_key(source_root), int(recursive), extensions_signature(extensions)),
            ).fetchall()
        if not rows:
            return None
        expected = rows[0]["cached_record_count"]
        if expected == 0:
            return SourceCatalog([], [])
        if len(rows) != expected or any(row["path"] is None for row in rows):
            return None  # a pruned/incomplete cache must never masquerade as complete
        records = []
        hints = []
        for row in rows:
            path = Path(row["path"])
            records.append(FileRecord(path, path.name, row["ext"], path.parent.name,
                                      row["size_bytes"], row["modified_time"], "cache"))
            if row["thumb_path"] and (row["thumb_status"] or "").lower() in ("", "ready", "complete", "has_thumbnail"):
                hints.append((row["path"], row["thumb_path"]))
        records.sort(key=lambda record: str(record.path).lower())
        return SourceCatalog(records, hints)

    def complete_source_snapshot(self, source_root: str | Path, recursive: bool,
                                 extensions: Iterable[str] | None, records: Iterable[FileRecord],
                                 *, canceled: Callable[[], bool] = lambda: False) -> bool:
        """Atomically publish fully verified rows, membership, and completion state.

        Caller must have successfully traversed the root. No scan-time writes are
        made before this transaction; rollback retains the previous snapshot.
        """
        root = catalog_root_key(source_root)
        signature = extensions_signature(extensions)
        unique = {str(record.path): record for record in records}
        now = time.time()
        values = [(path, os.path.abspath(os.fspath(record.path)), record.extension, record.size_bytes,
                   record.modified_time, str(source_root), now) for path, record in unique.items()]
        if canceled():
            return False
        with closing(sqlite3.connect(str(self._db_path))) as conn, conn:
            conn.execute("CREATE TEMP TABLE verified (path TEXT PRIMARY KEY, path_key TEXT, ext TEXT, size_bytes INTEGER, modified_time REAL, source_root TEXT, last_seen REAL)")
            conn.executemany("INSERT INTO verified VALUES (?,?,?,?,?,?,?)", values)
            conn.execute(
                "UPDATE asset_metadata_cache SET file_exists=0 WHERE path IN "
                "(SELECT m.path FROM source_catalog_members m JOIN source_catalog_state s "
                "ON s.source_root=m.source_root WHERE m.source_root=? AND s.recursive=? "
                "AND s.extensions_signature=?) AND path NOT IN (SELECT path FROM verified)",
                (root, int(recursive), signature),
            )
            conn.execute("""
                INSERT INTO asset_metadata_cache
                (path,path_key,ext,size_bytes,modified_time,source_root,last_seen,file_exists)
                SELECT path,path_key,ext,size_bytes,modified_time,source_root,last_seen,1 FROM verified WHERE 1
                ON CONFLICT(path) DO UPDATE SET
                  path_key=excluded.path_key, ext=excluded.ext,
                  metadata_json=CASE WHEN size_bytes IS excluded.size_bytes AND modified_time IS excluded.modified_time THEN metadata_json ELSE NULL END,
                  thumb_status=CASE WHEN size_bytes IS excluded.size_bytes AND modified_time IS excluded.modified_time THEN thumb_status ELSE NULL END,
                  thumb_path=CASE WHEN size_bytes IS excluded.size_bytes AND modified_time IS excluded.modified_time THEN thumb_path ELSE NULL END,
                  size_bytes=excluded.size_bytes, modified_time=excluded.modified_time,
                  source_root=excluded.source_root,last_seen=excluded.last_seen,file_exists=1
            """)
            conn.execute("DELETE FROM source_catalog_members WHERE source_root=?", (root,))
            conn.execute("INSERT INTO source_catalog_members SELECT ?,path FROM verified", (root,))
            conn.execute("INSERT OR REPLACE INTO source_catalog_state VALUES (?,?,?,?,?,1)",
                         (root, int(recursive), signature, now, len(unique)))
            if canceled():
                conn.rollback()
                return False
        return True

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
            if row is None or int(row["value"]) < SCHEMA_VERSION:
                self._conn.execute(
                    "INSERT OR REPLACE INTO cache_meta (key, value) VALUES ('schema_version', ?)",
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

    @staticmethod
    def _row_to_non_renderable(row: sqlite3.Row) -> NonRenderableThumbEntry:
        return NonRenderableThumbEntry(
            path=str(row["path"]),
            path_key=str(row["path_key"]),
            ext=str(row["ext"] or ""),
            reason=str(row["reason"]),
            detail=row["detail"],
            size_bytes=int(row["size_bytes"]),
            modified_time=float(row["modified_time"]),
            recorded_at=float(row["recorded_at"]),
        )

    def record_non_renderable_thumb(
        self,
        *,
        path: str | Path,
        reason: str,
        size_bytes: int,
        modified_time: float,
        detail: str | None = None,
    ) -> None:
        """
        Persist a known non-renderable thumbnail result for *path*.

        The row is keyed by normalized path and carries the file's size and mtime, so a
        later edit of the source file makes the negative result stale automatically.
        """
        p = Path(path)
        now = time.time()
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO thumb_negative_cache (
                    path_key, path, ext, reason, detail,
                    size_bytes, modified_time, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path_key) DO UPDATE SET
                    path = excluded.path,
                    ext = excluded.ext,
                    reason = excluded.reason,
                    detail = excluded.detail,
                    size_bytes = excluded.size_bytes,
                    modified_time = excluded.modified_time,
                    recorded_at = excluded.recorded_at
                """,
                (
                    _norm_path_key(p),
                    str(p),
                    p.suffix.lower(),
                    str(reason),
                    detail,
                    int(size_bytes),
                    float(modified_time),
                    now,
                ),
            )
        logger.info("thumbnail marked non-renderable (%s): %s", reason, p)

    def non_renderable_thumb(self, path: str | Path) -> NonRenderableThumbEntry | None:
        """Return the persisted negative thumbnail result for *path*, if any."""
        cur = self._conn.execute(
            "SELECT * FROM thumb_negative_cache WHERE path_key = ? LIMIT 1",
            (_norm_path_key(path),),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_non_renderable(row)

    def non_renderable_thumbs_for_paths(
        self,
        paths: list[str | Path],
    ) -> list[NonRenderableThumbEntry]:
        """Batch lookup so a view can hydrate negative state without per-row queries."""
        if not paths:
            return []
        keys = [_norm_path_key(p) for p in paths]
        placeholders = ",".join("?" * len(keys))
        cur = self._conn.execute(
            f"SELECT * FROM thumb_negative_cache WHERE path_key IN ({placeholders})",
            keys,
        )
        return [self._row_to_non_renderable(row) for row in cur.fetchall()]

    def clear_non_renderable_thumb(self, path: str | Path) -> bool:
        """Forget the negative result for *path* (manual regenerate). True if removed."""
        with self._conn:
            cur = self._conn.execute(
                "DELETE FROM thumb_negative_cache WHERE path_key = ?",
                (_norm_path_key(path),),
            )
        return int(cur.rowcount or 0) > 0

    def non_renderable_thumb_count(self) -> int:
        """Number of persisted negative thumbnail results (diagnostics)."""
        cur = self._conn.execute("SELECT COUNT(*) FROM thumb_negative_cache")
        row = cur.fetchone()
        return int(row[0]) if row else 0

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
        """
        Remove every cached row, including negative thumbnail results.

        Age-based :meth:`prune_older_than` deliberately leaves ``thumb_negative_cache``
        alone: those rows are invalidated by file fingerprint, not by age.
        """
        with self._conn:
            self._conn.execute("DELETE FROM source_catalog_members")
            self._conn.execute("DELETE FROM source_catalog_state")
            self._conn.execute("DELETE FROM thumb_negative_cache")
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
    "NonRenderableThumbEntry",
    "SCHEMA_VERSION",
    "default_metadata_cache_path",
]
