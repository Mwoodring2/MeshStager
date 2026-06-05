"""Prime v1.0 Sprint C — search polish tests."""

from __future__ import annotations

import unittest
from pathlib import Path
from meshcorral.models.file_record import FileRecord
from meshcorral.ui.search.async_filter_engine import (
    ASYNC_FILTER_THRESHOLD,
    AsyncFilterEngine,
    compute_filtered_records,
)
from meshcorral.ui.search.query_parser import parse_query
from meshcorral.ui.search.search_highlight import highlight_spans_for_field
from meshcorral.ui.search.search_index import SearchIndex


def _rec(
    name: str,
    ext: str,
    folder: str,
    *,
    size_bytes: int | None = 1,
    path: Path | None = None,
) -> FileRecord:
    p = path or Path(f"C:/lib/{folder}/{name}")
    return FileRecord(
        path=p,
        name=name,
        extension=ext,
        parent_folder=folder,
        size_bytes=size_bytes,
        modified_time=0.0,
    )


class TestQueryParser(unittest.TestCase):
    """Structured query parsing and plain-text fallback."""

    def test_plain_text_single_term(self) -> None:
        parsed = parse_query("vader helmet")
        self.assertEqual(parsed.plain_terms, ("vader", "helmet"))

    def test_ext_type_folder_name(self) -> None:
        parsed = parse_query("ext:stl type:3d folder:starwars name:helmet")
        self.assertEqual(parsed.extension, "stl")
        self.assertEqual(parsed.asset_type, "3d")
        self.assertEqual(parsed.folder_contains, "starwars")
        self.assertEqual(parsed.name_contains, "helmet")

    def test_tag_predicate(self) -> None:
        parsed = parse_query("tag:print-ready")
        self.assertEqual(parsed.tag_contains, "print-ready")

    def test_size_predicates(self) -> None:
        gt = parse_query("size>100mb")
        self.assertIsNotNone(gt.size_predicate)
        self.assertEqual(gt.size_predicate.op, ">")  # type: ignore[union-attr]
        self.assertEqual(gt.size_predicate.bytes_value, 100 * 1024 * 1024)  # type: ignore[union-attr]

        lt = parse_query("size<2gb")
        self.assertIsNotNone(lt.size_predicate)
        self.assertEqual(lt.size_predicate.op, "<")  # type: ignore[union-attr]

    def test_unknown_syntax_falls_back_to_plain(self) -> None:
        parsed = parse_query("foo:bar baz")
        self.assertEqual(parsed.plain_fallback, "foo:bar baz")

    def test_empty_query_is_empty(self) -> None:
        self.assertTrue(parse_query("").is_empty())
        self.assertTrue(parse_query("   ").is_empty())


class TestSearchIndex(unittest.TestCase):
    """Token index finds rows across fields."""

    def test_token_index_finds_by_name_and_folder(self) -> None:
        rows = [
            _rec("vader_helmet.stl", ".stl", "starwars"),
            _rec("other.obj", ".obj", "misc"),
        ]
        index = SearchIndex()
        index.rebuild(rows)
        parsed = parse_query("helmet")
        out = index.filter_records(rows, parsed)
        self.assertEqual([r.name for r in out], ["vader_helmet.stl"])

        folder_parsed = parse_query("folder:star")
        out_folder = index.filter_records(rows, folder_parsed)
        self.assertEqual(len(out_folder), 1)
        self.assertEqual(out_folder[0].parent_folder, "starwars")

    def test_type_3d_matches_geometry(self) -> None:
        rows = [_rec("a.stl", ".stl", "A"), _rec("b.png", ".png", "A")]
        index = SearchIndex()
        out = index.filter_records(rows, parse_query("type:3d"))
        self.assertEqual([r.name for r in out], ["a.stl"])


class TestAsyncFilterEngine(unittest.TestCase):
    """Sync vs async paths and epoch cancellation."""

    def test_small_set_uses_sync_path(self) -> None:
        rows = [_rec(f"f{i}.stl", ".stl", "A") for i in range(10)]
        engine = AsyncFilterEngine()
        result = engine.request_filter(rows, {}, "stl")
        self.assertFalse(result.pending)
        self.assertEqual(len(result.records), 10)

    def test_large_set_marks_pending_with_query(self) -> None:
        rows = [_rec(f"f{i}.stl", ".stl", "A") for i in range(ASYNC_FILTER_THRESHOLD)]
        engine = AsyncFilterEngine()
        result = engine.request_filter(rows, {}, "ext:stl")
        self.assertTrue(result.pending)

    def test_large_set_sync_without_query(self) -> None:
        rows = [_rec(f"f{i}.stl", ".stl", "A") for i in range(ASYNC_FILTER_THRESHOLD)]
        engine = AsyncFilterEngine()
        result = engine.request_filter(rows, {}, "")
        self.assertFalse(result.pending)
        self.assertEqual(len(result.records), ASYNC_FILTER_THRESHOLD)

    def test_async_cancellation_bumps_epoch(self) -> None:
        """A newer request increments epoch so an older async pass is dropped."""
        engine = AsyncFilterEngine()
        rows = [_rec(f"f{i}.stl", ".stl", "A") for i in range(ASYNC_FILTER_THRESHOLD)]
        first = engine.request_filter(rows, {}, "zzz")
        self.assertTrue(first.pending)
        epoch_first = first.epoch
        second = engine.request_filter(rows, {}, "f0")
        self.assertGreater(second.epoch, epoch_first)
        self.assertEqual(engine.current_epoch(), second.epoch)

    def test_result_count_stable(self) -> None:
        rows = [
            _rec("alpha.stl", ".stl", "A"),
            _rec("beta.stl", ".stl", "A"),
            _rec("gamma.obj", ".obj", "A"),
        ]
        index = SearchIndex()
        first = compute_filtered_records(rows, query_text="alpha", search_index=index)
        second = compute_filtered_records(rows, query_text="alpha", search_index=index)
        self.assertEqual(len(first), len(second))
        self.assertEqual(len(first), 1)


class TestSearchHighlight(unittest.TestCase):
    """Match span helper for delegates."""

    def test_highlight_spans_name(self) -> None:
        parsed = parse_query("helmet")
        spans = highlight_spans_for_field("vader_helmet.stl", parsed)
        self.assertTrue(any(s.start <= 6 and s.end >= 12 for s in spans))


class TestComputeFilteredRecords(unittest.TestCase):
    """Combo filters plus query still respect extension combo."""

    def test_ext_query_with_combo(self) -> None:
        rows = [
            _rec("a.stl", ".stl", "A"),
            _rec("b.obj", ".obj", "A"),
        ]
        index = SearchIndex()
        out = compute_filtered_records(
            rows,
            query_text="ext:stl",
            search_index=index,
            extension_filter="All",
        )
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].extension, ".stl")


if __name__ == "__main__":
    unittest.main()
