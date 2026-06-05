"""User tag operations — single source of truth (Tier 2.1)."""

from __future__ import annotations

import logging
from pathlib import Path

from meshcorral.services.tagging.tag_repository import TagRepository
from meshcorral.services.tagging.tag_validation import normalize_tag, parse_tags_from_dialog

logger = logging.getLogger(__name__)


class TagService:
    """
    High-level tag API for UI and search.

    Does not touch scan, thumbnail, or metadata caches.
    """

    def __init__(self, repository: TagRepository | None = None) -> None:
        self._repo = repository or TagRepository()

    def close(self) -> None:
        """Release the repository connection."""
        self._repo.close()

    @property
    def repository(self) -> TagRepository:
        """Underlying store (tests)."""
        return self._repo

    def add_tag(self, asset_path: Path | str, tag: str) -> None:
        """Add one normalized tag to an asset."""
        normalized = normalize_tag(tag)
        self._repo.add_tag(asset_path, normalized)

    def remove_tag(self, asset_path: Path | str, tag: str) -> bool:
        """Remove a tag from an asset."""
        return self._repo.remove_tag(asset_path, normalize_tag(tag))

    def get_tags(self, asset_path: Path | str) -> list[str]:
        """Tags on one asset (normalized, sorted)."""
        return self._repo.get_tags(asset_path)

    def find_assets_by_tag(self, tag: str) -> list[str]:
        """Normalized asset paths that have *tag*."""
        return self._repo.find_asset_paths_by_tag(normalize_tag(tag))

    def tags_display_for_path(self, asset_path: Path | str) -> str:
        """Comma-separated tags for the Metadata tab."""
        tags = self.get_tags(asset_path)
        if not tags:
            return "No tags assigned"
        return ", ".join(tags)

    def user_tags_for_record(self, asset_path: Path | str) -> tuple[str, ...]:
        """Normalized tag names for search indexing."""
        return tuple(self.get_tags(asset_path))

    def add_tags_from_dialog(self, asset_paths: list[Path], dialog_text: str) -> int:
        """
        Apply every parsed tag to each path in *asset_paths*.

        Returns the number of (path, tag) assignments attempted.
        """
        tags = parse_tags_from_dialog(dialog_text)
        count = 0
        for path in asset_paths:
            for tag in tags:
                self.add_tag(path, tag)
                count += 1
        return count

    def add_tag_to_paths(self, paths: list[Path], raw_tag: str) -> None:
        """Apply one tag to many assets (multi-select)."""
        normalized = normalize_tag(raw_tag)
        for path in paths:
            self._repo.add_tag(path, normalized)
