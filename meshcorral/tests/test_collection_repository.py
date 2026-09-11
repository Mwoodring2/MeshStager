"""Persistent Collections storage, integrity, and atomic batch behavior."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from meshcorral.services.collections.collection_repository import CollectionRepository
from meshcorral.services.tagging.tag_repository import TagRepository


class TestCollectionRepository(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "collections.sqlite"
        self.repo = CollectionRepository(self.db)
        self.addCleanup(lambda: self.repo.close())
        self.path = Path(self.temp.name) / "mesh.stl"

    def test_idempotent_schema_creation(self):
        self.repo.create_collection("Ready")
        other = CollectionRepository(self.db)
        try:
            self.assertEqual(len(other.list_collections()), 1)
            self.assertEqual(other._conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        finally:
            other.close()

    def test_create_has_identity_and_timestamps(self):
        c = self.repo.create_collection(" Ready ")
        self.assertEqual(c.name, "Ready")
        self.assertGreater(c.collection_id, 0)
        self.assertTrue(c.created_at)
        self.assertEqual(c.created_at, c.modified_at)

    def test_case_insensitive_duplicates(self):
        self.repo.create_collection("Print Ready")
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.create_collection(" PRINT READY ")

    def test_unicode_duplicates(self):
        self.repo.create_collection("Straße")
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.create_collection("STRASSE")

    def test_rename_preserves_id_and_members(self):
        c = self.repo.create_collection("Old")
        self.repo.change_members(c.collection_id, [self.path], add=True)
        renamed = self.repo.rename_collection(c.collection_id, "New")
        self.assertEqual(renamed.collection_id, c.collection_id)
        self.assertEqual(renamed.created_at, c.created_at)
        self.assertTrue(self.repo.is_member(c.collection_id, self.path))
        self.assertGreater(renamed.modified_at, c.modified_at)

    def test_duplicate_rename_rolls_back(self):
        c = self.repo.create_collection("One")
        self.repo.create_collection("Two")
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.rename_collection(c.collection_id, "two")
        self.assertEqual(self.repo.get_collection(c.collection_id).name, "One")

    def test_delete_only_removes_own_memberships(self):
        self.path.write_bytes(b"asset content")
        a = self.repo.create_collection("A")
        b = self.repo.create_collection("B")
        for c in (a, b):
            self.repo.change_members(c.collection_id, [self.path], add=True)
        self.assertTrue(self.repo.delete_collection(a.collection_id))
        self.assertEqual(self.repo.get_members(a.collection_id), frozenset())
        self.assertTrue(self.repo.is_member(b.collection_id, self.path))
        self.assertEqual(self.path.read_bytes(), b"asset content")

    def test_reopen_and_missing_path_persistence(self):
        c = self.repo.create_collection("Offline")
        self.repo.change_members(c.collection_id, [self.path], add=True)
        self.repo.close()
        self.repo = CollectionRepository(self.db)
        self.assertTrue(self.repo.is_member(c.collection_id, self.path))
        self.assertFalse(self.path.exists())

    def test_membership_idempotency(self):
        c = self.repo.create_collection("C")
        self.assertEqual(self.repo.change_members(c.collection_id, [self.path, self.path], add=True), 1)
        self.assertEqual(self.repo.change_members(c.collection_id, [self.path], add=True), 0)
        self.assertEqual(self.repo.change_members(c.collection_id, [self.path], add=False), 1)
        self.assertEqual(self.repo.change_members(c.collection_id, [self.path], add=False), 0)

    def test_asset_in_multiple_collections(self):
        for name in ("Zulu", "alpha"):
            c = self.repo.create_collection(name)
            self.repo.change_members(c.collection_id, [self.path], add=True)
        self.assertEqual([c.name for c in self.repo.get_collections_for_asset(self.path)], ["alpha", "Zulu"])

    def test_canonical_path_matches_tags(self):
        c = self.repo.create_collection("Paths")
        path = Path(self.temp.name) / "folder" / ".." / "mesh.stl"
        self.repo.change_members(c.collection_id, [path], add=True)
        self.assertEqual(self.repo.get_members(c.collection_id), frozenset([TagRepository.normalize_asset_path(path)]))
        self.assertTrue(self.repo.is_member(c.collection_id, self.path))

    def test_large_batch_counts_and_single_transaction(self):
        c = self.repo.create_collection("Batch")
        paths = [Path(self.temp.name) / f"{i}.stl" for i in range(1200)]
        statements = []
        self.repo._conn.set_trace_callback(statements.append)
        self.assertEqual(self.repo.change_members(c.collection_id, paths, add=True), 1200)
        self.assertEqual(sum(s.startswith("BEGIN") for s in statements), 1)
        self.assertEqual(self.repo.get_collection(c.collection_id).member_count, 1200)
        self.assertEqual(self.repo.change_members(c.collection_id, paths[:800], add=False), 800)
        self.assertEqual(self.repo.list_collections()[0].member_count, 400)

    def test_unknown_collection_cannot_receive_members(self):
        with self.assertRaises(ValueError):
            self.repo.change_members(123, [self.path], add=True)
        self.assertEqual(self.repo.membership_rows(), [])

    def test_failed_batch_rolls_back_all_rows(self):
        c = self.repo.create_collection("Atomic")
        self.repo._conn.executescript("""
            CREATE TRIGGER reject_members BEFORE INSERT ON collection_members
            WHEN (SELECT COUNT(*) FROM collection_members) > 0
            BEGIN SELECT RAISE(ABORT, 'test failure'); END;
        """)
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.change_members(c.collection_id, [self.path, self.path.with_name("b.stl")], add=True)
        self.assertEqual(self.repo.get_collection(c.collection_id).member_count, 0)

    def test_deleted_ids_are_not_reused(self):
        c = self.repo.create_collection("First")
        self.repo.delete_collection(c.collection_id)
        self.assertNotEqual(self.repo.create_collection("Next").collection_id, c.collection_id)

    def test_sql_like_names_are_literal(self):
        name = "Robert'); DROP TABLE collections;--"
        c = self.repo.create_collection(name)
        self.assertEqual(self.repo.get_collection(c.collection_id).name, name)
