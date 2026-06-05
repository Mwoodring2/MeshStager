"""Tests for Prime v0.7 background stat enrichment."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from meshcorral.app.bridge.thumb_index import _norm_path_key
from meshcorral.models.file_record import FileRecord
from meshcorral.services.metadata_enrichment import (
    MetadataUpdate,
    iter_metadata_batches,
    stat_metadata_for,
)


def _lightweight(p: Path) -> FileRecord:
    return FileRecord(
        path=p,
        name=p.name,
        extension=p.suffix.lower(),
        parent_folder=p.parent.name,
    )


class TestStatMetadataFor(unittest.TestCase):
    def test_returns_size_and_mtime_for_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "file.bin"
            p.write_bytes(b"\x01" * 128)
            size, mtime = stat_metadata_for(p)
            self.assertEqual(size, 128)
            self.assertIsNotNone(mtime)

    def test_returns_none_when_missing(self) -> None:
        size, mtime = stat_metadata_for(Path("Z:/does/not/exist/file.bin"))
        self.assertIsNone(size)
        self.assertIsNone(mtime)


class TestIterMetadataBatches(unittest.TestCase):
    def test_emits_chunked_updates(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            paths = [Path(td) / f"f{i}.png" for i in range(5)]
            for p in paths:
                p.write_bytes(b"x")
            entries = [(_norm_path_key(p), p) for p in paths]
            batches = list(
                iter_metadata_batches(entries, batch_size=2, batch_pause_s=0.0)
            )
        self.assertEqual(len(batches), 3)
        all_updates = [u for batch in batches for u in batch]
        self.assertEqual(len(all_updates), 5)
        for update in all_updates:
            self.assertIsInstance(update, MetadataUpdate)
            self.assertEqual(update.size_bytes, 1)

    def test_respects_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            paths = [Path(td) / f"x{i}.png" for i in range(10)]
            for p in paths:
                p.write_bytes(b"x")
            entries = [(_norm_path_key(p), p) for p in paths]
            seen = 0

            def _is_cancelled() -> bool:
                nonlocal seen
                seen += 1
                return seen > 1

            batches = list(
                iter_metadata_batches(
                    entries,
                    batch_size=3,
                    batch_pause_s=0.0,
                    is_cancelled=_is_cancelled,
                )
            )
        flat = [u for batch in batches for u in batch]
        self.assertLess(len(flat), len(entries))


class TestFileRecordOptionalMetadata(unittest.TestCase):
    def test_lightweight_default_unenriched(self) -> None:
        rec = _lightweight(Path("C:/a/b.png"))
        self.assertFalse(rec.is_metadata_enriched())

    def test_with_metadata_returns_new_record(self) -> None:
        rec = _lightweight(Path("C:/a/b.png"))
        enriched = rec.with_metadata(size_bytes=100, modified_time=1.0)
        self.assertIsNot(rec, enriched)
        self.assertEqual(enriched.size_bytes, 100)
        self.assertEqual(enriched.modified_time, 1.0)
        self.assertTrue(enriched.is_metadata_enriched())


if __name__ == "__main__":
    unittest.main()
