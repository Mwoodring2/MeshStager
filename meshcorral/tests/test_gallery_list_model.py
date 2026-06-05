"""Tests for :class:`~meshcorral.ui.gallery_list_model.GalleryListModel` and browse sort."""

from __future__ import annotations

import unittest
import uuid
from pathlib import Path
from unittest import mock

from PySide6.QtCore import QCoreApplication, QSettings, Qt
from PySide6.QtWidgets import QApplication

from meshcorral.models.file_record import FileRecord
from meshcorral.services.browse_sort import (
    SORT_NAME_ASC,
    SORT_TYPE_ASC,
    SORT_TYPE_DESC,
    normalized_extension,
    sort_file_records,
)
from meshcorral.ui.gallery_list_model import GalleryListModel, GALLERY_RECORD_ROLE
from meshcorral.ui.thumbnail_controller import ThumbnailViewController


def _ensure_qapp() -> QApplication:
    inst = QApplication.instance()
    if inst is None:
        return QApplication([])
    return inst  # type: ignore[return-value]


class _SettingsSandbox:
    def __init__(self) -> None:
        self._org = QCoreApplication.organizationName() or ""
        self._app = QCoreApplication.applicationName() or ""
        self._test_id = f"meshcorral-tests-{uuid.uuid4().hex[:8]}"

    def __enter__(self) -> "_SettingsSandbox":
        QCoreApplication.setOrganizationName("MeshCorralTests")
        QCoreApplication.setApplicationName(self._test_id)
        QSettings().clear()
        return self

    def __exit__(self, *args: object) -> None:
        QSettings().clear()
        QCoreApplication.setOrganizationName(self._org)
        QCoreApplication.setApplicationName(self._app)


def _record(
    name: str,
    *,
    extension: str = "",
    size_bytes: int | None = 1,
    modified_time: float | None = 0.0,
) -> FileRecord:
    return FileRecord(
        path=Path(f"C:/assets/{name}"),
        name=name,
        extension=extension,
        parent_folder="assets",
        size_bytes=size_bytes,
        modified_time=modified_time,
    )


class TestGalleryListModel(unittest.TestCase):
    def setUp(self) -> None:
        self._thumb = ThumbnailViewController()
        self._model = GalleryListModel(self._thumb)

    def test_set_records_and_rowcount(self) -> None:
        p = Path("C:/t/a.stl")
        r = FileRecord(
            path=p,
            name="a.stl",
            extension=".stl",
            parent_folder="t",
            size_bytes=10,
            modified_time=0.0,
        )
        self._model.set_records([r])
        self.assertEqual(self._model.rowCount(), 1)
        ix = self._model.index(0)
        self.assertEqual(ix.data(GALLERY_RECORD_ROLE), r)
        self.assertEqual(ix.data(Qt.ItemDataRole.DisplayRole), "a.stl")

    def test_record_at(self) -> None:
        p = Path("C:/t/b.obj")
        r = FileRecord(
            path=p,
            name="b.obj",
            extension=".obj",
            parent_folder="t",
            size_bytes=1,
            modified_time=0.0,
        )
        self._model.set_records([r])
        self.assertEqual(self._model.record_at(0), r)
        self.assertIsNone(self._model.record_at(99))

    def test_append_records_extends_rowcount(self) -> None:
        """Staged scan appends rows without replacing the whole model."""
        p1 = Path("C:/t/a.stl")
        r1 = FileRecord(
            path=p1,
            name="a.stl",
            extension=".stl",
            parent_folder="t",
            size_bytes=1,
            modified_time=0.0,
        )
        p2 = Path("C:/t/b.stl")
        r2 = FileRecord(
            path=p2,
            name="b.stl",
            extension=".stl",
            parent_folder="t",
            size_bytes=2,
            modified_time=0.0,
        )
        self._model.set_records([r1])
        gen_after_set = self._model.layout_generation
        self._model.append_records([r2])
        self.assertEqual(self._model.rowCount(), 2)
        self.assertEqual(self._model.record_at(1), r2)
        self.assertEqual(
            self._model.layout_generation,
            gen_after_set,
            "append_records must not full-reset the gallery model",
        )


