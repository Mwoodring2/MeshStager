"""Tests for :mod:`meshcorral.services.tagging.tag_service`."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from meshcorral.services.tagging.tag_repository import TagRepository
from meshcorral.services.tagging.tag_service import TagService
from meshcorral.services.tagging.tag_validation import normalize_tag, parse_tags_from_dialog


class TestTagValidation(unittest.TestCase):
    def test_normalize_tag(self) -> None:
        self.assertEqual(normalize_tag("  Print-Ready  "), "print-ready")

    def test_parse_dialog_lines(self) -> None:
        tags = parse_tags_from_dialog("helmet\napproved\nprint-ready")
        self.assertEqual(tags, ["helmet", "approved", "print-ready"])


class TestTagService(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        db = Path(self._tmp.name) / "tags.sqlite"
        self._svc = TagService(TagRepository(db))
        self._path = Path(self._tmp.name) / "mesh.stl"
        self._path.write_text("solid", encoding="utf-8")

    def tearDown(self) -> None:
        self._svc.close()
        self._tmp.cleanup()

    def test_add_get_remove(self) -> None:
        self._svc.add_tag(self._path, "helmet")
        self.assertEqual(self._svc.get_tags(self._path), ["helmet"])
        self.assertTrue(self._svc.remove_tag(self._path, "helmet"))
        self.assertEqual(self._svc.get_tags(self._path), [])

    def test_persistence_across_instances(self) -> None:
        self._svc.add_tag(self._path, "needs-review")
        db = self._svc.repository._db_path
        self._svc.close()
        reloaded = TagService(TagRepository(db))
        self.assertEqual(reloaded.get_tags(self._path), ["needs-review"])
        reloaded.close()

    def test_find_assets_by_tag(self) -> None:
        self._svc.add_tag(self._path, "mvp")
        paths = self._svc.find_assets_by_tag("mvp")
        self.assertEqual(len(paths), 1)


if __name__ == "__main__":
    unittest.main()
