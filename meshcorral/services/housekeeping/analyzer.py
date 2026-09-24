"""Catalog-driven, read-only analysis. No traversal, extraction, or mesh loading."""
from __future__ import annotations
from collections import defaultdict
from contextlib import closing
import hashlib
import os
from pathlib import Path, PurePosixPath
import shlex
import sqlite3
import stat
import time
from .models import (AnalysisStats, checkpoint, finding, stable_id, path_key,
                     LARGE_ASSET_BYTES, HASH_CHUNK_BYTES, TEXT_LIMIT_BYTES, POSSIBLE_SIZE_RATIO)
from .naming import naming_issue, normalized_stem


def safe_local_path(path, root):
    """Resolve only I/O candidates; reject links/junctions escaping the selected root."""
    path, root = Path(path), Path(root).resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(root) or path.is_symlink():
        raise OSError("Path is outside the source or is a symbolic link")
    # Refuse reparse-point aliases rather than treating the same asset as a copy.
    current = path
    while current != root and current != current.parent:
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise OSError("Linked asset path is excluded from housekeeping I/O")
        current = current.parent
    return resolved


def hash_candidate(record, root, canceled, stats):
    checkpoint(canceled)
    path = safe_local_path(record.path, root)
    if not stat.S_ISREG(path.stat().st_mode):
        raise OSError("Not a regular asset")
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise OSError("Not a regular asset")
        if record.size_bytes != before.st_size or (record.modified_time is not None and record.modified_time != before.st_mtime):
            raise OSError("Asset changed since catalog scan; rescan before analysis")
        digest = hashlib.sha256()
        consumed = 0
        while True:
            checkpoint(canceled)
            data = stream.read(HASH_CHUNK_BYTES)
            if not data:
                break
            consumed += len(data)
            if consumed > before.st_size:
                raise OSError("Asset grew while hashing")
            digest.update(data)
            stats.hashed_bytes += len(data)
        after = os.fstat(stream.fileno())
    current = path.stat()
    signature = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    if signature(before) != signature(after) or signature(before) != signature(current):
        raise OSError("Asset changed while hashing")
    stats.hashed_assets += 1
    return digest.hexdigest(), (before.st_dev, before.st_ino)


def read_text_prefix(path, root):
    safe = safe_local_path(path, root)
    with safe.open("rb") as stream:
        data = stream.read(TEXT_LIMIT_BYTES + 1)
    # Drop an incomplete trailing line instead of inventing a missing dependency.
    if len(data) > TEXT_LIMIT_BYTES:
        prefix = data[:TEXT_LIMIT_BYTES]
        data = prefix[:prefix.rfind(b"\n") + 1]
    if b"\0" in data:
        raise ValueError("Binary data in OBJ/MTL text")
    return data.decode("utf-8-sig", errors="replace").splitlines()


def reference_tokens(text):
    try:
        return [p.strip('"') for p in shlex.split(text, posix=False, comments=True)]
    except ValueError:
        return []


def local_reference(owner, text, root):
    if not text or "\0" in text or ":" in text or text.startswith(("/", "\\")):
        return None
    target = owner.parent / text.replace("\\", "/")
    return safe_local_path(target, root)


def companion_findings(record, root, canceled, stats):
    path = Path(record.path)
    results = []
    try:
        lines = read_text_prefix(path, root)
        mtls = []
        if path.suffix.lower() == ".obj":
            for line in lines:
                checkpoint(canceled)
                parts = line.strip().split(None, 1)
                if len(parts) != 2 or parts[0].lower() != "mtllib":
                    continue
                names = reference_tokens(parts[1])
                if not names or not all(name.lower().endswith(".mtl") for name in names):
                    continue  # ambiguous unquoted names are not evidence of absence
                for name in names:
                    target = local_reference(path, name, root)
                    if target is None:
                        continue
                    try:
                        target.stat()
                        mtls.append(target)
                    except FileNotFoundError:
                        results.append(finding(record, "missing_companion", {"rule": "mtl:" + name, "message": "Referenced MTL is absent", "reference": name}))
        else:
            mtls = [path]
        for mtl in dict.fromkeys(mtls):
            for line in read_text_prefix(mtl, root):
                checkpoint(canceled)
                parts = line.strip().split(None, 1)
                if len(parts) != 2 or parts[0].lower() not in {"map_kd", "map_ka", "map_ks", "map_d", "map_bump", "bump", "disp", "decal", "norm"}:
                    continue
                tokens = reference_tokens(parts[1])
                # Simple local references only; option-bearing statements are ambiguous.
                if len(tokens) != 1 or tokens[0].startswith("-"):
                    continue
                target = local_reference(mtl, tokens[0], root)
                if target is None:
                    continue
                try:
                    target.stat()
                except FileNotFoundError:
                    results.append(finding(record, "missing_companion", {"rule": "texture:" + str(mtl) + ":" + tokens[0], "message": "Referenced local texture is absent", "reference": tokens[0], "mtl": str(mtl)}))
    except (OSError, ValueError) as exc:
        stats.warn(f"Companion check skipped for {path.name}: {exc}")
    return results


