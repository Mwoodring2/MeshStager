"""Tests for :mod:`meshcorral.services.favorites.favorite_repository`."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from meshcorral.services.favorites.favorite_repository import FavoriteRepository


class TestFavoriteRepository(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "favorites.sqlite"
        self._repo = FavoriteRepository(db)

    def tearDown(self) -> None:
        self._repo.close()
        self._tmp.cleanup()

    def test_set_and_query(self) -> None:
        path = Path(self._tmp.name) / "hero.stl"
        path.write_text("x", encoding="utf-8")
        self.assertFalse(self._repo.is_favorite(path))
        self._repo.set_favorite(path, favorite=True)
        self.assertTrue(self._repo.is_favorite(path))
        self._repo.set_favorite(path, favorite=False)
        self.assertFalse(self._repo.is_favorite(path))


if __name__ == "__main__":
    unittest.main()
