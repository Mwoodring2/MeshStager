"""Locate and validate Blender for the optional Blender Bridge (no Blender required to run the app)."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Literal, Optional

from meshcorral.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

# Seconds; `blender --version` should return almost immediately.
_VERSION_TIMEOUT_SEC = 15.0


def _candidate_blender_roots() -> list[Path]:
    """
    Common install roots on Windows (and similar layouts under LOCALAPPDATA).

    Typical layout:
    ``C:/Program Files/Blender Foundation/Blender 4.4/blender.exe``
    """
    roots: list[Path] = []
    for base_env in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
        base = os.environ.get(base_env)
        if not base:
            continue
        root = Path(base)
        roots.append(root / "Blender Foundation")
        roots.append(root / "Programs" / "Blender Foundation")
    return roots


def _scan_for_blender_exe(roots: list[Path]) -> list[Path]:
    """Collect ``blender.exe`` paths under known roots (best-effort, newest-ish first)."""
    found: list[Path] = []
    for r in roots:
        try:
            if r.is_file() and r.name.lower() == "blender.exe":
                found.append(r)
                continue
            if not r.exists() or not r.is_dir():
                continue
            for p in r.rglob("blender.exe"):
                found.append(p)
        except OSError as e:
            logger.debug("Could not scan %s: %s", r, e)
    # Prefer higher version-ish paths (string sort is a simple heuristic).
    unique = {p.resolve() for p in found}
    return sorted(unique, key=lambda x: str(x).lower(), reverse=True)


def find_blender_executable(settings: SettingsService | None = None) -> Optional[Path]:
    """
    Resolve a Blender executable if possible.

    Precedence:
    1. User path in app settings (when ``settings`` is provided and non-empty)
    2. ``BLENDER_EXE`` environment variable
    3. Common Windows install locations under ``Blender Foundation``

    Returns ``None`` if nothing is found. The app must run without Blender installed.
    """
    if settings is not None:
        configured = settings.blender_executable()
        if configured:
            p = Path(configured)
            if p.is_file():
                return p.resolve()

    env = os.environ.get("BLENDER_EXE", "").strip()
    if env:
        p = Path(env)
        if p.is_file():
            return p.resolve()

    for exe in _scan_for_blender_exe(_candidate_blender_roots()):
        return exe
    return None


BlenderReadinessLabel = Literal["Ready", "Not found", "Not configured"]


def describe_blender_readiness(
    settings: SettingsService,
    locator_result: Path | None,
) -> BlenderReadinessLabel:
    """
    Map stored settings plus a precomputed locator result to a short UI label.

    Pure: does not spawn Blender. Pass *locator_result* from :func:`find_blender_executable`
    (filesystem / env / install layout checks only).

    **Ready** — a usable executable path was resolved.

    **Not configured** — no path is stored in settings and nothing was resolved (nothing to
    run until the user sets a path or installs Blender where discovery looks).

    **Not found** — a non-empty path is stored in settings but nothing was resolved (invalid
    or missing configured path and no fallback from env/install scan matched, per locator).
    """
    if locator_result is not None:
        return "Ready"
    if (settings.blender_executable() or "").strip():
        return "Not found"
    return "Not configured"


def _run_version_subprocess(exe: Path) -> tuple[int, str, str]:
    """
    Run ``blender --version`` and return (returncode, stdout, stderr).

    On Windows, avoid spawning a visible console window when possible.
    """
    run_kwargs: dict = {
        "capture_output": True,
        "text": True,
        "timeout": _VERSION_TIMEOUT_SEC,
    }
    if os.name == "nt":
        # Python 3.7+; suppress console window for GUI apps.
        run_kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    try:
        completed = subprocess.run([str(exe), "--version"], **run_kwargs)
    except FileNotFoundError:
        return -1, "", "Executable not found or not runnable."
    except PermissionError as e:
        return -1, "", f"Permission denied: {e}"
    except OSError as e:
        return -1, "", f"OS error: {e}"
    except subprocess.TimeoutExpired:
        return -1, "", f"Timed out after {_VERSION_TIMEOUT_SEC:.0f} seconds."
    return (
        completed.returncode,
        completed.stdout or "",
        completed.stderr or "",
    )


def get_blender_version(path: str | Path) -> str:
    """
    Return the version string from ``blender --version`` (first line, stripped).

    On failure (missing file, not executable, timeout, non-zero exit), returns a short
    human-readable message starting with a prefix so the UI can show it clearly. Does not
    raise for normal failure cases.
    """
    exe = Path(path)
    if not exe.is_file():
        return "Error: file does not exist or is not a file."

    code, out, err = _run_version_subprocess(exe)
    combined = (out + "\n" + err).strip()
    if code != 0:
        detail = combined if combined else "No output from Blender."
        logger.warning("Blender --version failed (%s): %s", code, detail)
        return f"Error: could not read version (exit {code}). {detail}"

    first_line = (out.strip().splitlines() or [""])[0].strip()
    if not first_line:
        return "Error: Blender returned no version text."
    return first_line


def validate_blender_path(path: str | Path) -> bool:
    """
    Return True if ``path`` points to a file that responds to ``blender --version`` successfully.
    """
    exe = Path(path)
    if not exe.is_file():
        return False
    code, out, _ = _run_version_subprocess(exe)
    if code != 0:
        return False
    if not (out or "").strip():
        return False
    return True


def detect_blender_executable(settings: SettingsService) -> Path | None:
    """
    Backwards-compatible alias for :func:`find_blender_executable`.

    .. deprecated:: Use :func:`find_blender_executable` instead.
    """
    return find_blender_executable(settings)
