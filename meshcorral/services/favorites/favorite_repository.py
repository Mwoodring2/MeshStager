"""SQLite persistence for asset favorites (Tier 2.2)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.app.config import USER_DATA_DIR

SCHEMA_VERSION: int = 1
DEFAULT_DB_PATH = USER_DATA_DIR / "cache" / "asset_favorites.sqlite"

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS asset_favorites (
    asset_path TEXT PRIMARY KEY,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS favorite_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class FavoriteRepository:
    """SQLite store for favorited asset paths."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = Path(db_path or DEFAULT_DB_PATH)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        self._migrate()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def _migrate(self) -> None:
        with self._conn:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS favorite_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            row = self._conn.execute(
                "SELECT value FROM favorite_meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                self._conn.executescript(_CREATE_SQL)
                self._conn.execute(
                    "INSERT INTO favorite_meta (key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
            else:
                self._conn.executescript(_CREATE_SQL)

    @staticmethod
    def normalize_asset_path(path: Path | str) -> str:
        """Stable path key."""
        return _norm_path_key(path)

    def set_favorite(self, asset_path: Path | str, *, favorite: bool) -> None:
        """Mark or clear favorite for *asset_path*."""
        path_s = self.normalize_asset_path(asset_path)
        with self._conn:
            if favorite:
                self._conn.execute(
                    """
                    INSERT OR IGNORE INTO asset_favorites (asset_path, created_at)
                    VALUES (?, ?)
                    """,
                    (path_s, _utc_now_iso()),
                )
            else:
                self._conn.execute(
                    "DELETE FROM asset_favorites WHERE asset_path = ?",
                    (path_s,),
                )

    def is_favorite(self, asset_path: Path | str) -> bool:
        """Return True when *asset_path* is favorited."""
        path_s = self.normalize_asset_path(asset_path)
        row = self._conn.execute(
            "SELECT 1 FROM asset_favorites WHERE asset_path = ? LIMIT 1",
            (path_s,),
        ).fetchone()
        return row is not None

    def all_favorite_paths(self) -> set[str]:
        """All favorited normalized paths."""
        rows = self._conn.execute("SELECT asset_path FROM asset_favorites").fetchall()
        return {str(r[0]) for r in rows}
