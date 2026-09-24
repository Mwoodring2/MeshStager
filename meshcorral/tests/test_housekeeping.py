"""Read-only analysis, storage, candidate hashing, and generation regressions."""
from dataclasses import replace
from contextlib import closing
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from meshcorral.models.file_record import FileRecord
from meshcorral.services.housekeeping.models import *
from meshcorral.services.housekeeping.repository import HousekeepingRepository
from meshcorral.services.housekeeping.service import HousekeepingService
from meshcorral.services.housekeeping.analyzer import analyze_catalog, safe_local_path
from meshcorral.services.housekeeping.naming import naming_issue, normalized_stem
from meshcorral.services.archive_manifest_cache import ArchiveManifestCache

class TestHousekeeping(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = HousekeepingRepository(self.root / "findings.sqlite")
        self.service = HousekeepingService(self.repo)

    def file(self, name, data=b"mesh"):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return FileRecord.from_path(p)

    def synthetic(self, name, size=100, mtime=1.0):
        p = self.root / name
        return FileRecord(p, p.name, p.suffix.lower(), p.parent.name, size, mtime)

    def analyze(self, records, **kwargs):
        return analyze_catalog(records, self.root, **kwargs)

    def test_schema_and_restart_persistence(self):
        rec = self.synthetic("a_copy.stl")
        snapshot, _ = self.service.analyze([rec], self.root, inspect_files=False)
        self.assertTrue(snapshot.generation)
        self.assertEqual(HousekeepingRepository(self.repo.db_path).load(self.root), snapshot)
        with closing(sqlite3.connect(self.repo.db_path)) as conn, conn:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 1)

    def test_completed_empty_generation_is_valid(self):
        self.repo.publish(self.root, [], 0)
        snapshot = self.repo.load(self.root)
        self.assertTrue(snapshot.generation)
        self.assertEqual(snapshot.findings, ())

    def test_canceled_publication_rolls_back_generation(self):
        f = finding(self.synthetic("a.stl"), "naming", {"message": "old"})
        self.repo.publish(self.root, [f], 1)
        old = self.repo.load(self.root)
        checks = iter([False, True])
        with self.assertRaises(AnalysisCanceled):
            self.repo.publish(self.root, [], 0, lambda: next(checks))
        self.assertEqual(self.repo.load(self.root), old)

    def test_canceled_analysis_retains_completed_results(self):
        self.service.analyze([self.synthetic("a_copy.stl")], self.root, inspect_files=False)
        old = self.repo.load(self.root)
        with self.assertRaises(AnalysisCanceled):
            self.service.analyze([], self.root, canceled=lambda: True)
        self.assertEqual(self.repo.load(self.root), old)

    def test_unavailable_root_retains_completed_results(self):
        missing = self.root / "offline"
        self.repo.publish(missing, [], 0)
        old = self.repo.load(missing)
        with self.assertRaises(OSError):
            self.service.analyze([], missing)
        self.assertEqual(self.repo.load(missing), old)

    def test_10k_batch_publication_and_load(self):
        records = [self.synthetic(f"asset_{i}_copy.stl", i + 100) for i in range(10000)]
        snapshot, stats = self.service.analyze(records, self.root, inspect_files=False)
        self.assertEqual(len(snapshot.findings), 10000)
        self.assertEqual(stats.hashed_assets, 0)
        self.assertEqual(stats.total_assets, 10000)

    def test_exact_content_group_and_stability(self):
        a, b = self.file("a.glb"), self.file("b.glb")
        first, stats = self.analyze([a, b])
        exact = [f for f in first if f.kind == "exact_duplicate"]
        self.assertEqual(len(exact), 2)
        self.assertEqual(len({f.group_id for f in exact}), 1)
        self.assertEqual(exact[0].details["sha256"], hashlib.sha256(b"mesh").hexdigest())
        second, _ = self.analyze([b, a])
        self.assertEqual({f.finding_id for f in first}, {f.finding_id for f in second})
        self.assertEqual(stats.hashed_assets, 2)

    def test_same_size_different_content_not_exact(self):
        findings, _ = self.analyze([self.file("a.glb", b"aaaa"), self.file("b.glb", b"bbbb")])
        self.assertFalse(any(f.kind == "exact_duplicate" for f in findings))

    def test_only_size_candidates_are_hashed(self):
        rows = [self.synthetic(f"unique{i}.glb", i + 1000) for i in range(100)]
        rows += [self.file("a.glb"), self.file("b.glb")]
        _, stats = self.analyze(rows)
        self.assertEqual((stats.total_assets, stats.size_candidates, stats.hashed_assets), (102, 2, 2))

    def test_chunked_hashing(self):
        records = [self.file("a.glb", b"123456789"), self.file("b.glb", b"123456789")]
        real = hashlib.sha256
        chunks = []
        class Digest:
            def __init__(self, initial=b""):
                self.value = real(initial)
            def update(self, value):
                chunks.append(len(value))
                self.value.update(value)
            def hexdigest(self):
                return self.value.hexdigest()
        with patch("meshcorral.services.housekeeping.analyzer.HASH_CHUNK_BYTES", 3), patch("meshcorral.services.housekeeping.analyzer.hashlib.sha256", Digest):
            self.analyze(records)
        self.assertEqual(chunks, [3] * 6)

    def test_cancel_between_hash_chunks(self):
        rows = [self.file("a.glb", b"x" * 20), self.file("b.glb", b"x" * 20)]
        count = 0
        def canceled():
            nonlocal count
            count += 1
            return count > 8
        with patch("meshcorral.services.housekeeping.analyzer.HASH_CHUNK_BYTES", 2):
            with self.assertRaises(AnalysisCanceled):
                self.analyze(rows, canceled=canceled)

    def test_changed_since_catalog_not_claimed_exact(self):
        a, b = self.file("a.glb"), self.file("b.glb")
        a.path.write_bytes(b"changed")
        findings, stats = self.analyze([a, b])
        self.assertFalse(any(f.kind == "exact_duplicate" for f in findings))
        self.assertEqual(stats.warning_count, 1)

    def test_change_during_hash_not_claimed_exact(self):
        a, b = self.file("a.glb", b"12345678"), self.file("b.glb", b"12345678")
        real = hashlib.sha256
        mutated = False
        class Digest:
            def __init__(self, initial=b""):
                self.value = real(initial)
            def update(self, value):
                nonlocal mutated
                self.value.update(value)
                if not mutated:
                    mutated = True
                    with a.path.open("ab") as stream:
                        stream.write(b"changed")
            def hexdigest(self):
                return self.value.hexdigest()
        with patch("meshcorral.services.housekeeping.analyzer.hashlib.sha256", Digest):
            findings, stats = self.analyze([a, b])
        self.assertFalse(any(f.kind == "exact_duplicate" for f in findings))
        self.assertGreater(stats.warning_count, 0)

    def test_missing_hash_candidate_is_skipped_not_broken(self):
        a = self.file("a.glb")
        missing = self.synthetic("missing.glb", 4)
        findings, stats = self.analyze([a, missing])
        self.assertFalse(any(f.kind in ("exact_duplicate", "broken") for f in findings))
        self.assertEqual(stats.warning_count, 1)

    def test_possible_duplicates_are_distinct_from_exact(self):
        rows = [self.file("model.stl", b"a" * 100), self.file("model (1).stl", b"b" * 100)]
        findings, _ = self.analyze(rows)
        self.assertEqual(sum(f.kind == "possible_duplicate" for f in findings), 2)
        self.assertFalse(any(f.kind == "exact_duplicate" for f in findings))

    def test_possible_duplicate_false_positive_sanity(self):
        rows = [self.synthetic("hand.stl", 100), self.synthetic("hand_copy.stl", 200), self.synthetic("hand.obj", 100)]
        findings, _ = self.analyze(rows, inspect_files=False)
        self.assertFalse(any(f.kind == "possible_duplicate" for f in findings))

    def test_naming_rules_are_token_bounded(self):
        for name in ("model_copy", "model - Copy", "model (2)", "model_final_final", "model_final2_final", "model_NEW", "model_backup", "model_tmp"):
            with self.subTest(name=name):
                self.assertIsNotNone(naming_issue(name))
        for name in ("oldham", "newton", "copyright", "template", "model_final", "fold"):
            with self.subTest(name=name):
                self.assertIsNone(naming_issue(name))
        self.assertEqual(normalized_stem("model - Copy (2)"), "model")

    def test_zero_and_large_policy_are_metadata_only(self):
        rows = [self.synthetic("zero.stl", 0), self.synthetic("big.stl", LARGE_ASSET_BYTES), self.synthetic("small.stl", LARGE_ASSET_BYTES - 1)]
        with patch.object(Path, "open", side_effect=AssertionError("asset read")), patch.object(Path, "stat", side_effect=AssertionError("stat")):
            findings, _ = self.analyze(rows, inspect_files=False)
        self.assertEqual({f.kind for f in findings}, {"zero_byte", "large"})
        self.assertEqual(next(f.severity for f in findings if f.kind == "large"), "info")

    def test_truncated_binary_stl_and_ascii_safety(self):
        findings, _ = self.analyze([self.file("broken.stl", b"\0" * 8), self.file("ascii.stl", b"solid a\nendsolid a")])
        self.assertEqual([Path(f.path).name for f in findings if f.kind == "broken"], ["broken.stl"])

    def test_obj_missing_mtl(self):
        findings, _ = self.analyze([self.file("a.obj", b"mtllib missing.mtl\nv 0 0 0\n")])
        self.assertEqual(sum(f.kind == "missing_companion" for f in findings), 1)

    def test_mtl_missing_texture_attaches_to_indexed_obj(self):
        self.file("a.mtl", b'map_Kd "absent texture.png"\n')
        obj = self.file("a.obj", b"mtllib a.mtl\n")
        findings, _ = self.analyze([obj])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].path, path_key(obj.path))
        self.assertEqual(findings[0].details["reference"], "absent texture.png")

    def test_existing_companions_not_flagged(self):
        self.file("texture.png", b"image")
        self.file("a.mtl", b"map_Kd texture.png\n")
        findings, _ = self.analyze([self.file("a.obj", b"mtllib a.mtl\n")])
        self.assertFalse(any(f.kind == "missing_companion" for f in findings))

    def test_ambiguous_mtl_options_and_malformed_obj_are_safe(self):
        self.file("a.mtl", b"map_Kd -unknown value missing.png\n")
        rows = [self.file("a.obj", b"mtllib a.mtl\n"), self.file("bad.obj", b"mtllib \"unclosed\n")]
        findings, _ = self.analyze(rows)
        self.assertFalse(any(f.kind == "missing_companion" for f in findings))

    def test_companion_outside_root_not_probed(self):
        findings, stats = self.analyze([self.file("a.obj", b"mtllib ../outside.mtl\n")])
        self.assertFalse(findings)
        self.assertEqual(stats.warning_count, 1)

    def test_archive_manifest_matching_and_unsafe_members(self):
        archive = self.root / "pack.zip"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("mesh.glb", b"mesh")
            z.writestr("../escape.glb", b"mesh")
        extracted = self.file("pack/mesh.glb")
        cache = ArchiveManifestCache(self.root / "archives.sqlite")
        self.addCleanup(cache.close)
        cache.ensure_indexed(archive)
        with patch.object(zipfile.ZipFile, "extract", side_effect=AssertionError("extract")), patch.object(zipfile.ZipFile, "extractall", side_effect=AssertionError("extract")):
            findings, _ = self.analyze([extracted], archive_db=cache._db_path)
        archive_findings = [f for f in findings if f.kind == "archive_extracted"]
        self.assertEqual(len(archive_findings), 1)
        self.assertEqual(archive_findings[0].details["member"], "mesh.glb")

    def test_ignore_persists_and_changed_identity_reappears(self):
        rec = self.synthetic("a_copy.stl")
        snap, _ = self.service.analyze([rec], self.root, inspect_files=False)
        ignored = self.service.ignore(self.root, snap.findings)
        self.assertTrue(ignored.findings[0].ignored)
        rerun, _ = self.service.analyze([rec], self.root, inspect_files=False)
        self.assertTrue(rerun.findings[0].ignored)
        changed, _ = self.service.analyze([replace(rec, size_bytes=101)], self.root, inspect_files=False)
        self.assertFalse(changed.findings[0].ignored)

    def test_restore_ignored_finding(self):
        snap, _ = self.service.analyze([self.synthetic("a_copy.stl")], self.root, inspect_files=False)
        ignored = self.service.ignore(self.root, snap.findings)
        restored = self.service.ignore(self.root, ignored.findings)
        self.assertFalse(restored.findings[0].ignored)

    def test_corrupt_cache_row_is_skipped(self):
        self.service.analyze([self.synthetic("a_copy.stl")], self.root, inspect_files=False)
        with closing(sqlite3.connect(self.repo.db_path)) as conn, conn:
            conn.execute("UPDATE findings SET details='not json'")
        self.assertEqual(self.repo.load(self.root).findings, ())

    def test_no_asset_mutations(self):
        rows = [self.file("a.glb"), self.file("b.glb")]
        before = [r.path.read_bytes() for r in rows]
        with patch.object(Path, "unlink", side_effect=AssertionError("delete")), patch.object(Path, "rename", side_effect=AssertionError("rename")), patch("shutil.move", side_effect=AssertionError("move")):
            self.service.analyze(rows, self.root)
        self.assertEqual([r.path.read_bytes() for r in rows], before)

    def test_unsafe_candidate_path_is_rejected(self):
        with self.assertRaises(OSError):
            safe_local_path(self.root.parent / "outside.glb", self.root)

    def test_cached_short_file_that_grew_is_not_broken(self):
        record = self.file("growing.stl", b"\0" * 8)
        record.path.write_bytes(b"\0" * 134)
        findings, _ = self.analyze([record])
        self.assertFalse(any(f.kind == "broken" for f in findings))

    def test_overlong_incomplete_obj_line_is_not_a_missing_reference(self):
        record = self.file("long.obj", b"mtllib " + b"a" * 100 + b".mtl")
        with patch("meshcorral.services.housekeeping.analyzer.TEXT_LIMIT_BYTES", 12):
            findings, _ = self.analyze([record])
        self.assertFalse(any(f.kind == "missing_companion" for f in findings))

    def test_symlink_candidate_rejected(self):
        record = self.file("a.glb")
        with patch.object(Path, "is_symlink", return_value=True):
            with self.assertRaises(OSError):
                safe_local_path(record.path, self.root)

    def test_permission_error_is_operational_not_broken(self):
        records = [self.file("a.glb"), self.file("b.glb")]
        with patch("meshcorral.services.housekeeping.analyzer.hash_candidate", side_effect=PermissionError("denied")):
            findings, stats = self.analyze(records)
        self.assertFalse(any(f.kind in ("broken", "exact_duplicate") for f in findings))
        self.assertEqual(stats.warning_count, 2)

    def test_publication_uses_one_commit(self):
        original = sqlite3.connect
        statements = []
        def connect(*args, **kwargs):
            conn = original(*args, **kwargs)
            conn.set_trace_callback(statements.append)
            return conn
        findings = [finding(self.synthetic(f"a{i}.stl"), "naming", {}) for i in range(100)]
        with patch("meshcorral.services.housekeeping.repository.sqlite3.connect", side_effect=connect):
            self.repo.publish(self.root, findings, 100)
        self.assertEqual(sum(s == "COMMIT" for s in statements), 1)
        self.assertFalse(any(s.startswith("SELECT") for s in statements))
