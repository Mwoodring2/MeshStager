"""Search integration for user tags (Tier 2.1)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from meshcorral.models.file_record import FileRecord
from meshcorral.services.tagging.tag_repository import TagRepository
from meshcorral.services.tagging.tag_service import TagService
from meshcorral.ui.search.query_parser import parse_query
from meshcorral.ui.search.search_index import SearchIndex


class TestTagSearch(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "tags.sqlite"
        self._svc = TagService(TagRepository(db))
        self._path = Path(self._tmp.name) / "mesh.stl"
        self._other = Path(self._tmp.name) / "other.stl"
        self._path.write_text("x", encoding="utf-8")
        self._other.write_text("y", encoding="utf-8")
        self._svc.add_tag(self._path, "helmet")

    def tearDown(self) -> None:
        self._svc.close()
        self._tmp.cleanup()

    def test_tag_query_parser(self) -> None:
        parsed = parse_query("tag:helmet")
        self.assertEqual(parsed.tag_contains, "helmet")

    def test_filter_by_tag(self) -> None:
        rec_a = FileRecord(
            path=self._path,
            name="mesh.stl",
            extension=".stl",
            parent_folder="lib",
        )
        rec_b = FileRecord(
            path=self._other,
            name="other.stl",
            extension=".stl",
            parent_folder="lib",
        )
        index = SearchIndex()
        parsed = parse_query("tag:helmet")
        filtered = index.filter_records(
            [rec_a, rec_b],
            parsed,
            user_tags_for=lambda r: self._svc.user_tags_for_record(r.path),
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].path, self._path)

    def test_plain_and_tag_together(self) -> None:
        rec_a = FileRecord(
            path=self._path,
            name="hero_helmet.stl",
            extension=".stl",
            parent_folder="props",
        )
        rec_b = FileRecord(
            path=self._other,
            name="other.stl",
            extension=".stl",
            parent_folder="props",
        )
        index = SearchIndex()
        parsed = parse_query("helmet tag:helmet")
        filtered = index.filter_records(
            [rec_a, rec_b],
            parsed,
            user_tags_for=lambda r: self._svc.user_tags_for_record(r.path),
        )
        self.assertEqual(len(filtered), 1)


if __name__ == "__main__":
    unittest.main()
