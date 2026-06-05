"""Lightweight asset metadata (Prime v1.0 Sprint E)."""

from meshcorral.services.metadata.asset_metadata_summary import AssetMetadataSummary
from meshcorral.services.metadata.metadata_summary_registry import MetadataSummaryRegistry
from meshcorral.services.metadata.metadata_tunables import (
    allow_large_inspector,
    max_inline_bytes,
)

__all__ = [
    "AssetMetadataSummary",
    "MetadataSummaryRegistry",
    "allow_large_inspector",
    "max_inline_bytes",
]
