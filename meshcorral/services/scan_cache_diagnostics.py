"""Scan-time cache diagnostics (Prime Performance v0.8)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from meshcorral.services.archive_manifest_cache import ArchiveManifestCache
    from meshcorral.services.metadata_cache import MetadataCache


@dataclass(frozen=True, slots=True)
class ScanCacheContext:
    """Optional caches passed into a background folder scan (v0.8)."""

    metadata_cache: MetadataCache | None = None
    source_root: str = ""
    network_optimistic: bool = False
    archive_manifest_cache: ArchiveManifestCache | None = None
    scan_cache_diagnostics: ScanCacheDiagnostics | None = None


@dataclass(slots=True)
class ScanCacheDiagnostics:
    """Counters accumulated during one folder scan."""

    records_discovered: int = 0
    metadata_cache_hits: int = 0
    metadata_cache_misses: int = 0
    archive_manifests_reused: int = 0
    archive_manifests_rebuilt: int = 0
    archive_manifests_failed: int = 0

    def note_record(self, *, from_cache: bool) -> None:
        """Record one scanned file row."""
        self.records_discovered += 1
        if from_cache:
            self.metadata_cache_hits += 1
        else:
            self.metadata_cache_misses += 1

    def note_archive_index(self, *, reused: bool, rebuilt: bool, failed: bool) -> None:
        """Record one archive manifest index attempt."""
        if failed:
            self.archive_manifests_failed += 1
        elif reused:
            self.archive_manifests_reused += 1
        elif rebuilt:
            self.archive_manifests_rebuilt += 1

    def cache_hit_rate(self) -> float:
        """Fraction of records hydrated from cache (0..1)."""
        total = self.metadata_cache_hits + self.metadata_cache_misses
        if total <= 0:
            return 0.0
        return self.metadata_cache_hits / total

    def summary_line(self, *, network_like: bool) -> str:
        """Human-readable status fragment for the status bar."""
        n = self.records_discovered
        hits = self.metadata_cache_hits
        if n <= 0:
            return ""
        if hits > 0:
            base = f"Loaded {n:,} records, {hits:,} from cache."
        else:
            base = f"Loaded {n:,} records."
        if network_like and hits > 0:
            base += " Server folder: using cached metadata while enrichment runs."
        return base


__all__ = ["ScanCacheContext", "ScanCacheDiagnostics"]
