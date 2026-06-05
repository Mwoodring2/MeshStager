"""Archive manifest cache for ZIP files (Prime Performance v0.8).

Indexes member names inside ``.zip`` archives without extracting contents.
Reuse is keyed on archive size + mtime.
"""

from __future__ import annotations

import logging
import sqlite3
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

from meshcorral.app.config import USER_DATA_DIR

logger = logging.getLogger(__name__)

SCHEMA_VERSION: int = 1
DEFAULT_DB_PATH = USER_DATA_DIR / "cache" / "archive_manifest.sqlite"
ZIP_SUFFIX = ".zip"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS archive_manifest_meta (
    archive_path TEXT PRIMARY KEY,
    archive_size INTEGER NOT NULL,
    archive_modified_time REAL NOT NULL,
    member_count INTEGER NOT NULL DEFAULT 0,
    last_indexed REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS archive_manifest_entries (
    archive_path TEXT NOT NULL,
    member_path TEXT NOT NULL,
    member_size INTEGER,
    member_modified_time REAL,
    member_ext TEXT NOT NULL DEFAULT '',
    last_indexed REAL NOT NULL,
    PRIMARY KEY (archive_path, member_path)
);
CREATE INDEX IF NOT EXISTS idx_archive_manifest_entries_archive
    ON archive_manifest_entries (archive_path);
CREATE TABLE IF NOT EXISTS cache_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


@dataclass(frozen=True, slots=True)
class ArchiveManifestMember:
    """One member inside a cached archive manifest."""

    member_path: str
    member_size: int | None
    member_modified_time: float | None
    member_ext: str


@dataclass(frozen=True, slots=True)
class ArchiveIndexResult:
    """Outcome of indexing or reusing a cached manifest."""

    archive_path: str
    member_count: int
    reused_cache: bool
    rebuilt: bool


@dataclass(frozen=True, slots=True)
class ArchiveManifestCacheStats:
    """Diagnostics for the archive manifest store."""

    archive_count: int
    entry_count: int


def default_archive_manifest_cache_path() -> Path:
    """Return the default on-disk path for the archive manifest database."""
    return DEFAULT_DB_PATH


class ArchiveManifestCache:
    """
    SQLite-backed ZIP manifest cache.

    Only ``.zip`` is supported in v0.8; other formats are reserved for later.
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path or DEFAULT_DB_PATH)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._migrate()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def _migrate(self) -> None:
        with self._conn:
            self._conn.executescript(_CREATE_SQL)
            cur = self._conn.execute(
                "SELECT value FROM cache_meta WHERE key = 'schema_version'"
            )
            if cur.fetchone() is None:
                self._conn.execute(
                    "INSERT INTO cache_meta (key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )

    @staticmethod
    def is_supported_archive(path: Path) -> bool:
        """True when *path* is a ZIP archive we can index in v0.8."""
        return path.suffix.lower() == ZIP_SUFFIX

    def _archive_signature(self, path: Path) -> tuple[int, float] | None:
        try:
            st = path.stat()
        except OSError:
            return None
        return int(st.st_size), float(st.st_mtime)

    def _cached_signature(self, archive_path: str) -> tuple[int, float] | None:
        cur = self._conn.execute(
            """
            SELECT archive_size, archive_modified_time
            FROM archive_manifest_meta WHERE archive_path = ?
            """,
            (archive_path,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return int(row["archive_size"]), float(row["archive_modified_time"])

    def ensure_indexed(self, archive_path: str | Path) -> ArchiveIndexResult | None:
        """
        Return a cached manifest when the archive signature is unchanged.

        Otherwise read the ZIP central directory only (no extraction) and cache
        member paths. Returns ``None`` when the path is missing or not a ZIP.
        """
        path = Path(archive_path)
        if not self.is_supported_archive(path):
            return None
        try:
            if not path.is_file():
                return None
        except OSError:
            return None

        path_s = str(path)
        sig = self._archive_signature(path)
        if sig is None:
            return None
        size, mtime = sig
        cached_sig = self._cached_signature(path_s)
        if cached_sig == sig:
            cur = self._conn.execute(
                "SELECT member_count FROM archive_manifest_meta WHERE archive_path = ?",
                (path_s,),
            )
            row = cur.fetchone()
            count = int(row["member_count"]) if row else 0
            return ArchiveIndexResult(
                archive_path=path_s,
                member_count=count,
                reused_cache=True,
                rebuilt=False,
            )
        return self._rebuild_manifest(path, size=size, mtime=mtime)

    def _rebuild_manifest(
        self, path: Path, *, size: int, mtime: float
    ) -> ArchiveIndexResult | None:
        path_s = str(path)
        members: list[ArchiveManifestMember] = []
        try:
            with zipfile.ZipFile(path, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    name = info.filename.replace("\\", "/")
                    ext = Path(name).suffix.lower()
                    members.append(
                        ArchiveManifestMember(
                            member_path=name,
                            member_size=int(info.file_size) if info.file_size >= 0 else None,
                            member_modified_time=float(info.date_time[0]) if info.date_time else None,
                            member_ext=ext,
                        )
                    )
        except (OSError, zipfile.BadZipFile) as exc:
            logger.warning("archive manifest index failed for %s: %s", path_s, exc)
            return None

        now = time.time()
        with self._conn:
            self._conn.execute(
                "DELETE FROM archive_manifest_entries WHERE archive_path = ?",
                (path_s,),
            )
            self._conn.execute(
                "DELETE FROM archive_manifest_meta WHERE archive_path = ?",
                (path_s,),
            )
            if members:
                self._conn.executemany(
                    """
                    INSERT INTO archive_manifest_entries (
                        archive_path, member_path, member_size,
                        member_modified_time, member_ext, last_indexed
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            path_s,
                            m.member_path,
                            m.member_size,
                            m.member_modified_time,
                            m.member_ext,
                            now,
                        )
                        for m in members
                    ],
                )
            self._conn.execute(
                """
                INSERT INTO archive_manifest_meta (
                    archive_path, archive_size, archive_modified_time,
                    member_count, last_indexed
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (path_s, size, mtime, len(members), now),
            )
        logger.debug(
            "archive manifest indexed %s (%s members, rebuilt)",
            path_s,
            len(members),
        )
        return ArchiveIndexResult(
            archive_path=path_s,
            member_count=len(members),
            reused_cache=False,
            rebuilt=True,
        )

    def list_members(self, archive_path: str | Path) -> list[ArchiveManifestMember]:
        """Return cached members for *archive_path* (may be empty)."""
        path_s = str(archive_path)
        cur = self._conn.execute(
            """
            SELECT member_path, member_size, member_modified_time, member_ext
            FROM archive_manifest_entries
            WHERE archive_path = ?
            ORDER BY member_path
            """,
            (path_s,),
        )
        return [
            ArchiveManifestMember(
                member_path=str(row["member_path"]),
                member_size=row["member_size"],
                member_modified_time=row["member_modified_time"],
                member_ext=str(row["member_ext"] or ""),
            )
            for row in cur.fetchall()
        ]

    def stats(self) -> ArchiveManifestCacheStats:
        """Return aggregate archive / entry counts."""
        cur_a = self._conn.execute("SELECT COUNT(*) FROM archive_manifest_meta")
        cur_e = self._conn.execute("SELECT COUNT(*) FROM archive_manifest_entries")
        a_row = cur_a.fetchone()
        e_row = cur_e.fetchone()
        return ArchiveManifestCacheStats(
            archive_count=int(a_row[0]) if a_row else 0,
            entry_count=int(e_row[0]) if e_row else 0,
        )

    def force_rebuild(self, archive_path: str | Path) -> ArchiveIndexResult | None:
        """Delete cached manifest for *archive_path* and re-index from disk."""
        path_s = str(archive_path)
        with self._conn:
            self._conn.execute(
                "DELETE FROM archive_manifest_entries WHERE archive_path = ?",
                (path_s,),
            )
            self._conn.execute(
                "DELETE FROM archive_manifest_meta WHERE archive_path = ?",
                (path_s,),
            )
        return self.ensure_indexed(archive_path)

    def clear_all(self) -> None:
        """Drop all cached manifests."""
        with self._conn:
            self._conn.execute("DELETE FROM archive_manifest_entries")
            self._conn.execute("DELETE FROM archive_manifest_meta")
        logger.info("archive manifest cache cleared")


__all__ = [
    "ArchiveIndexResult",
    "ArchiveManifestCache",
    "ArchiveManifestCacheStats",
    "ArchiveManifestMember",
    "default_archive_manifest_cache_path",
]
