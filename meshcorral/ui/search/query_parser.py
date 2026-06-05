"""Structured search query parsing (Prime v1.0 Sprint C)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

_SIZE_PATTERN = re.compile(
    r"^size(?P<op>[<>])(?P<num>\d+(?:\.\d+)?)(?P<unit>[kmgt]?b)?$",
    re.IGNORECASE,
)
_KNOWN_PREFIXES = frozenset(
    {
        "ext",
        "type",
        "folder",
        "name",
        "tag",
        "size",
        "faces",
        "watertight",
        "archive_members",
    }
)
_INT_PATTERN = re.compile(r"^(faces|archive_members)(?P<op>[<>])(?P<num>\d+)$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class IntPredicate:
    """Integer comparison for ``faces>100000`` or ``archive_members>0`` tokens."""

    field: str
    op: Literal[">", "<"]
    value: int


@dataclass(frozen=True, slots=True)
class SizePredicate:
    """Byte-size comparison from ``size>100mb`` style tokens."""

    op: Literal[">", "<"]
    bytes_value: int


@dataclass(frozen=True, slots=True)
class ParsedQuery:
    """
    Normalized query: structured predicates plus optional plain-text terms.

    When *plain_fallback* is set, the entire raw query is one case-insensitive
    substring match across indexed fields (unknown ``key:value`` syntax).
    """

    plain_terms: tuple[str, ...] = ()
    plain_fallback: str | None = None
    extension: str | None = None
    asset_type: str | None = None
    folder_contains: str | None = None
    name_contains: str | None = None
    size_predicate: SizePredicate | None = None
    faces_predicate: IntPredicate | None = None
    watertight_required: bool | None = None
    archive_members_predicate: IntPredicate | None = None
    tag_contains: str | None = None

    def needs_metadata(self) -> bool:
        """True when matching requires :class:`AssetMetadataSummary` fields."""
        return (
            self.faces_predicate is not None
            or self.watertight_required is not None
            or self.archive_members_predicate is not None
        )

    def is_empty(self) -> bool:
        """True when the query imposes no extra constraints beyond combo filters."""
        return (
            not self.plain_terms
            and self.plain_fallback is None
            and self.extension is None
            and self.asset_type is None
            and self.folder_contains is None
            and self.name_contains is None
            and self.size_predicate is None
            and self.faces_predicate is None
            and self.watertight_required is None
            and self.archive_members_predicate is None
            and self.tag_contains is None
        )

    @staticmethod
    def from_plain_text(text: str) -> ParsedQuery:
        """Treat the full string as a single substring search."""
        stripped = text.strip()
        if not stripped:
            return ParsedQuery()
        return ParsedQuery(plain_fallback=stripped.lower())


def _size_unit_multiplier(unit: str) -> int:
    u = (unit or "b").lower()
    if u in ("b", ""):
        return 1
    if u == "kb":
        return 1024
    if u == "mb":
        return 1024 * 1024
    if u == "gb":
        return 1024 * 1024 * 1024
    if u == "tb":
        return 1024 * 1024 * 1024 * 1024
    return 1


def parse_int_predicate_token(token: str) -> IntPredicate | None:
    """Parse ``faces>100000`` or ``archive_members>0`` style tokens."""
    match = _INT_PATTERN.match(token.strip())
    if match is None:
        return None
    field = match.group(1).lower()
    op = match.group("op")
    if op not in (">", "<"):
        return None
    return IntPredicate(field=field, op=op, value=int(match.group("num")))  # type: ignore[arg-type]


def parse_size_token(value: str) -> SizePredicate | None:
    """
    Parse ``>100mb`` or ``<2gb`` tail after a ``size:`` prefix, or a combined
    ``size>100mb`` token.
    """
    raw = value.strip()
    if not raw:
        return None
    combined = raw if raw.lower().startswith("size") else f"size{raw}"
    match = _SIZE_PATTERN.match(combined)
    if match is None:
        return None
    op = match.group("op")
    if op not in (">", "<"):
        return None
    num = float(match.group("num"))
    unit = match.group("unit") or "b"
    bytes_value = int(num * _size_unit_multiplier(unit))
    return SizePredicate(op=op, bytes_value=bytes_value)  # type: ignore[arg-type]


def _split_query_tokens(text: str) -> list[str]:
    """Split on whitespace; respect simple double-quoted phrases."""
    tokens: list[str] = []
    current: list[str] = []
    in_quote = False
    for ch in text:
        if ch == '"':
            in_quote = not in_quote
            continue
        if ch.isspace() and not in_quote:
            if current:
                tokens.append("".join(current))
                current = []
            continue
        current.append(ch)
    if current:
        tokens.append("".join(current))
    return tokens


def parse_query(text: str) -> ParsedQuery:
    """
    Parse a search box query.

    Supported tokens (case-insensitive keys):
    ``ext:stl``, ``type:3d``, ``folder:starwars``, ``name:helmet``, ``tag:print-ready``,
    ``size>100mb``, ``size<2gb``, or ``size:>100mb``.

    Unknown ``key:value`` forms fall back to plain-text search on the full input.
    """
    stripped = text.strip()
    if not stripped:
        return ParsedQuery()

    tokens = _split_query_tokens(stripped)
    plain_terms: list[str] = []
    extension: str | None = None
    asset_type: str | None = None
    folder_contains: str | None = None
    name_contains: str | None = None
    size_predicate: SizePredicate | None = None
    faces_predicate: IntPredicate | None = None
    watertight_required: bool | None = None
    archive_members_predicate: IntPredicate | None = None
    tag_contains: str | None = None
    saw_structured = False

    for token in tokens:
        size_direct = parse_size_token(token)
        if size_direct is not None:
            size_predicate = size_direct
            saw_structured = True
            continue
        int_direct = parse_int_predicate_token(token)
        if int_direct is not None:
            if int_direct.field == "faces":
                faces_predicate = int_direct
            else:
                archive_members_predicate = int_direct
            saw_structured = True
            continue
        if ":" not in token:
            plain_terms.append(token.lower())
            continue
        key, _, value = token.partition(":")
        key_lower = key.lower().strip()
        value = value.strip()
        if key_lower not in _KNOWN_PREFIXES:
            return ParsedQuery.from_plain_text(stripped)
        saw_structured = True
        if key_lower == "ext":
            extension = value.lstrip(".").lower()
        elif key_lower == "type":
            asset_type = value.lower()
        elif key_lower == "folder":
            folder_contains = value.lower()
        elif key_lower == "name":
            name_contains = value.lower()
        elif key_lower == "tag":
            tag_contains = normalize_tag_token(value)
            if not tag_contains:
                return ParsedQuery.from_plain_text(stripped)
        elif key_lower == "size":
            size_predicate = parse_size_token(value if value else token[len(key) :])
            if size_predicate is None and value:
                size_predicate = parse_size_token(token)
            if size_predicate is None:
                return ParsedQuery.from_plain_text(stripped)
        elif key_lower == "faces":
            tail = value if value else ""
            if tail and tail[0] not in (">", "<"):
                tail = f">{tail}"
            faces_predicate = parse_int_predicate_token(f"faces{tail}")
            if faces_predicate is None:
                return ParsedQuery.from_plain_text(stripped)
        elif key_lower == "watertight":
            val = value.lower()
            if val in ("true", "yes", "1"):
                watertight_required = True
            elif val in ("false", "no", "0"):
                watertight_required = False
            else:
                return ParsedQuery.from_plain_text(stripped)
        elif key_lower == "archive_members":
            tail = value if value else ""
            if tail and tail[0] not in (">", "<"):
                tail = f">{tail}"
            archive_members_predicate = parse_int_predicate_token(f"archive_members{tail}")
            if archive_members_predicate is None:
                return ParsedQuery.from_plain_text(stripped)

    if not saw_structured and plain_terms and not any(
        (
            extension,
            asset_type,
            folder_contains,
            name_contains,
            tag_contains,
            size_predicate,
            faces_predicate,
            watertight_required,
            archive_members_predicate,
        )
    ):
        if len(plain_terms) == 1:
            return ParsedQuery(plain_fallback=plain_terms[0])
        return ParsedQuery(plain_terms=tuple(plain_terms))

    return ParsedQuery(
        plain_terms=tuple(plain_terms),
        extension=extension,
        asset_type=asset_type,
        folder_contains=folder_contains,
        name_contains=name_contains,
        size_predicate=size_predicate,
        faces_predicate=faces_predicate,
        watertight_required=watertight_required,
        archive_members_predicate=archive_members_predicate,
        tag_contains=tag_contains,
    )


def normalize_tag_token(value: str) -> str:
    """Normalize ``tag:`` query value to canonical lowercase tag name."""
    from meshcorral.services.tagging.tag_validation import normalize_tag

    try:
        return normalize_tag(value)
    except ValueError:
        return ""
