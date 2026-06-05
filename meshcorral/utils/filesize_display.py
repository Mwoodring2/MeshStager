from __future__ import annotations

import logging
import math

logger = logging.getLogger(__name__)


def format_file_size_display(size_bytes: int | float | None) -> str:
    """
    Convert a file size in bytes to a human-readable string.

    Examples:
        0 B
        532 B
        1.2 KB
        15.4 MB
        2.1 GB

    Returns:
        Human-readable string, or em dash if invalid.
    """
    if size_bytes is None:
        return "—"

    try:
        size = float(size_bytes)

        if math.isnan(size) or math.isinf(size) or size < 0:
            raise ValueError("Invalid file size.")

        # Bytes
        if size < 1024:
            return f"{int(size)} B"

        # KB, MB, GB, TB
        units = ["KB", "MB", "GB", "TB"]
        size /= 1024.0

        for unit in units:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0

        # Larger than TB
        return f"{size:.1f} PB"

    except (ValueError, TypeError) as exc:
        logger.warning("Could not format file size %r: %s", size_bytes, exc)
        return "—"
