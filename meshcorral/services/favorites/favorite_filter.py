"""Favorite filter labels for the left filter column (Tier 2.2)."""

from __future__ import annotations

FAVORITE_FILTER_ALL: str = "All"
FAVORITE_FILTER_ONLY: str = "Favorites Only"

FAVORITE_FILTER_CHOICES: tuple[str, ...] = (
    FAVORITE_FILTER_ALL,
    FAVORITE_FILTER_ONLY,
)
