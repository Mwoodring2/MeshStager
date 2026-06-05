"""Tag name validation and bulk input parsing (Tier 2.1)."""

from __future__ import annotations

import re

_MAX_TAG_LEN = 64
_TAG_SPLIT_RE = re.compile(r"[,;]+")


def normalize_tag(raw: str) -> str:
    """
    Canonical tag string (lowercase, collapsed whitespace).

    Raises:
        ValueError: when empty or too long.
    """
    cleaned = " ".join((raw or "").strip().split()).lower()
    if not cleaned:
        raise ValueError("Tag cannot be empty.")
    if len(cleaned) > _MAX_TAG_LEN:
        raise ValueError(f"Tag must be at most {_MAX_TAG_LEN} characters.")
    if "/" in cleaned or "\\" in cleaned:
        raise ValueError("Tag cannot contain path separators.")
    return cleaned


def parse_tags_from_dialog(text: str) -> list[str]:
    """
    Parse multiline / comma-separated tag input from :class:`TagDialog`.

    Returns normalized unique tags in first-seen order.
    """
    seen: set[str] = set()
    out: list[str] = []
    for line in (text or "").splitlines():
        for chunk in _TAG_SPLIT_RE.split(line):
            piece = chunk.strip()
            if not piece:
                continue
            normalized = normalize_tag(piece)
            if normalized in seen:
                continue
            seen.add(normalized)
            out.append(normalized)
    return out
