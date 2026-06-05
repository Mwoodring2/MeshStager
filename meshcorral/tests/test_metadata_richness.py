"""Prime v1.0 Sprint E — metadata richness tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from meshcorral.models.file_record import FileRecord
from meshcorral.services.metadata.asset_metadata_summary import AssetMetadataSummary
from meshcorral.services.metadata.geometry_metadata import (
    extract_geometry_metadata,
    should_defer_geometry,
    summary_from_loaded_mesh,
)
from meshcorral.services.metadata.metadata_display_copy import (
    METADATA_STATUS_DEFERRED,
    METADATA_STATUS_PENDING,
    METADATA_STATUS_READY,
    metadata_status_label,
)
from meshcorral.services.metadata.metadata_summary_registry import MetadataSummaryRegistry
from meshcorral.services.metadata.metadata_tunables import max_inline_bytes
from meshcorral.ui.file_columns import export_headers, export_row_for_record
from meshcorral.ui.inspector.metadata_panel import MetadataPanel
from meshcorral.ui.search.query_parser import parse_query
from meshcorral.ui.search.search_index import record_matches_metadata


def _stl_record(
    name: str = "part.stl",
    *,
    size_bytes: int = 1024,
    path: Path | None = None,
) -> FileRecord:
    p = path or Path(f"C:/work/{name}")
    return FileRecord(
        path=p,
        name=name,
        extension=".stl",
        parent_folder="work",
        size_bytes=size_bytes,
        modified_time=0.0,
    )


class TestAssetMetadataSummary(unittest.TestCase):
    """Summary formatting and display helpers."""

    def test_dimensions_shown_as_mm(self) -> None:
        summary = AssetMetadataSummary(
            path=Path("C:/a.stl"),
            ext=".stl",
            dimensions_mm=(10.0, 20.5, 5.25),
        )
        self.assertIn("mm", summary.dimensions_display())
        self.assertIn("10.00", summary.dimensions_display())

    def test_copy_block_includes_fields(self) -> None:
        summary = AssetMetadataSummary(
            path=Path("C:/a.stl"),
            ext=".stl",
            face_count=1200,
            metadata_source="live",
        )
        text = "\n".join(summary.copy_block_lines())
        self.assertIn("Faces:", text)
        self.assertIn("1,200", text)

    def test_geometry_diagnostics_watertight_and_faces(self) -> None:
        summary = AssetMetadataSummary(
            path=Path("C:/a.stl"),
            ext=".stl",
            watertight=True,
            face_count=125_000,
        )
        self.assertEqual(summary.geometry_diagnostics_display(), "Watertight · 125,000 faces")

    def test_geometry_diagnostics_deferred(self) -> None:
        summary = AssetMetadataSummary(
            path=Path("C:/big.stl"),
            ext=".stl",
            deferred_reason="File exceeds 8 MB inline metadata cap",
        )
        self.assertEqual(summary.geometry_diagnostics_display(), METADATA_STATUS_DEFERRED)

    def test_geometry_diagnostics_unavailable_for_non_mesh(self) -> None:
        summary = AssetMetadataSummary(path=Path("C:/tex.png"), ext=".png")
        self.assertEqual(summary.geometry_diagnostics_display(), "Unsupported file type")

    def test_geometry_diagnostics_pending_mesh(self) -> None:
        summary = AssetMetadataSummary(path=Path("C:/a.stl"), ext=".stl")
        self.assertEqual(summary.geometry_diagnostics_display(), "Not loaded yet")


class TestMetadataStatusCopy(unittest.TestCase):
    def test_pending_mesh_without_geometry(self) -> None:
        summary = AssetMetadataSummary(
            path=Path("C:/a.stl"),
            ext=".stl",
            metadata_source="pending",
            cache_status="READY, indexed",
        )
        self.assertEqual(metadata_status_label(summary), METADATA_STATUS_PENDING)
        self.assertEqual(summary.face_count_display(), "Preview ready, metadata not loaded")

    def test_render_source_ready(self) -> None:
        summary = AssetMetadataSummary(
            path=Path("C:/a.stl"),
            ext=".stl",
            face_count=100,
            metadata_source="render",
        )
        self.assertEqual(metadata_status_label(summary), METADATA_STATUS_READY)

    def test_deferred_large_file(self) -> None:
        summary = AssetMetadataSummary(
            path=Path("C:/big.stl"),
            ext=".stl",
            deferred_reason="cap",
            metadata_source="deferred",
        )
        self.assertEqual(metadata_status_label(summary), METADATA_STATUS_DEFERRED)


class TestRenderGeometryBackfill(unittest.TestCase):
    def test_summary_from_loaded_mesh_populates_counts(self) -> None:
        try:
            import trimesh  # type: ignore[import-not-found]
        except ImportError:
            self.skipTest("trimesh not installed")
        box = trimesh.creation.box(extents=(10.0, 20.0, 5.0))
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
            box.export(tmp.name)
            path = Path(tmp.name)
        try:
            loaded = trimesh.load(str(path), force="mesh")
            mesh = loaded
            if hasattr(loaded, "dump") and not hasattr(loaded, "vertices"):
                mesh = loaded.dump(concatenate=True)
            summary = summary_from_loaded_mesh(path, mesh, metadata_source="render")
            self.assertEqual(summary.metadata_source, "render")
            self.assertIsNotNone(summary.face_count)
            self.assertIsNotNone(summary.vertex_count)
            self.assertIsNotNone(summary.dimensions_mm)
        finally:
            path.unlink(missing_ok=True)


class TestGeometryMetadata(unittest.TestCase):
    """Deferred large files and worker-only extraction contract."""

    def test_large_file_returns_deferred_status(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".stl", delete=False) as tmp:
            tmp.write(b"solid test\nendsolid test\n")
            path = Path(tmp.name)
        try:
            huge = max_inline_bytes() + 1
            defer, reason = should_defer_geometry(path, huge, allow_large=False)
            self.assertTrue(defer)
            self.assertIsNotNone(reason)
            summary = extract_geometry_metadata(path, size_bytes=huge, allow_large=False)
            self.assertEqual(summary.metadata_source, "deferred")
            self.assertEqual(summary.cache_status, "deferred")
        finally:
            path.unlink(missing_ok=True)

    def test_extract_does_not_require_ui_thread_marker(self) -> None:
        """Geometry module is documented for background use only (no Qt imports)."""
        import meshcorral.services.metadata.geometry_metadata as geom

        self.assertNotIn("PySide6", Path(geom.__file__).read_text(encoding="utf-8"))


class TestMetadataSearchQueries(unittest.TestCase):
    """Metadata predicates only match when summary fields exist."""

    def test_faces_query_requires_metadata(self) -> None:
        parsed = parse_query("faces>100000")
        self.assertTrue(parsed.needs_metadata())
        rich = AssetMetadataSummary(
            path=Path("C:/a.stl"),
            ext=".stl",
            face_count=200_000,
        )
        poor = AssetMetadataSummary(path=Path("C:/b.stl"), ext=".stl")
        self.assertTrue(record_matches_metadata(rich, parsed))
        self.assertFalse(record_matches_metadata(poor, parsed))
        self.assertFalse(record_matches_metadata(None, parsed))

    def test_watertight_query(self) -> None:
        parsed = parse_query("watertight:true")
        ok = AssetMetadataSummary(path=Path("a"), ext=".stl", watertight=True)
        no = AssetMetadataSummary(path=Path("b"), ext=".stl", watertight=False)
        self.assertTrue(record_matches_metadata(ok, parsed))
        self.assertFalse(record_matches_metadata(no, parsed))

    def test_archive_members_query(self) -> None:
        parsed = parse_query("archive_members>0")
        ok = AssetMetadataSummary(path=Path("a.zip"), ext=".zip", archive_member_count=3)
        self.assertTrue(record_matches_metadata(ok, parsed))


class TestExportColumns(unittest.TestCase):
    """CSV export keeps legacy columns and appends rich metadata."""

    def test_export_includes_new_columns_without_breaking_old(self) -> None:
        headers = export_headers()
        self.assertEqual(headers[:7], ["Name", "Ext", "Type", "Folder", "Path", "Size", "Modified"])
        record = _stl_record()
        row = export_row_for_record(record)
        self.assertEqual(len(row), len(headers))
        self.assertEqual(row[0], "part.stl")

    def test_export_with_summary_populates_rich_cells(self) -> None:
        record = _stl_record()
        summary = AssetMetadataSummary(
            path=record.path,
            ext=".stl",
            face_count=10,
            watertight=True,
            metadata_source="live",
            cache_status="live",
        )
        row = export_row_for_record(record, summary)
        self.assertEqual(row[7], "Not loaded yet")
        self.assertEqual(row[8], "10")


class TestInspectorMetadataPanel(unittest.TestCase):
    """Inspector shows placeholders when metadata is missing."""

    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication
        import sys

        if QApplication.instance() is None:
            QApplication(sys.argv)

    def test_missing_metadata_graceful(self) -> None:
        panel = MetadataPanel()
        panel.apply(
            path_str="C:/x.stl",
            folder_display="work",
            extension=".STL",
            size_display="1 KB",
            modified_display="—",
            asset_mode_display="3D",
            metadata_source_display="Metadata pending",
            dimensions_display="Metadata pending",
            face_count_display="Metadata pending",
            vertex_count_display="—",
            watertight_display="—",
            mesh_density_display="—",
            archive_members_display="—",
            cache_status_display="deferred (size)",
            tags="—",
            metadata_block="",
            metadata_copy_text="",
            path_actions_enabled=True,
        )
        self.assertEqual(panel._faces_value.text(), "Metadata pending")


class TestMetadataRegistry(unittest.TestCase):
    """Registry merge preserves prior fields."""

    def test_merge_keeps_archive_when_geometry_arrives(self) -> None:
        reg = MetadataSummaryRegistry()
        base = AssetMetadataSummary(
            path=Path("C:/a.stl"),
            ext=".stl",
            archive_member_count=5,
        )
        reg.put(base)
        geom = AssetMetadataSummary(
            path=Path("C:/a.stl"),
            ext=".stl",
            face_count=100,
            metadata_source="live",
        )
        merged = reg.merge(geom)
        self.assertEqual(merged.archive_member_count, 5)
        self.assertEqual(merged.face_count, 100)


if __name__ == "__main__":
    unittest.main()
