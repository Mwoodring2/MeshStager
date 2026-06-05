"""Maya executable discovery (Windows-focused, safe fallback).

No file parsing and no thumbnail generation. Used only to enable "Open in Maya".
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Literal

from meshcorral.services.settings_service import SettingsService

MayaReadinessLabel = Literal["Ready", "Not found", "Not configured"]


def _candidate_maya_roots() -> list[Path]:
    roots: list[Path] = []
    pf = os.environ.get("ProgramFiles")
    if pf:
        roots.append(Path(pf) / "Autodesk")
    return roots


def _scan_for_maya_exe(roots: list[Path]) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        try:
            if not root.exists() or not root.is_dir():
                continue
            # Autodesk/Maya2026/bin/maya.exe (version folder varies).
            for exe in root.rglob("maya.exe"):
                if exe.name.lower() == "maya.exe" and exe.parent.name.lower() == "bin":
                    found.append(exe)
        except OSError:
            continue
    unique = {p.resolve() for p in found if p.is_file()}
    return sorted(unique, key=lambda p: str(p).lower(), reverse=True)


def find_maya_executable(settings: SettingsService | None = None) -> Path | None:
    """Resolve a Maya executable path if possible.

    Precedence:
    1. User path in app settings (when provided and valid)
    2. PATH search for ``maya.exe``
    3. Common install roots under ``C:/Program Files/Autodesk/Maya*/bin/maya.exe``
    """

    if settings is not None:
        configured = settings.maya_executable()
        if configured:
            p = Path(configured)
            if p.is_file():
                return p.resolve()

    if os.name == "nt":
        hit = shutil.which("maya.exe")
        if hit:
            p = Path(hit)
            if p.is_file():
                return p.resolve()

    for exe in _scan_for_maya_exe(_candidate_maya_roots()):
        return exe
    return None


def describe_maya_readiness(
    settings: SettingsService,
    locator_result: Path | None,
) -> MayaReadinessLabel:
    """Map stored settings plus a precomputed locator result to a short UI label."""

    if locator_result is not None:
        return "Ready"
    if (settings.maya_executable() or "").strip():
        return "Not found"
    return "Not configured"

