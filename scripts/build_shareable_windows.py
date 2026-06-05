"""
Build a shareable portable Windows ZIP for MeshStager (RC3 Beta).

This script is packaging-only:
- does not modify app behavior
- does not change render/gallery/scan logic
- does not add new dependencies

Outputs are written under ``release/`` and are gitignored.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "dist"
SPEC_PYI = REPO_ROOT / "MeshStager.spec"
DIST_APP_DIR = DIST_DIR / "MeshStager"
RELEASE_DIR = REPO_ROOT / "release"


def _venv_python() -> Path | None:
    """Prefer repo venv python when present (for tests / validation)."""
    venv_py = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_py.is_file():
        return venv_py
    return None


def _python_has_module(python: Path, module: str) -> bool:
    """Best-effort check (no stderr parsing assumptions)."""
    code, _out = _run([str(python), "-c", f"import {module}"], cwd=REPO_ROOT)
    return code == 0


def _run(cmd: list[str], *, cwd: Path) -> tuple[int, str]:
    """Run a subprocess and return (exit_code, captured_output)."""
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


def _git_commit_hash() -> str:
    code, out = _run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT)
    if code != 0:
        return "unknown"
    return out.strip().splitlines()[-1] if out.strip() else "unknown"


def _git_repo_clean_status_line() -> str:
    code, out = _run(["git", "status", "--porcelain"], cwd=REPO_ROOT)
    if code != 0:
        return "status: unknown"
    return f"status: {'clean' if not out.strip() else 'dirty'}"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _zip_dir(src_dir: Path, zip_path: Path) -> None:
    """Create a ZIP with paths relative to src_dir parent."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    if zip_path.exists():
        zip_path.unlink()

    base = src_dir.parent
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in src_dir.rglob("*"):
            if file_path.is_file():
                rel = file_path.relative_to(base)
                zf.write(str(file_path), str(rel))


def _quick_validate(python: Path) -> tuple[bool, str]:
    """
    Lightweight validation before build.

    Keeps build pipeline responsive while still catching common regressions.
    """
    # Small suite: gallery scroll + thumbnail quality tier policy.
    tests = [
        "meshcorral.tests.test_gallery_scroll_perf",
        "meshcorral.tests.test_thumbnail_quality_regression",
        "meshcorral.tests.test_gallery_list_model",
    ]
    cmd = [str(python), "-m", "unittest"] + tests
    code, out = _run(cmd, cwd=REPO_ROOT)
    ok = code == 0
    return ok, out[-5000:]


