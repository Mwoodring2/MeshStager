"""SQLite persistence for user asset tags (Tier 2.1)."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.app.config import USER_DATA_DIR
from meshcorral.services.tagging.tag_models import AssetTagRow

logger = logging.getLogger(__name__)

SCHEMA_VERSION: int = 2
DEFAULT_DB_PATH = USER_DATA_DIR / "cache" / "asset_tags.sqlite"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS asset_tags (
    id INTEGER PRIMARY KEY,
    asset_path TEXT NOT NULL,
    tag TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(asset_path, tag)
);
CREATE INDEX IF NOT EXISTS idx_asset_tags_path ON asset_tags(asset_path);
CREATE INDEX IF NOT EXISTS idx_asset_tags_tag ON asset_tags(tag);
CREATE TABLE IF NOT EXISTS tag_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class TagRepository:
    """
    Thread-safe tag store (``check_same_thread=False``).

    UI and services use :class:`TagService`; this class talks to SQLite only.
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
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS tag_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            row = self._conn.execute(
                "SELECT value FROM tag_meta WHERE key = 'schema_version'"
            ).fetchone()
            version = int(row["value"]) if row is not None else 0
            if version < SCHEMA_VERSION:
                self._conn.executescript(
                    "DROP TABLE IF EXISTS asset_tags;"
                    "DROP TABLE IF EXISTS tags;"
                )
            self._conn.executescript(_CREATE_SQL)
            if version < SCHEMA_VERSION:
                self._conn.execute(
                    """
                    INSERT INTO tag_meta (key, value) VALUES ('schema_version', ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (str(SCHEMA_VERSION),),
                )

    @staticmethod
    def normalize_asset_path(path: Path | str) -> str:
        """Stable absolute path key for one asset."""
        return _norm_path_key(path)

    def add_tag(self, asset_path: Path | str, tag: str) -> bool:
        """Insert one tag assignment. Returns False if already present."""
        path_s = self.normalize_asset_path(asset_path)
        created = _utc_now_iso()
        with self._conn:
            cur = self._conn.execute(
                """
                INSERT OR IGNORE INTO asset_tags (asset_path, tag, created_at)
                VALUES (?, ?, ?)
                """,
                (path_s, tag, created),
            )
        return int(cur.rowcount) > 0

    def remove_tag(self, asset_path: Path | str, tag: str) -> bool:
        """Remove one tag from an asset."""
        path_s = self.normalize_asset_path(asset_path)
        with self._conn:
            cur = self._conn.execute(
                "DELETE FROM asset_tags WHERE asset_path = ? AND tag = ?",
                (path_s, tag),
            )
        return int(cur.rowcount) > 0

    def get_tags(self, asset_path: Path | str) -> list[str]:
        """Sorted tag list for one asset."""
        path_s = self.normalize_asset_path(asset_path)
        rows = self._conn.execute(
            """
            SELECT tag FROM asset_tags
            WHERE asset_path = ?
            ORDER BY tag COLLATE NOCASE
            """,
            (path_s,),
        ).fetchall()
        return [str(r["tag"]) for r in rows]

    def find_asset_paths_by_tag(self, tag: str) -> list[str]:
        """All ``asset_path`` values that carry *tag*."""
        rows = self._conn.execute(
            """
            SELECT DISTINCT asset_path FROM asset_tags
            WHERE tag = ?
            ORDER BY asset_path
            """,
            (tag,),
        ).fetchall()
        return [str(r["asset_path"]) for r in rows]

    def list_rows_for_path(self, asset_path: Path | str) -> list[AssetTagRow]:
        """All tag rows for one asset (tests / diagnostics)."""
        path_s = self.normalize_asset_path(asset_path)
        rows = self._conn.execute(
            """
            SELECT id, asset_path, tag, created_at FROM asset_tags
            WHERE asset_path = ?
            ORDER BY tag COLLATE NOCASE
            """,
            (path_s,),
        ).fetchall()
        return [
            AssetTagRow(
                row_id=int(r["id"]),
                asset_path=str(r["asset_path"]),
                tag=str(r["tag"]),
                created_at=str(r["created_at"]),
            )
            for r in rows
        ]
