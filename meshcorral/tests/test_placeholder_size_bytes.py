"""Placeholder cards tolerate records with unknown size_bytes."""

from __future__ import annotations

import unittest
from pathlib import Path

from PySide6.QtWidgets import QApplication

from meshcorral.models.file_record import FileRecord
from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.ui.thumbnails.placeholder_factory import build_format_card_icon


def _qapp() -> QApplication:
    inst = QApplication.instance()
    if inst is None:
        return QApplication([])
    return inst


class TestPlaceholderSizeBytes(unittest.TestCase):
    def test_none_size_bytes_does_not_raise(self) -> None:
        _qapp()
        record = FileRecord(
            path=Path("C:/work/part.stl"),
            name="part.stl",
            extension=".stl",
            parent_folder="work",
            size_bytes=None,
            modified_time=0.0,
        )
        icon = build_format_card_icon(
            record,
            visual=ThumbVisualState.PLACEHOLDER,
            health=ThumbHealth.PENDING,
            px=96,
            deferred=True,
        )
        self.assertFalse(icon.isNull())


if __name__ == "__main__":
    unittest.main()
