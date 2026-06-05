"""Match span helpers for table/gallery delegates (Prime v1.0 Sprint C)."""

from __future__ import annotations

from dataclasses import dataclass

from meshcorral.ui.search.query_parser import ParsedQuery


@dataclass(frozen=True, slots=True)
class MatchSpan:
    """Half-open interval ``[start, end)`` within a display field."""

    start: int
    end: int


def _plain_needles(parsed: ParsedQuery) -> list[str]:
    if parsed.plain_fallback:
        return [parsed.plain_fallback]
    needles: list[str] = list(parsed.plain_terms)
    if parsed.name_contains:
        needles.append(parsed.name_contains)
    if parsed.folder_contains:
        needles.append(parsed.folder_contains)
    if parsed.extension:
        needles.append(parsed.extension.lstrip("."))
    return needles


def highlight_spans_for_field(
    field_text: str,
    parsed: ParsedQuery,
    *,
    case_insensitive: bool = True,
) -> tuple[MatchSpan, ...]:
    """
    Return non-overlapping match spans in *field_text* for plain query needles.

    Structured-only predicates (e.g. ``size>100mb``) may yield no spans here;
    delegates can call this for name/path columns when plain terms apply.
    """
    if not field_text or parsed.is_empty():
        return ()

    haystack = field_text.lower() if case_insensitive else field_text
    spans: list[MatchSpan] = []
    for needle in _plain_needles(parsed):
        if not needle:
            continue
        n = needle.lower() if case_insensitive else needle
        start = 0
        while True:
            idx = haystack.find(n, start)
            if idx < 0:
                break
            spans.append(MatchSpan(idx, idx + len(n)))
            start = idx + len(n)

    if not spans:
        return ()

    spans.sort(key=lambda s: (s.start, s.end))
    merged: list[MatchSpan] = [spans[0]]
    for span in spans[1:]:
        last = merged[-1]
        if span.start <= last.end:
            merged[-1] = MatchSpan(last.start, max(last.end, span.end))
        else:
            merged.append(span)
    return tuple(merged)
