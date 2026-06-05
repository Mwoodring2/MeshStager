"""
Severity tiers for thumbnail/Bridge job failures.

Background thumbnail generation (auto-after-scan, large galleries) must be non-blocking:
typical asset issues (camera-only FBX, malformed files) should not throw modal popups
during browsing. A single, deliberate user-triggered job for one file, on the other hand,
is a high-signal moment where the full diagnostic dialog (open log, open output folder,
copy error) is still useful.

This module exposes :class:`JobOrigin`, attached to each enqueue request, plus a small
:func:`should_show_failure_modal` policy helper. Both are pure data so they can be unit
tested without instantiating the Qt UI.
"""

from __future__ import annotations

from enum import Enum
from typing import Final


class JobOrigin(str, Enum):
    """
    Where a bridge job request came from.

    Members
    -------
    MANUAL_SINGLE
        User explicitly triggered exactly one thumbnail (e.g. inspector "Generate
        thumbnail" button, single-file context menu). Failures may surface as a modal
        diagnostic dialog because the user is waiting on this exact result.
    MANUAL_BATCH
        User explicitly triggered a batch (e.g. "Queue thumbnails for selected",
        "Generate missing thumbnails for current view"). Per-job failures must not
        spawn modal dialogs; a footer/status message and the Jobs panel are enough.
    BACKGROUND_AUTO
        Auto thumbnail after scan and any other implicit background passes. Per-job
        failures must stay silent at the modal level (they remain visible in the Jobs
        panel, on the failed thumbnail card, and in the status footer).
    """

    MANUAL_SINGLE = "manual_single"
    MANUAL_BATCH = "manual_batch"
    BACKGROUND_AUTO = "background_auto"

    @classmethod
    def coerce(cls, value: object) -> "JobOrigin":
        """
        Best-effort coercion of *value* to :class:`JobOrigin`.

        Falls back to :attr:`BACKGROUND_AUTO` when *value* is ``None`` or unknown.
        Background is the safer default: it preserves the non-blocking guarantee for
        large gallery scans even if a future caller forgets to pass an origin.
        """
        if isinstance(value, cls):
            return value
        if value is None:
            return cls.BACKGROUND_AUTO
        try:
            return cls(str(value))
        except ValueError:
            return cls.BACKGROUND_AUTO


_MODAL_ORIGINS: Final[frozenset[JobOrigin]] = frozenset({JobOrigin.MANUAL_SINGLE})


def should_show_failure_modal(origin: JobOrigin) -> bool:
    """
    Return True when *origin* warrants a modal failure dialog.

    Only :attr:`JobOrigin.MANUAL_SINGLE` qualifies. Background and batch flows must
    remain non-blocking; their failures are still recorded in the Jobs panel/history,
    on the failed thumbnail card, and (optionally) in a footer toast.
    """
    return origin in _MODAL_ORIGINS