class TestBrowseSort(unittest.TestCase):
    def test_type_az_groups_by_extension(self) -> None:
        records = [
            _record("z.stl", extension=".stl"),
            _record("a.blend", extension=".blend"),
            _record("m.obj", extension=".obj"),
            _record("b.fbx", extension=".fbx"),
            _record("c.3mf", extension=".3mf"),
            _record("d.jpg", extension=".jpg"),
            _record("e.png", extension=".png"),
        ]
        ordered = sort_file_records(records, SORT_TYPE_ASC)
        exts = [normalized_extension(r) for r in ordered]
        self.assertEqual(
            exts,
            [".3mf", ".blend", ".fbx", ".jpg", ".obj", ".png", ".stl"],
        )

    def test_type_za_reverses_type_grouping(self) -> None:
        records = [
            _record("a.stl", extension=".stl"),
            _record("b.obj", extension=".obj"),
            _record("c.blend", extension=".blend"),
        ]
        ordered = sort_file_records(records, SORT_TYPE_DESC)
        exts = [normalized_extension(r) for r in ordered]
        self.assertEqual(exts, [".stl", ".obj", ".blend"])

    def test_within_type_sorts_by_name(self) -> None:
        records = [
            _record("zebra.obj", extension=".obj"),
            _record("alpha.obj", extension=".obj"),
            _record("beta.stl", extension=".stl"),
        ]
        ordered = sort_file_records(records, SORT_TYPE_ASC)
        self.assertEqual([r.name for r in ordered], ["alpha.obj", "zebra.obj", "beta.stl"])

    def test_extension_comparison_case_insensitive(self) -> None:
        records = [
            _record("b.STL", extension=".STL"),
            _record("a.stl", extension=".stl"),
        ]
        ordered = sort_file_records(records, SORT_TYPE_ASC)
        self.assertEqual([r.name for r in ordered], ["a.stl", "b.STL"])

    def test_files_without_extension_sort_last(self) -> None:
        records = [
            _record("readme", extension=""),
            _record("a.stl", extension=".stl"),
            _record("notes", extension=""),
        ]
        ordered = sort_file_records(records, SORT_TYPE_ASC)
        self.assertEqual(normalized_extension(ordered[0]), ".stl")
        self.assertEqual([r.name for r in ordered[1:]], ["notes", "readme"])

    def test_name_asc_default_preserves_existing_behavior(self) -> None:
        records = [
            _record("charlie.txt", extension=".txt"),
            _record("Alpha.txt", extension=".txt"),
            _record("bravo.txt", extension=".txt"),
        ]
        ordered = sort_file_records(records, SORT_NAME_ASC)
        self.assertEqual([r.name for r in ordered], ["Alpha.txt", "bravo.txt", "charlie.txt"])


class TestBrowseSortMainWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = _ensure_qapp()

    def test_changing_sort_does_not_schedule_thumbnail_pass(self) -> None:
        with _SettingsSandbox():
            from meshcorral.ui.main_window import MainWindow

            window = MainWindow()
            try:
                records = [
                    _record("b.stl", extension=".stl"),
                    _record("a.obj", extension=".obj"),
                ]
                window._view_records = list(records)
                window._model.set_rows(records)
                window._gallery_model.set_records(records)
                type_idx = window._sort_combo.findData(SORT_TYPE_ASC)
                self.assertGreaterEqual(type_idx, 0)
                with mock.patch.object(window, "_schedule_viewport_thumb_pass") as sched:
                    with mock.patch.object(window, "_try_enqueue_thumbnail_record") as enqueue:
                        window._sort_combo.setCurrentIndex(type_idx)
                        sched.assert_not_called()
                        enqueue.assert_not_called()
                ordered = [r.name for r in window._view_records]
                self.assertEqual(ordered, ["a.obj", "b.stl"])
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
