"""Prime v1.0 search polish: query parsing, token index, async filtering."""

from meshcorral.ui.search.async_filter_engine import (
    ASYNC_FILTER_THRESHOLD,
    AsyncFilterEngine,
    FilterRunResult,
    compute_filtered_records,
)
from meshcorral.ui.search.query_parser import ParsedQuery, parse_query
from meshcorral.ui.search.search_highlight import MatchSpan, highlight_spans_for_field
from meshcorral.ui.search.search_index import SearchIndex

__all__ = [
    "ASYNC_FILTER_THRESHOLD",
    "AsyncFilterEngine",
    "FilterRunResult",
    "MatchSpan",
    "ParsedQuery",
    "SearchIndex",
    "compute_filtered_records",
    "highlight_spans_for_field",
    "parse_query",
]
