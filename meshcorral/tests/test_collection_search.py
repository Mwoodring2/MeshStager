"""Structured collection predicates compose with existing browser filters."""

import unittest
from pathlib import Path

from meshcorral.models.file_record import FileRecord
from meshcorral.services.favorites.favorite_filter import FAVORITE_FILTER_ONLY
from meshcorral.ui.search.async_filter_engine import compute_filtered_records
from meshcorral.ui.search.query_parser import parse_query
from meshcorral.ui.search.search_index import SearchIndex


class TestCollectionSearch(unittest.TestCase):
    def setUp(self):
        self.records = [FileRecord(path=Path(f"C:/lib/{name}.stl"), name=f"{name}.stl", extension=".stl", parent_folder="lib") for name in ("hero", "other")]

    def test_quoted_name_and_case(self):
        query = parse_query('collection:"Print Ready"')
        self.assertEqual(query.collection_name, "print ready")
        self.assertFalse(query.is_empty())

    def test_unquoted_name(self):
        self.assertEqual(parse_query("collection:PrintReady").collection_name, "printready")

    def test_empty_value_uses_existing_fallback(self):
        self.assertEqual(parse_query('collection:""').plain_fallback, 'collection:""')

    def test_collection_matching_is_exact(self):
        index = SearchIndex()
        provider = lambda r: ("Print Ready",)
        self.assertEqual(index.filter_records(self.records, parse_query("collection:Print"), collections_for=provider), [])
        self.assertEqual(index.filter_records(self.records, parse_query('collection:"PRINT READY"'), collections_for=provider), self.records)

    def test_composes_with_tag_text_extension_and_favorites(self):
        result = compute_filtered_records(
            self.records, query_text='hero tag:approved collection:"Print Ready" ext:stl',
            search_index=SearchIndex(), collections_for=lambda r: ("Print Ready",),
            user_tags_for=lambda r: ("approved",), favorite_filter=FAVORITE_FILTER_ONLY,
            is_favorite_for=lambda r: r == self.records[0],
            collection_filter=lambda r: True,
        )
        self.assertEqual(result, self.records[:1])

    def test_sidebar_and_search_intersect(self):
        result = compute_filtered_records(
            self.records, query_text="collection:A", search_index=SearchIndex(),
            collections_for=lambda r: ("A",) if r == self.records[0] else ("B",),
            collection_filter=lambda r: r == self.records[1],
        )
        self.assertEqual(result, [])

    def test_collection_names_do_not_change_plain_text_search(self):
        self.assertEqual(SearchIndex().filter_records(self.records, parse_query("Print Ready"), collections_for=lambda r: ("Print Ready",)), [])

    def test_unicode_casefold(self):
        self.assertEqual(SearchIndex().filter_records(self.records, parse_query("collection:STRASSE"), collections_for=lambda r: ("Straße",)), self.records)
