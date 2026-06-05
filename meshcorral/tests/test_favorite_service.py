"""Tests for :mod:`meshcorral.services.favorites.favorite_service`."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from meshcorral.models.file_record import FileRecord
from meshcorral.services.favorites.favorite_repository import FavoriteRepository
from meshcorral.services.favorites.favorite_service import FavoriteService
from meshcorral.services.search_service import filter_records
from meshcorral.services.favorites.favorite_filter import FAVORITE_FILTER_ONLY


class TestFavoriteService(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "favorites.sqlite"
        self._svc = FavoriteService(FavoriteRepository(db))
        self._path = Path(self._tmp.name) / "part.stl"
        self._path.write_text("x", encoding="utf-8")
        self._rec = FileRecord(
            path=self._path,
            name="part.stl",
            extension=".stl",
            parent_folder="lib",
        )

    def tearDown(self) -> None:
        self._svc.close()
        self._tmp.cleanup()

    def test_toggle(self) -> None:
        self.assertTrue(self._svc.toggle_favorite(self._path))
        self.assertTrue(self._svc.is_favorite(self._path))
        self.assertFalse(self._svc.toggle_favorite(self._path))

    def test_filter_favorites_only(self) -> None:
        other = FileRecord(
            path=Path(self._tmp.name) / "b.stl",
            name="b.stl",
            extension=".stl",
            parent_folder="lib",
        )
        self._svc.set_favorite(self._path, favorite=True)
        rows = filter_records(
            [self._rec, other],
            favorite_filter=FAVORITE_FILTER_ONLY,
            is_favorite_for=self._svc.is_favorite_record,
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].path, self._path)


if __name__ == "__main__":
    unittest.main()
