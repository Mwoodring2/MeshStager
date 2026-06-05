"""
Programmatic v1 acceptance checks against TestSource / TestDestination fixtures.

Steps 1 and 11 (full GUI, clipboard) are not exercised here; the rest mirror the checklist.
"""

from __future__ import annotations

import csv
import shutil
import tempfile
import unittest
from pathlib import Path

from meshcorral.services.export_service import export_records_to_csv
from meshcorral.services.move_service import MoveService
from meshcorral.services.scanner import scan_folder
from meshcorral.services.search_service import filter_records
from meshcorral.ui.file_columns import export_headers, export_row_for_record

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_SOURCE = REPO_ROOT / "TestSource"
FIXTURE_DEST = REPO_ROOT / "TestDestination"


class TestAcceptanceV1Fixture(unittest.TestCase):
    """Run the 14-step checklist (API-level) on a disposable copy of the repo fixtures."""

    @classmethod
    def setUpClass(cls) -> None:
        if not FIXTURE_SOURCE.is_dir() or not FIXTURE_DEST.is_dir():
            raise unittest.SkipTest(
                "TestSource and/or TestDestination missing under repo root; "
                "create them before running acceptance tests."
            )

    def test_steps_2_through_14_against_fixture_copy(self) -> None:
        """Disposable workspace so copy/move do not destroy the golden fixture tree."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ts = root / "TestSource"
            td = root / "TestDestination"
            shutil.copytree(FIXTURE_SOURCE, ts)
            shutil.copytree(FIXTURE_DEST, td)
            mover = MoveService()

            # Step 2 — recursive scan; notes.txt must not appear as a row.
            rec_full = scan_folder(ts, recursive=True)
            names_full = {r.name for r in rec_full}
            self.assertNotIn(
                "notes.txt",
                names_full,
                "Step 2: notes.txt must not appear (unsupported extension).",
            )
            for ext in (".stl", ".obj", ".blend", ".mtl", ".ztl"):
                self.assertTrue(
                    any(r.extension == ext for r in rec_full),
                    f"Step 2: expected at least one {ext} file in scan.",
                )

            # Step 3 — non-recursive: nothing under SubFolder/.
            rec_flat = scan_folder(ts, recursive=False)
            names_flat = {r.name for r in rec_flat}
            self.assertNotIn("nested_model.stl", names_flat, "Step 3: nested STL excluded.")
            self.assertNotIn("sculpt.ztl", names_flat, "Step 3: nested ZTL excluded.")
            self.assertEqual(len(rec_full), len(rec_flat) + 2, "Step 3: two nested-only files.")

            # Step 4 — filter "model"; working set size unchanged (rec_full is scan output).
            filtered_model = filter_records(rec_full, search_text="model")
            for r in filtered_model:
                self.assertIn("model", r.name.lower())
            self.assertEqual(len(rec_full), 6, "Step 4: full scan row count unchanged.")
            self.assertEqual(
                {r.name for r in filtered_model},
                {"model_a.stl", "model_b.obj", "nested_model.stl"},
                "Step 4: name filter 'model' narrows to matching files only.",
            )

            # Step 5 — Type = DCC Scene (only .blend and .ztl from this fixture).
            dcc = filter_records(rec_full, category_filter="DCC Scene")
            dcc_exts = {r.extension for r in dcc}
            self.assertEqual(dcc_exts, {".blend", ".ztl"}, "Step 5: DCC filter set.")
            self.assertEqual({r.name for r in dcc}, {"scene.blend", "sculpt.ztl"})

            # Step 6 — reset filters = defaults.
            reset_view = filter_records(rec_full)
            self.assertEqual(len(reset_view), len(rec_full))

            # Step 7 — model_b + destination: one OK row.
            model_b = next(r for r in rec_full if r.name == "model_b.obj")
            plan_b_ok = mover.build_move_plan([model_b.path], td)
            self.assertEqual(plan_b_ok[0].status, MoveService.STATUS_OK)
            self.assertEqual(plan_b_ok[0].message[:5], "Ready")

            # Step 8 — model_a collides with existing TestDestination/model_a.stl.
            model_a = next(r for r in rec_full if r.name == "model_a.stl")
            plan_a = mover.build_move_plan([model_a.path], td)
            self.assertEqual(len(plan_a), 1)
            self.assertEqual(plan_a[0].status, MoveService.STATUS_BLOCKED)
            self.assertIn("collision", plan_a[0].message.lower())

            # Step 9 — copy model_b; source and destination both have the file.
            self.assertFalse((td / "model_b.obj").exists())
            copy_res = mover.execute_copy_plan(plan_b_ok)
            self.assertEqual(copy_res.success_count, 1, "Step 9: one successful copy.")
            self.assertTrue(model_b.path.is_file(), "Step 9: source file still present.")
            self.assertTrue((td / "model_b.obj").is_file(), "Step 9: destination has copy.")

            # Step 10 — move scene.blend off source into destination.
            scene_path = ts / "scene.blend"
            self.assertTrue(scene_path.is_file())
            plan_scene = mover.build_move_plan([scene_path], td)
            self.assertEqual(plan_scene[0].status, MoveService.STATUS_OK)
            move_res = mover.execute_move_plan(plan_scene)
            self.assertEqual(move_res.success_count, 1, "Step 10: one successful move.")
            self.assertFalse(scene_path.exists(), "Step 10: removed from source.")
            self.assertTrue((td / "scene.blend").is_file(), "Step 10: present at destination.")

            # Step 12 — CSV matches table headers and display-formatted Size/Modified.
            remaining = scan_folder(ts, recursive=True)
            out_csv = root / "export.csv"
            export_records_to_csv(remaining, out_csv)
            with out_csv.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(
                rows[0],
                export_headers(),
                "Step 12: CSV header row matches file_columns / table.",
            )
            base_headers = ["Name", "Ext", "Type", "Folder", "Path", "Size", "Modified"]
            self.assertEqual(rows[0][: len(base_headers)], base_headers)
            if len(rows) > 1:
                data_row = rows[1]
                self.assertEqual(len(data_row), len(export_headers()))
                # Size column is human-readable (not raw integer-only).
                self.assertRegex(data_row[5], r"\d+(\.\d+)?\s*(B|KB|MB|GB|TB|PB)|—")
                # Modified column is MM/DD/YYYY style, not ISO.
                self.assertRegex(data_row[6], r"^\d{2}/\d{2}/\d{4} \d{1,2}:\d{2} (AM|PM)$")
                # Same as export_row_for_record for first remaining file.
                self.assertEqual(data_row, export_row_for_record(remaining[0]))

            # Step 13 — invalid destination: planning raises before touching files.
            bad_dest = root / "missing_parent" / "nested" / "dest"
            with self.assertRaises(ValueError):
                mover.build_move_plan([model_b.path], bad_dest)

            # Step 14 — scan a different folder replaces working set (new scan output only).
            other = root / "OtherScan"
            other.mkdir()
            lone = other / "solo.stl"
            lone.write_text("x", encoding="utf-8")
            other_records = scan_folder(other, recursive=True)
            self.assertEqual(len(other_records), 1)
            self.assertEqual(other_records[0].name, "solo.stl")
            self.assertTrue(str(other_records[0].path).startswith(str(other)))
            self.assertFalse(any(str(r.path).startswith(str(ts)) for r in other_records))


if __name__ == "__main__":
    unittest.main()
