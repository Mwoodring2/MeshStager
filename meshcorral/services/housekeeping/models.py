"""Housekeeping finding identities and centralized conservative policy."""
from __future__ import annotations
from dataclasses import dataclass, field
import hashlib
import json
from meshcorral.services.metadata_cache import catalog_root_key as path_key

LABELS = {
    "exact_duplicate": "Exact Duplicates", "possible_duplicate": "Possible Duplicates",
    "archive_extracted": "Archive + Extracted", "broken": "Broken Files",
    "zero_byte": "Zero-byte Files", "missing_companion": "Missing Companion Files",
    "naming": "Naming Issues", "large": "Large Assets",
}
LARGE_ASSET_BYTES = 128 * 1024 * 1024
HASH_CHUNK_BYTES = 1024 * 1024
TEXT_LIMIT_BYTES = 2 * 1024 * 1024
POSSIBLE_SIZE_RATIO = .01

class AnalysisCanceled(Exception):
    """Cooperative cancellation; no new generation may be published."""

def checkpoint(canceled):
    if canceled():
        raise AnalysisCanceled()

def stable_id(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()

@dataclass(frozen=True, slots=True)
class Finding:
    finding_id: str
    path: str
    kind: str
    severity: str
    group_id: str
    identity: str
    details: dict
    ignored: bool = False


def finding(record, kind, details, *, group="", identity=None):
    key = path_key(record.path)
    return Finding(stable_id(key, kind, group, details.get("rule", "")), key, kind,
                   "info" if kind in ("large", "naming", "archive_extracted") else "review",
                   group, identity or stable_id(record.size_bytes, record.modified_time), details)

@dataclass(slots=True)
class AnalysisStats:
    total_assets: int = 0
    size_candidates: int = 0
    hashed_assets: int = 0
    hashed_bytes: int = 0
    warning_count: int = 0
    warnings: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def warn(self, message):
        self.warning_count += 1
        if len(self.warnings) < 100:
            self.warnings.append(str(message))

@dataclass(frozen=True, slots=True)
class Snapshot:
    generation: str = ""
    findings: tuple[Finding, ...] = ()
