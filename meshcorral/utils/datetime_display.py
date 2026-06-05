from __future__ import annotations

import logging
import math
from datetime import datetime

logger = logging.getLogger(__name__)


def format_local_modified_display(epoch_seconds: float | int | None) -> str:
    """
    Convert a filesystem modified timestamp into a local, human-readable
    Windows-style date/time string.

    Example:
        04/18/2026 02:43 PM

    Returns:
        A formatted local time string, or an em dash if the value is invalid.
    """
    if epoch_seconds is None:
        return "—"

    try:
        value = float(epoch_seconds)
        if math.isnan(value) or math.isinf(value):
            raise ValueError("Timestamp is NaN or infinite.")

        dt = datetime.fromtimestamp(value)
        return dt.strftime("%m/%d/%Y %I:%M %p")
    except (OSError, OverflowError, ValueError, TypeError) as exc:
        logger.warning("Could not format modified timestamp %r: %s", epoch_seconds, exc)
        return "—"
