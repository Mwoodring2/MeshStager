"""Tests for user-facing filesystem error text."""

from __future__ import annotations

import errno
import unittest

from meshcorral.utils.filesystem_errors import humanize_filesystem_error


class TestHumanizeFilesystemError(unittest.TestCase):
    """``humanize_filesystem_error`` maps common failures to readable strings."""

    def test_enospc(self) -> None:
        exc = OSError(errno.ENOSPC, "No space left on device")
        msg = humanize_filesystem_error(exc)
        self.assertIn("space", msg.lower())

    def test_enoent(self) -> None:
        exc = OSError(errno.ENOENT, "No such file")
        msg = humanize_filesystem_error(exc)
        self.assertIn("not found", msg.lower())

    def test_permission_error(self) -> None:
        msg = humanize_filesystem_error(PermissionError("denied"))
        self.assertIn("permission", msg.lower())

    def test_winerror_32_via_attribute(self) -> None:
        exc = OSError(13, "Permission denied")
        exc.winerror = 32  # type: ignore[attr-defined]
        msg = humanize_filesystem_error(exc)
        self.assertIn("in use", msg.lower())
