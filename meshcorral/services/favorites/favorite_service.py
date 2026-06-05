"""Favorite flag operations (Tier 2.2)."""

from __future__ import annotations

from pathlib import Path

from meshcorral.models.file_record import FileRecord
from meshcorral.services.favorites.favorite_repository import FavoriteRepository


class FavoriteService:
    """Single source of truth for asset favorites."""

    def __init__(self, repository: FavoriteRepository | None = None) -> None:
        self._repo = repository or FavoriteRepository()

    def close(self) -> None:
        """Release the repository connection."""
        self._repo.close()

    def set_favorite(self, asset_path: Path | str, *, favorite: bool) -> None:
        """Set favorite state for one asset."""
        self._repo.set_favorite(asset_path, favorite=favorite)

    def is_favorite(self, asset_path: Path | str) -> bool:
        """Return whether *asset_path* is favorited."""
        return self._repo.is_favorite(asset_path)

    def toggle_favorite(self, asset_path: Path | str) -> bool:
        """Flip favorite state; returns the new state."""
        new_state = not self.is_favorite(asset_path)
        self.set_favorite(asset_path, favorite=new_state)
        return new_state

    def is_favorite_record(self, record: FileRecord) -> bool:
        """Favorite check for a :class:`FileRecord`."""
        return self.is_favorite(record.path)
