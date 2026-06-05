"""Consistent filename truncation and tooltips across browse surfaces."""

from __future__ import annotations

# Default visible filename length (gallery label, table name, preview title).
DEFAULT_FILENAME_MAX_CHARS: int = 52


def truncate_filename(name: str, *, max_chars: int = DEFAULT_FILENAME_MAX_CHARS) -> str:
    """
    Truncate *name* for on-screen labels while keeping the extension when possible.

    Full *name* should still be exposed via tooltip or copy actions.
    """
    text = (name or "").strip()
    limit = max(12, int(max_chars))
    if len(text) <= limit:
        return text
    dot = text.rfind(".")
    if dot > 0 and dot < len(text) - 1:
        ext = text[dot:]
        if len(ext) <= 14:
            head_budget = limit - len(ext) - 1
            if head_budget >= 8:
                return f"{text[:head_budget]}…{ext}"
    return f"{text[: limit - 1]}…"


def filename_tooltip(name: str, *, extra_lines: str = "") -> str:
    """Tooltip text: always the full filename, optional extra diagnostic lines."""
    base = (name or "").strip()
    extra = (extra_lines or "").strip()
    if base and extra:
        return f"{base}\n{extra}"
    return base or extra
