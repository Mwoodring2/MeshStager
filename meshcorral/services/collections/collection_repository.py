"""SQLite storage for collections, independent of asset files and caches."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Iterable

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.app.config import USER_DATA_DIR

DEFAULT_DB_PATH = USER_DATA_DIR / "cache" / "asset_collections.sqlite"
MAX_NAME_LENGTH = 120


def validate_name(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("Enter a collection name.")
    name = name.strip()
    if not name:
        raise ValueError("Enter a collection name.")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"Collection names may contain up to {MAX_NAME_LENGTH} characters.")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise ValueError("Collection names cannot contain control characters.")
    return name


@dataclass(frozen=True, slots=True)
class Collection:
    collection_id: int
    name: str
    created_at: str
    modified_at: str
    member_count: int = 0


class CollectionRepository:
    """One synchronous, owner-thread connection; batch writes are atomic."""

    normalize_asset_path = staticmethod(_norm_path_key)

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path or DEFAULT_DB_PATH)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS collections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    name_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    modified_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS collection_members (
                    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
                    asset_path TEXT NOT NULL,
                    PRIMARY KEY (collection_id, asset_path)
                );
                CREATE INDEX IF NOT EXISTS idx_collection_members_path
                    ON collection_members(asset_path);
                CREATE TABLE IF NOT EXISTS collection_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            """)
            with self._conn:
                self._conn.execute(
                    "INSERT OR IGNORE INTO collection_meta(key, value) VALUES (?, ?)",
                    ("schema_version", "1"),
                )
        except Exception:
            self._conn.close()
            raise

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_collection(self, name: str) -> Collection:
        name = validate_name(name)
        now = self._now()
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO collections(name, name_key, created_at, modified_at) VALUES (?, ?, ?, ?)",
                (name, name.casefold(), now, now),
            )
        return self.get_collection(cur.lastrowid)

    def get_collection(self, collection_id: int) -> Collection:
        row = self._conn.execute("""
            SELECT c.id, c.name, c.created_at, c.modified_at, COUNT(m.asset_path) AS member_count
            FROM collections c LEFT JOIN collection_members m ON c.id = m.collection_id
            WHERE c.id = ? GROUP BY c.id
        """, (collection_id,)).fetchone()
        if row is None:
            raise ValueError("This collection no longer exists.")
        return Collection(*tuple(row))

    def list_collections(self) -> list[Collection]:
        rows = self._conn.execute("""
            SELECT c.id, c.name, c.created_at, c.modified_at, COUNT(m.asset_path)
            FROM collections c LEFT JOIN collection_members m ON c.id = m.collection_id
            GROUP BY c.id ORDER BY c.name_key, c.id
        """).fetchall()
        return [Collection(*tuple(row)) for row in rows]

    def rename_collection(self, collection_id: int, name: str) -> Collection:
        name = validate_name(name)
        with self._conn:
            cur = self._conn.execute(
                "UPDATE collections SET name = ?, name_key = ?, modified_at = ? WHERE id = ?",
                (name, name.casefold(), self._now(), collection_id),
            )
            if not cur.rowcount:
                raise ValueError("This collection no longer exists.")
        return self.get_collection(collection_id)

    def delete_collection(self, collection_id: int) -> bool:
        with self._conn:
            cur = self._conn.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
        return bool(cur.rowcount)

    def change_members(self, collection_id: int, paths: Iterable[Path | str], *, add: bool) -> int:
        keys = set(self.normalize_asset_path(path) for path in paths)
        with self._conn:
            self.get_collection(collection_id)
            before = self._conn.total_changes
            sql = (
                "INSERT OR IGNORE INTO collection_members(collection_id, asset_path) VALUES (?, ?)"
                if add else "DELETE FROM collection_members WHERE collection_id = ? AND asset_path = ?"
            )
            self._conn.executemany(sql, ((collection_id, key) for key in keys))
            changed = self._conn.total_changes - before
            if changed:
                self._conn.execute("UPDATE collections SET modified_at = ? WHERE id = ?",
                                   (self._now(), collection_id))
        return changed

    def get_members(self, collection_id: int) -> frozenset[str]:
        return frozenset(row[0] for row in self._conn.execute(
            "SELECT asset_path FROM collection_members WHERE collection_id = ?", (collection_id,)))

    def get_collections_for_asset(self, path: Path | str) -> list[Collection]:
        ids = {row[0] for row in self._conn.execute(
            "SELECT collection_id FROM collection_members WHERE asset_path = ?",
            (self.normalize_asset_path(path),))}
        return [c for c in self.list_collections() if c.collection_id in ids]

    def is_member(self, collection_id: int, path: Path | str) -> bool:
        return self._conn.execute(
            "SELECT 1 FROM collection_members WHERE collection_id = ? AND asset_path = ?",
            (collection_id, self.normalize_asset_path(path)),
        ).fetchone() is not None

    def membership_rows(self) -> list[tuple[int, str]]:
        """Single batch read for an in-memory UI/search snapshot."""
        return [tuple(row) for row in self._conn.execute(
            "SELECT collection_id, asset_path FROM collection_members")]
