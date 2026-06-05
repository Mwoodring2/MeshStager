"""Favorite asset records (Tier 2.2)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class FavoriteRow:
    """One favorited asset path."""

    asset_path: str
    created_at: str
