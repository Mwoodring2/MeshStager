"""Synthetic SQLite -> FileRecord benchmark (no asset files created)."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import time
from meshcorral.models.file_record import FileRecord
from meshcorral.services.metadata_cache import MetadataCache

with tempfile.TemporaryDirectory() as td:
    root = Path(td)
    cache = MetadataCache(root / "metadata.sqlite")
    try:
        for count in (1000, 10000, 50000):
            records = [FileRecord(root / f"{i:06}.stl", f"{i:06}.stl", ".stl", root.name, 1000, 1.0) for i in range(count)]
            cache.complete_source_snapshot(root, True, {".stl"}, records)
            started = time.perf_counter()
            catalog = cache.get_records_for_source_root(root, True, {".stl"})
            elapsed = time.perf_counter() - started
            print(f"{len(catalog.records):,} rows: {elapsed * 1000:.3f} ms", flush=True)
    finally:
        cache.close()
