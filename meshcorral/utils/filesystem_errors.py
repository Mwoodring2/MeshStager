"""Map OS-level exceptions to short, actionable UI strings."""

from __future__ import annotations

import errno


def humanize_filesystem_error(exc: BaseException) -> str:
    """Return human-readable text for move/copy failures (no raw errno dumps)."""
    winerr = getattr(exc, "winerror", None)

    if winerr == 32:
        return (
            "The file is in use or locked by another program. Close that program "
            "(or the file tab) and try again."
        )
    if winerr == 206:
        return (
            "The path is too long for Windows (default limit is about 260 characters). "
            "Use a shorter folder chain or enable long paths in Windows."
        )
    if winerr == 5:
        return (
            "Access was denied. You may be writing to a protected system folder, "
            "or need permission to the destination."
        )

    if isinstance(exc, PermissionError):
        return (
            "Permission denied. Check that you can read the source and write the "
            "destination, and that no other app has the file open."
        )

    if isinstance(exc, OSError):
        err = exc.errno
        if err in (errno.EACCES, errno.EPERM):
            return (
                "Permission denied. Check folder permissions or whether the file "
                "is read-only or open elsewhere."
            )
        if err == errno.ENOSPC:
            return "Not enough disk space to complete the operation."
        if err == errno.ENOENT:
            return (
                "A file or folder was not found. The path may have changed since "
                "the preview (for example, the file was moved or deleted)."
            )
        if err == errno.ENOTDIR:
            return "A path component is not a folder—check the destination path."
        if err == errno.EEXIST:
            return "A file already exists at the destination (collision)."
        if err == errno.EISDIR:
            return "Expected a file but found a folder at the destination path."
        if exc.strerror:
            return f"{exc.strerror.strip().rstrip('.')}. ({type(exc).__name__})"
        return str(exc)

    return str(exc)