def _build_with_pyinstaller(python: Path) -> tuple[int, str]:
    """
    Build portable onedir output to ``dist/MeshStager/``.

    Uses the existing MeshStager.spec and matches scripts/build_exe.bat flags.
    """
    icon_path = REPO_ROOT / "assets" / "icons" / "MeshStager_icon.ico"
    cmd = [
        str(python),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        "MeshStager",
        "--icon",
        str(icon_path),
        "--paths",
        ".",
        "run_frozen.py",
    ]
    # build_exe.bat uses run_frozen.py (spec-less). Keep same to preserve behavior.
    return _run(cmd, cwd=REPO_ROOT)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version",
        default="v0.1.0-rc3",
        help="Release version label (defaults to v0.1.0-rc3).",
    )
    parser.add_argument(
        "--skip-validate-quick",
        action="store_true",
        help="Skip quick unit validation before the PyInstaller build.",
    )
    args = parser.parse_args()

    version = (args.version or "").strip() or "v0.1.0-rc3"
    tests_python = _venv_python() or Path(sys.executable)
    pyi_python = tests_python

    # IMPORTANT: this script is commonly executed with the repo venv python, so
    # ``sys.executable`` may point at the venv (which might not have PyInstaller).
    # For the build step, prefer the `python` on PATH.
    python_on_path = shutil.which("python")
    python_on_path_path = Path(python_on_path) if python_on_path else Path(sys.executable)

    if not _python_has_module(pyi_python, "PyInstaller"):
        if _python_has_module(python_on_path_path, "PyInstaller"):
            pyi_python = python_on_path_path
        else:
            pyi_python = python_on_path_path

    if not SPEC_PYI.is_file():
        # Spec is present in this repo; keep a soft failure with clear message.
        print(f"WARNING: {SPEC_PYI} not found (continuing with run_frozen build).")

    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    out_portable_dir = RELEASE_DIR / f"MeshStager_{version}_Windows_Portable"
    zip_path = RELEASE_DIR / f"MeshStager_{version}_Windows_Portable.zip"
    sha_path = RELEASE_DIR / f"MeshStager_{version}_Windows_Portable.sha256.txt"

    # Clean previous output (gitignored; safe for repeated runs).
    if out_portable_dir.exists():
        shutil.rmtree(out_portable_dir)
    out_portable_dir.mkdir(parents=True, exist_ok=True)

    # Validation (optional).
    test_status = "skipped"
    validate_ok = True
    if not args.skip_validate_quick:
        validate_ok, validate_out = _quick_validate(tests_python)
        test_status = "PASS" if validate_ok else "FAIL"
        if not validate_ok:
            sys.stderr.write(validate_out)
            print("Quick validation failed; aborting build.")
            return 1

    # Build.
    print("Building MeshStager (PyInstaller onedir)...")
    build_code, build_out = _build_with_pyinstaller(pyi_python)
    if build_code != 0:
        sys.stderr.write(build_out)
        print("Build failed.")
        return build_code

    if not DIST_APP_DIR.is_dir():
        print(f"ERROR: expected dist output at {DIST_APP_DIR} not found.")
        return 2

    # Copy PyInstaller onedir output as MeshStager/ (exe + _internal + deps).
    app_dest = out_portable_dir / "MeshStager"
    if app_dest.exists():
        shutil.rmtree(app_dest)
    shutil.copytree(DIST_APP_DIR, app_dest)

    # Root-level docs and license.
    def _copy_if_exists(rel: str, dst: Path) -> None:
        src = REPO_ROOT / rel
        if src.is_file():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    _copy_if_exists("README.md", out_portable_dir / "README.md")
    _copy_if_exists("LICENSE", out_portable_dir / "LICENSE")

    docs_dest = out_portable_dir / "docs"
    docs_dest.mkdir(parents=True, exist_ok=True)
    for doc_name in (
        "GITHUB_QUICK_START.md",
        "SAMPLE_DATA_POLICY.md",
        "QUICK_QA_CHECKLIST.md",
    ):
        _copy_if_exists(f"docs/{doc_name}", docs_dest / doc_name)

    start_here = out_portable_dir / "START_HERE.txt"
    start_here.write_text(
        "\n".join(
            [
                f"MeshStager {version} — Windows Portable",
                "",
                "1) Extract this ZIP to a writeable folder (example: C:\\MeshStager_Test)",
                "2) Run: MeshStager\\MeshStager.exe",
                "",
                "Smoke checklist before sharing:",
                "  - MeshStager.exe launches",
                "  - Header/title/taskbar icon appears",
                "  - Settings opens centered, resizable, Save/Cancel visible",
                "  - Scan a small local STL/OBJ folder",
                "  - Balanced thumbnails are readable",
                "  - Sort by Type works",
                "  - Large/network behavior does not lock up",
                "",
                "User data (settings, caches) is stored outside this folder:",
                "  %LOCALAPPDATA%\\MeshStager\\",
                "",
                "See docs/GITHUB_QUICK_START.md for more detail.",
            ]
        ),
        encoding="utf-8",
    )

    commit = _git_commit_hash()
    build_date = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    version_file = out_portable_dir / "VERSION.txt"
    version_file.write_text(
        "\n".join(
            [
                f"Version: {version}",
                f"Commit: {commit}",
                _git_repo_clean_status_line(),
                f"Build date: {build_date}",
                f"Quick validation: {test_status}",
            ]
        ),
        encoding="utf-8",
    )

    # Zip + sha256.
    print(f"Creating ZIP: {zip_path}")
    _zip_dir(out_portable_dir, zip_path)
    sha = _sha256_file(zip_path)
    sha_path.write_text(sha + "\n", encoding="utf-8")

    # Keep the console output readable.
    print("Portable build complete.")
    print(f"build folder: {out_portable_dir}")
    print(f"zip path: {zip_path}")
    print(f"sha256 path: {sha_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

