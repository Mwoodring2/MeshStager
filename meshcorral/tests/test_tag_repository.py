"""Tests for :mod:`meshcorral.services.tagging.tag_repository`."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from meshcorral.services.tagging.tag_repository import TagRepository


class TestTagRepository(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "tags.sqlite"
        self._repo = TagRepository(db)

    def tearDown(self) -> None:
        self._repo.close()
        self._tmp.cleanup()

    def test_add_get_remove(self) -> None:
        path = Path(self._tmp.name) / "part.stl"
        path.write_text("x", encoding="utf-8")
        self.assertTrue(self._repo.add_tag(path, "helmet"))
        self.assertFalse(self._repo.add_tag(path, "helmet"))
        self.assertEqual(self._repo.get_tags(path), ["helmet"])
        self.assertTrue(self._repo.remove_tag(path, "helmet"))
        self.assertEqual(self._repo.get_tags(path), [])

    def test_find_asset_paths_by_tag(self) -> None:
        p1 = Path(self._tmp.name) / "one.stl"
        p2 = Path(self._tmp.name) / "two.stl"
        p1.write_text("a", encoding="utf-8")
        p2.write_text("b", encoding="utf-8")
        self._repo.add_tag(p1, "approved")
        keys = self._repo.find_asset_paths_by_tag("approved")
        self.assertIn(self._repo.normalize_asset_path(p1), keys)
        self.assertNotIn(self._repo.normalize_asset_path(p2), keys)


if __name__ == "__main__":
    unittest.main()
