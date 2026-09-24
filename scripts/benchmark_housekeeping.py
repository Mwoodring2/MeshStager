"""Synthetic cheap pass plus a small real-file candidate-hashing benchmark."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import tempfile
import time
import tracemalloc
from meshcorral.models.file_record import FileRecord
from meshcorral.services.housekeeping.analyzer import analyze_catalog

def main():
    output = []
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for count in (10000, 50000, 100000):
            rows = []
            for i in range(count):
                name = f"asset_{i}" + ("_copy" if i % 10 == 0 else "") + ".glb"
                rows.append(FileRecord(root / name, name, ".glb", root.name, i + 1000, 1.0))
            tracemalloc.start()
            started = time.perf_counter()
            findings, stats = analyze_catalog(rows, root, inspect_files=False)
            elapsed = time.perf_counter() - started
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            result = dict(assets=count, seconds=round(elapsed, 4), peak_mib=round(peak / 1024**2, 3), findings=len(findings), candidates=stats.size_candidates, hashed=stats.hashed_assets)
            output.append(result)
            print(json.dumps(result), flush=True)
        rows = [FileRecord(root / f"unique{i}.glb", f"unique{i}.glb", ".glb", root.name, i + 1000, 1.0) for i in range(994)]
        for i in range(6):
            p = root / f"candidate{i}.glb"
            p.write_bytes(bytes([i // 2]) * 128)
            rows.append(FileRecord.from_path(p))
        started = time.perf_counter()
        findings, stats = analyze_catalog(rows, root)
        result = dict(assets=len(rows), candidates=stats.size_candidates, hashed=stats.hashed_assets, hashed_bytes=stats.hashed_bytes, seconds=round(time.perf_counter() - started, 4), exact_findings=sum(f.kind == "exact_duplicate" for f in findings))
        output.append(result)
        print(json.dumps(result), flush=True)
    return output

if __name__ == "__main__":
    main()
