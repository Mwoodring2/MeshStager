"""User-defined asset tag records (Tier 2.1)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AssetTagRow:
    """One row in ``asset_tags``."""

    row_id: int
    asset_path: str
    tag: str
    created_at: str
