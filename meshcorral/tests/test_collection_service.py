"""Collection validation, batching, and safe failure behavior."""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from meshcorral.services.collections.collection_repository import CollectionRepository
from meshcorral.services.collections.collection_service import CollectionService, CollectionError


class TestCollectionService(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = CollectionRepository(Path(tmp.name) / "collections.sqlite")
        self.service = CollectionService(self.repo)
        self.addCleanup(self.service.close)
        self.paths = [Path(tmp.name) / "a.stl", Path(tmp.name) / "b.stl"]

    def test_trim_and_lookup(self):
        c = self.service.create_collection("  Print Ready  ")
        self.assertEqual(self.service.get_collection(c.collection_id).name, "Print Ready")

    def test_invalid_names(self):
        for name in ("", " \t ", "x" * 121, "a\nb", "a\x00b", None):
            with self.subTest(name=name), self.assertRaises(CollectionError):
                self.service.create_collection(name)
        self.assertEqual(self.service.list_collections(), [])

    def test_maximum_length(self):
        self.assertEqual(len(self.service.create_collection("x" * 120).name), 120)

    def test_duplicate_has_friendly_message(self):
        self.service.create_collection("Same")
        with self.assertRaisesRegex(CollectionError, "already exists"):
            self.service.create_collection("same")

    def test_bulk_add_remove_idempotent(self):
        c = self.service.create_collection("Batch")
        self.assertEqual(self.service.add_assets(c.collection_id, self.paths), 2)
        self.assertEqual(self.service.add_assets(c.collection_id, self.paths), 0)
        self.assertEqual(self.service.remove_assets(c.collection_id, self.paths), 2)
        self.assertEqual(self.service.remove_assets(c.collection_id, self.paths), 0)

    def test_snapshot_is_immutable_and_stable(self):
        c = self.service.create_collection("Snapshot")
        self.service.add_assets(c.collection_id, self.paths)
        snapshot = self.service.membership_snapshot()
        self.service.remove_assets(c.collection_id, self.paths)
        self.assertEqual(len(snapshot), 2)
        with self.assertRaises(TypeError):
            snapshot["new"] = frozenset()
        self.assertEqual(len(self.service.membership_snapshot()), 0)

    def test_rename_preserves_asset_lookup(self):
        c = self.service.create_collection("Old")
        self.service.add_assets(c.collection_id, self.paths)
        self.service.rename_collection(c.collection_id, "New")
        self.assertEqual(self.service.get_collections_for_asset(self.paths[0])[0].name, "New")

    def test_storage_failure_is_safe(self):
        with patch.object(self.repo, "list_collections", side_effect=sqlite3.OperationalError("private database detail")):
            with self.assertLogs(level="WARNING"), self.assertRaises(CollectionError) as caught:
                self.service.list_collections()
        self.assertNotIn("private database detail", str(caught.exception))

    def test_close_is_idempotent(self):
        self.service.close()
        self.service.close()
