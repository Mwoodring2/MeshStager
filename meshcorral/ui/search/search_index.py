"""Lightweight in-memory search tokens for the working set."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from meshcorral.models.file_record import FileRecord
from meshcorral.services.metadata.asset_metadata_summary import AssetMetadataSummary
from meshcorral.services.metadata.metadata_summary_registry import MetadataSummaryRegistry
from meshcorral.ui.search.query_parser import IntPredicate, ParsedQuery, SizePredicate

logger = logging.getLogger(__name__)

_TYPE_ALIASES: dict[str, frozenset[str]] = {
    "3d": frozenset({"geometry", "dcc scene", "dcc", "3d", "3d asset"}),
    "image": frozenset({"image"}),
    "geometry": frozenset({"geometry"}),
    "dcc": frozenset({"dcc scene", "dcc"}),
    "support": frozenset({"support"}),
}


@dataclass(frozen=True, slots=True)
class IndexedRecord:
    """Precomputed lowercase fields for fast predicate checks."""

    record: FileRecord
    name: str
    extension: str
    folder: str
    path_text: str
    asset_type: str
    tags: str
    user_tag_set: frozenset[str]
    combined: str
    collection_names: frozenset[str] = frozenset()


def _normalize_extension(ext: str) -> str:
    return ext.lstrip(".").lower()


def _record_tags(record: FileRecord) -> str:
    """Optional tags string when present on the record (future metadata)."""
    raw = getattr(record, "tags", None)
    if raw is None:
        return ""
    if isinstance(raw, (list, tuple)):
        return " ".join(str(t) for t in raw).lower()
    return str(raw).lower()


def _asset_type_label(record: FileRecord) -> str:
    return (record.asset_family or "").lower()


def build_index_entry(
    record: FileRecord,
    *,
    user_tags: tuple[str, ...] = (),
    collections: tuple[str, ...] = (),
) -> IndexedRecord:
    """Build one index row from a :class:`FileRecord`."""
    name = record.name_lower
    extension = _normalize_extension(record.extension)
    folder = record.parent_folder.lower()
    path_text = str(record.path).lower()
    asset_type = _asset_type_label(record)
    bridge_tags = _record_tags(record)
    user_tag_set = frozenset(t.lower() for t in user_tags if t)
    user_part = " ".join(sorted(user_tag_set))
    tags = " ".join(p for p in (bridge_tags, user_part) if p).strip()
    combined = " ".join((name, extension, folder, path_text, asset_type, tags))
    return IndexedRecord(
        record=record,
        name=name,
        extension=extension,
        folder=folder,
        path_text=path_text,
        asset_type=asset_type,
        tags=tags,
        user_tag_set=user_tag_set,
        combined=combined,
        collection_names=frozenset(name.casefold() for name in collections),
    )


def _matches_asset_type(entry: IndexedRecord, type_token: str) -> bool:
    token = type_token.strip().lower()
    aliases = _TYPE_ALIASES.get(token)
    if aliases is not None:
        label = entry.asset_type
        return any(a in label or label in a for a in aliases)
    return token in entry.asset_type or token in entry.combined


def _matches_size(entry: IndexedRecord, pred: SizePredicate) -> bool:
    size = entry.record.size_bytes
    if size is None:
        return False
    if pred.op == ">":
        return size > pred.bytes_value
    return size < pred.bytes_value


def _matches_int_field(value: int | None, pred: IntPredicate) -> bool:
    if value is None:
        return False
    if pred.op == ">":
        return value > pred.value
    return value < pred.value


def record_matches_metadata(
    summary: AssetMetadataSummary | None,
    parsed: ParsedQuery,
) -> bool:
    """Apply metadata predicates; missing metadata never matches."""
    if not parsed.needs_metadata():
        return True
    if summary is None:
        return False
    if parsed.faces_predicate is not None:
        if not _matches_int_field(summary.face_count, parsed.faces_predicate):
            return False
    if parsed.watertight_required is not None:
        if summary.watertight is None:
            return False
        if summary.watertight != parsed.watertight_required:
            return False
    if parsed.archive_members_predicate is not None:
        if not _matches_int_field(summary.archive_member_count, parsed.archive_members_predicate):
            return False
    return True


def record_matches_query(entry: IndexedRecord, parsed: ParsedQuery) -> bool:
    """Return whether *entry* satisfies a parsed query."""
    if parsed.plain_fallback:
        return parsed.plain_fallback in entry.combined

    if parsed.plain_terms:
        for term in parsed.plain_terms:
            if term not in entry.combined:
                return False

    if parsed.extension is not None:
        want = _normalize_extension(parsed.extension)
        if entry.extension != want:
            return False

    if parsed.asset_type is not None:
        if not _matches_asset_type(entry, parsed.asset_type):
            return False

    if parsed.folder_contains is not None:
        if parsed.folder_contains not in entry.folder:
            return False

    if parsed.name_contains is not None:
        if parsed.name_contains not in entry.name:
            return False

    if parsed.size_predicate is not None:
        if not _matches_size(entry, parsed.size_predicate):
            return False

    if parsed.collection_name is not None and parsed.collection_name not in entry.collection_names:
        return False

    if parsed.tag_contains is not None:
        if parsed.tag_contains not in entry.user_tag_set:
            return False

    return True


class SearchIndex:
    """
    Token index over the current working set.

    Rebuild is O(n) over record count; kept cheap for typical local libraries.
    """

    def __init__(self) -> None:
        self._entries: list[IndexedRecord] = []
        self._source_len: int = -1
        self._source_id: int = -1
        self._user_tags_for: object | None = None
        self._collections_for: object | None = None

    @property
    def entries(self) -> list[IndexedRecord]:
        """Current indexed rows (read-only use)."""
        return self._entries

    def rebuild(
        self,
        records: list[FileRecord],
        *,
        user_tags_for: object | None = None,
        collections_for: object | None = None,
    ) -> None:
        """Rebuild the index from *records*."""
        tag_fn = user_tags_for
        if callable(tag_fn):
            self._entries = [
                build_index_entry(
                    r, user_tags=tag_fn(r),
                    collections=collections_for(r) if callable(collections_for) else (),
                ) for r in records
            ]
        else:
            self._entries = [
                build_index_entry(
                    r, collections=collections_for(r) if callable(collections_for) else (),
                ) for r in records
            ]
        self._source_len = len(records)
        self._source_id = id(records)
        self._user_tags_for = user_tags_for
        self._collections_for = collections_for

    def rebuild_if_stale(
        self,
        records: list[FileRecord],
        *,
        user_tags_for: object | None = None,
        collections_for: object | None = None,
    ) -> None:
        """Rebuild when the working set or user-metadata providers changed."""
        stale_tags = getattr(self, "_user_tags_for", None) is not user_tags_for
        if (
            not stale_tags
            and getattr(self, "_collections_for", None) is collections_for
            and id(records) == self._source_id
            and len(records) == self._source_len
        ):
            return
        self.rebuild(records, user_tags_for=user_tags_for, collections_for=collections_for)

    def filter_records(
        self,
        records: list[FileRecord],
        parsed: ParsedQuery,
        metadata_registry: MetadataSummaryRegistry | None = None,
        *,
        user_tags_for: object | None = None,
        collections_for: object | None = None,
    ) -> list[FileRecord]:
        """Filter *records* using indexed predicates (rebuilds index when stale)."""
        if parsed.is_empty():
            return list(records)
        self.rebuild_if_stale(records, user_tags_for=user_tags_for, collections_for=collections_for)
        path_to_entry = {e.record.path: e for e in self._entries}
        out: list[FileRecord] = []
        for rec in records:
            entry = path_to_entry.get(rec.path)
            if entry is None:
                tags: tuple[str, ...] = ()
                if callable(user_tags_for):
                    tags = user_tags_for(rec)  # type: ignore[misc]
                entry = build_index_entry(
                    rec, user_tags=tags,
                    collections=collections_for(rec) if callable(collections_for) else (),
                )
            if not record_matches_query(entry, parsed):
                continue
            summary = (
                metadata_registry.get(rec.path) if metadata_registry is not None else None
            )
            if not record_matches_metadata(summary, parsed):
                continue
            out.append(rec)
        return out
