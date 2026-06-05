from __future__ import annotations

import math
import unittest

from meshcorral.utils.datetime_display import format_local_modified_display


class TestDatetimeDisplay(unittest.TestCase):
    def test_formats_local_timestamp(self) -> None:
        result = format_local_modified_display(1713470580)
        self.assertIsInstance(result, str)
        self.assertNotEqual(result, "—")
        self.assertIn("/", result)

    def test_nan_returns_dash(self) -> None:
        result = format_local_modified_display(math.nan)
        self.assertEqual(result, "—")

    def test_none_returns_dash(self) -> None:
        result = format_local_modified_display(None)
        self.assertEqual(result, "—")


if __name__ == "__main__":
    unittest.main()