def cached_archive_matches(records, root, db_path, canceled, stats):
    """Read existing manifests in one joined query; never open/extract archives."""
    if db_path is None or not Path(db_path).is_file():
        return []
    indexed = {path_key(r.path): r for r in records}
    results = {}
    try:
        uri = Path(db_path).resolve().as_uri() + "?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            rows = conn.execute("""SELECT m.archive_path,m.archive_size,m.archive_modified_time,e.member_path,e.member_size
                FROM archive_manifest_meta m JOIN archive_manifest_entries e ON e.archive_path=m.archive_path""")
            checked = {}
            for archive_s, size, mtime, member, member_size in rows:
                checkpoint(canceled)
                if archive_s not in checked:
                    try:
                        archive = safe_local_path(Path(archive_s), root)
                        sig = archive.stat()
                        checked[archive_s] = archive if (sig.st_size, sig.st_mtime) == (size, mtime) else None
                    except (OSError, ValueError):
                        checked[archive_s] = None
                archive = checked[archive_s]
                if archive is None or not isinstance(member, str):
                    continue
                logical = PurePosixPath(member.replace("\\", "/"))
                if logical.is_absolute() or ".." in logical.parts or ":" in member or "\0" in member:
                    continue
                for target in (archive.parent / str(logical), archive.parent / archive.stem / str(logical)):
                    rec = indexed.get(path_key(target))
                    if rec is None or rec.size_bytes != member_size:
                        continue
                    group = stable_id("archive", path_key(archive))
                    details = {"rule": "archive:" + path_key(archive), "message": "Cached archive member matches extracted path and size", "archive": str(archive), "member": member, "evidence": "path/name/size; not a content hash"}
                    f = finding(rec, "archive_extracted", details, group=group)
                    results[f.finding_id] = f
                    archive_rec = indexed.get(path_key(archive))
                    if archive_rec is not None:
                        f = finding(archive_rec, "archive_extracted", details, group=group)
                        results[f.finding_id] = f
    except (sqlite3.Error, OSError, ValueError, TypeError) as exc:
        stats.warn(f"Archive cache unavailable: {exc}")
    return list(results.values())


def analyze_catalog(records, root, *, canceled=lambda: False, progress=lambda stage: None,
                    inspect_files=True, archive_db=None):
    started = time.perf_counter()
    records = list({path_key(r.path): r for r in records}.values())
    stats = AnalysisStats(total_assets=len(records))
    results, sizes, names = [], defaultdict(list), defaultdict(list)
    checkpoint(canceled)
    if inspect_files and not Path(root).is_dir():
        raise OSError("Source is unavailable; previous housekeeping findings retained")
    progress("Checking catalog metadata…")
    for record in records:
        checkpoint(canceled)
        size = record.size_bytes
        issue = naming_issue(record.path.stem)
        if issue:
            results.append(finding(record, "naming", {"rule": "name_suffix", "message": issue}))
        if size == 0:
            results.append(finding(record, "zero_byte", {"message": "Supported asset contains zero bytes"}))
        if size is not None and size >= LARGE_ASSET_BYTES:
            results.append(finding(record, "large", {"message": "Large asset (informational)", "bytes": size, "threshold": LARGE_ASSET_BYTES}))
        if size is not None and size > 0:
            sizes[size].append(record)
            names[(record.extension.lower(), normalized_stem(record.path.stem))].append(record)
    candidates = [group for group in sizes.values() if len(group) > 1]
    stats.size_candidates = sum(map(len, candidates))
    exact_paths = set()
    if inspect_files:
        progress("Hashing same-size duplicate candidates…")
        for group in candidates:
            hashes = defaultdict(list)
            seen_files = set()
            for record in group:
                checkpoint(canceled)
                try:
                    digest, physical = hash_candidate(record, root, canceled, stats)
                    if physical not in seen_files:
                        hashes[digest].append(record)
                        seen_files.add(physical)
                except (OSError, ValueError) as exc:
                    stats.warn(f"Hash skipped for {record.name}: {exc}")
            for digest, matches in hashes.items():
                if len(matches) < 2:
                    continue
                group_id = stable_id("sha256", matches[0].size_bytes, digest)
                for record in matches:
                    exact_paths.add(path_key(record.path))
                    results.append(finding(record, "exact_duplicate", {"message": "Byte-identical SHA-256 duplicate", "sha256": digest, "matching_files": len(matches)}, group=group_id, identity=digest))
    progress("Checking possible duplicates…")
    for (extension, stem), group in names.items():
        checkpoint(canceled)
        group = [r for r in group if path_key(r.path) not in exact_paths]
        group.sort(key=lambda r: r.size_bytes)
        # Adjacent size windows are linear after sorting, avoiding pairwise comparisons.
        clusters = []
        for record in group:
            if not clusters or record.size_bytes > clusters[-1][0].size_bytes * (1 + POSSIBLE_SIZE_RATIO):
                clusters.append([])
            clusters[-1].append(record)
        for cluster in clusters:
            if len(cluster) < 2 or not any(normalized_stem(r.path.stem) != r.path.stem.casefold().strip() for r in cluster):
                continue
            group_id = stable_id("possible", extension, stem, cluster[0].size_bytes)
            for record in cluster:
                results.append(finding(record, "possible_duplicate", {"message": "Copy/version name and size within 1%; content identity unproven", "matching_files": len(cluster)}, group=group_id))
    if inspect_files:
        progress("Checking bounded companion references…")
        for record in records:
            checkpoint(canceled)
            if record.extension.lower() in (".obj", ".mtl"):
                results.extend(companion_findings(record, root, canceled, stats))
            elif record.extension.lower() == ".stl" and record.size_bytes is not None and 0 < record.size_bytes < 84:
                try:
                    with safe_local_path(record.path, root).open("rb") as stream:
                        header = stream.read(84)
                    if len(header) < 84 and b"\0" in header:
                        results.append(finding(record, "broken", {"message": "Truncated binary STL: shorter than its 84-byte header"}))
                except (OSError, ValueError) as exc:
                    stats.warn(f"Header check skipped for {record.name}: {exc}")
        progress("Checking cached archive manifests…")
        results.extend(cached_archive_matches(records, root, archive_db, canceled, stats))
    checkpoint(canceled)
    stats.elapsed_seconds = time.perf_counter() - started
    return list({f.finding_id: f for f in results}.values()), stats
