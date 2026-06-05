"""Gallery UI performance tuning (RC3 scroll pass)."""

from __future__ import annotations

from typing import Final

from meshcorral.app.config import read_branded_env

_DEFAULT_MAX_VISIBLE_BUILD: Final[int] = 100
_DEFAULT_SCROLL_DEBOUNCE_MS: Final[int] = 75


def gallery_max_visible_build() -> int:
    """
    Cap viewport prefetch / decode fan-out during scroll (visible + buffer).

    Override with ``MESHSTAGER_GALLERY_MAX_VISIBLE_BUILD`` (or ``ROUNDUP_*`` legacy).
    """
    raw = read_branded_env("GALLERY_MAX_VISIBLE_BUILD", str(_DEFAULT_MAX_VISIBLE_BUILD))
    try:
        value = int(raw)
    except ValueError:
        value = _DEFAULT_MAX_VISIBLE_BUILD
    return max(24, min(value, 2000))


def gallery_scroll_debounce_ms() -> int:
    """
    Debounce delay for selection-driven inspector/metadata refresh.

    Override with ``MESHSTAGER_GALLERY_SCROLL_DEBOUNCE_MS``.
    """
    raw = read_branded_env("GALLERY_SCROLL_DEBOUNCE_MS", str(_DEFAULT_SCROLL_DEBOUNCE_MS))
    try:
        value = int(raw)
    except ValueError:
        value = _DEFAULT_SCROLL_DEBOUNCE_MS
    return max(0, min(value, 2000))
