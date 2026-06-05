from __future__ import annotations

import math
import unittest

from meshcorral.utils.filesize_display import format_file_size_display


class TestFileSizeDisplay(unittest.TestCase):
    def test_bytes(self) -> None:
        self.assertEqual(format_file_size_display(512), "512 B")

    def test_kb(self) -> None:
        self.assertEqual(format_file_size_display(2048), "2.0 KB")

    def test_mb(self) -> None:
        self.assertEqual(format_file_size_display(1048576), "1.0 MB")

    def test_nan(self) -> None:
        self.assertEqual(format_file_size_display(math.nan), "—")

    def test_none(self) -> None:
        self.assertEqual(format_file_size_display(None), "—")


if __name__ == "__main__":
    unittest.main()
