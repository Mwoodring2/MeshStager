"""Tests for Prime Performance v0.8 metadata and archive manifest caches."""

from __future__ import annotations

import tempfile
import time
import unittest
import uuid
import zipfile
from pathlib import Path

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.models.file_record import FileRecord
from meshcorral.services.archive_manifest_cache import ArchiveManifestCache
from meshcorral.services.metadata_cache import MetadataCache
from meshcorral.services.scanner import iter_scan_file_records


class TestMetadataCache(unittest.TestCase):
    def setUp(self) -> None:
        self._td = tempfile.TemporaryDirectory()
        self._db = Path(self._td.name) / "meta.sqlite"
        self._cache = MetadataCache(self._db)

    def tearDown(self) -> None:
        self._cache.close()
        self._td.cleanup()

    def test_upsert_and_get(self) -> None:
        p = Path(self._td.name) / "a.obj"
        p.write_bytes(b"x")
        self._cache.upsert(
            path=p,
            ext=".obj",
            size_bytes=1,
            modified_time=100.0,
            source_root=str(self._td.name),
            enriched=True,
        )
        row = self._cache.get(p)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row.size_bytes, 1)
        self.assertEqual(row.modified_time, 100.0)

    def test_get_many(self) -> None:
        p1 = Path(self._td.name) / "one.obj"
        p2 = Path(self._td.name) / "two.obj"
        p1.write_bytes(b"a")
        p2.write_bytes(b"b")
        self._cache.upsert(path=p1, ext=".obj", size_bytes=1, modified_time=1.0)
        self._cache.upsert(path=p2, ext=".obj", size_bytes=2, modified_time=2.0)
        found = self._cache.get_many([p1, p2])
        self.assertEqual(len(found), 2)
        self.assertIn(_norm_path_key(p1), found)

    def test_mark_missing(self) -> None:
        p = Path(self._td.name) / "gone.obj"
        self._cache.upsert(path=p, ext=".obj", size_bytes=1, modified_time=1.0)
        self._cache.mark_missing(p)
        row = self._cache.get(p)
        assert row is not None
        self.assertFalse(row.file_exists)

    def test_prune_older_than(self) -> None:
        p = Path(self._td.name) / "old.obj"
        p.write_bytes(b"x")
        self._cache.upsert(path=p, ext=".obj", size_bytes=1, modified_time=1.0)
        with self._cache._conn:  # noqa: SLF001
            self._cache._conn.execute(
                "UPDATE asset_metadata_cache SET last_seen = ?",
                (time.time() - 90 * 86400,),
            )
        removed = self._cache.prune_older_than(30.0)
        self.assertGreaterEqual(removed, 1)
        self.assertIsNone(self._cache.get(p))

    def test_count_for_source_root(self) -> None:
        root = str(self._td.name)
        p = Path(root) / "f.obj"
        p.write_bytes(b"x")
        self._cache.upsert(
            path=p, ext=".obj", size_bytes=1, modified_time=1.0, source_root=root
        )
        self.assertEqual(self._cache.count_for_source_root(root), 1)


class TestScannerCacheHydration(unittest.TestCase):
    def test_lightweight_scan_hydrates_from_cache(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = root / "mesh.obj"
            f.write_bytes(b"data")
            db = root / "cache.sqlite"
            cache = MetadataCache(db)
            cache.upsert(
                path=f,
                ext=".obj",
                size_bytes=4,
                modified_time=12345.0,
                source_root=str(root),
                enriched=True,
            )
            records = list(
                iter_scan_file_records(
                    root,
                    recursive=False,
                    allowed_extensions={".obj"},
                    lightweight=True,
                    metadata_cache=cache,
                    source_root=str(root),
                    network_optimistic=True,
                )
            )
            cache.close()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].size_bytes, 4)
            self.assertEqual(records[0].metadata_source, "cache")


class TestArchiveManifestCache(unittest.TestCase):
    def test_zip_manifest_reuse_when_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            zpath = Path(td) / "pack.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr("inner/a.txt", b"hello")
            db = Path(td) / "arch.sqlite"
            cache = ArchiveManifestCache(db)
            first = cache.ensure_indexed(zpath)
            assert first is not None
            self.assertFalse(first.reused_cache)
            self.assertTrue(first.rebuilt)
            second = cache.ensure_indexed(zpath)
            assert second is not None
            self.assertTrue(second.reused_cache)
            self.assertFalse(second.rebuilt)
            members = cache.list_members(zpath)
            cache.close()
            self.assertEqual(len(members), 1)
            self.assertEqual(members[0].member_path, "inner/a.txt")

    def test_zip_manifest_rebuild_when_modified(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            zpath = Path(td) / "pack.zip"
            with zipfile.ZipFile(zpath, "w") as zf:
                zf.writestr("a.txt", b"1")
            db = Path(td) / "arch.sqlite"
            cache = ArchiveManifestCache(db)
            cache.ensure_indexed(zpath)
            time.sleep(0.05)
            with zipfile.ZipFile(zpath, "a") as zf:
                zf.writestr("b.txt", b"2")
            result = cache.force_rebuild(zpath)
            cache.close()
            assert result is not None
            self.assertTrue(result.rebuilt)
            self.assertEqual(result.member_count, 2)


class TestEnrichmentCacheWrite(unittest.TestCase):
    def test_file_record_with_metadata_sets_source_stat(self) -> None:
        rec = FileRecord(
            path=Path("C:/x.obj"),
            name="x.obj",
            extension=".obj",
            parent_folder="",
            metadata_source="cache",
        )
        updated = rec.with_metadata(size_bytes=10, modified_time=1.0)
        self.assertEqual(updated.metadata_source, "stat")


if __name__ == "__main__":
    unittest.main()
