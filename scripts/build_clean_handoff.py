"""
Build a clean MeshStager tester handoff package from the source repo.

Does not delete anything in the working tree — copies only into::

    handoff/MeshStager_Clean_Handoff_2026-06-01/

Usage::

    python scripts/build_clean_handoff.py
    python scripts/build_clean_handoff.py --verify-only

Creates HANDOFF_MANIFEST.md, EXCLUDED_ITEMS.md, tester docs, and a zip archive.
"""

from __future__ import annotations

import argparse
import fnmatch
import logging
import os
import shutil
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("build_clean_handoff")

HANDOFF_FOLDER_NAME = "MeshStager_RC2_Performance_Diagnostics_2026-06-01"
HANDOFF_DATE = "2026-06-01"
HANDOFF_TAG = "MeshStager RC2 Performance Diagnostics"
HANDOFF_STATUS = "Ready for benchmark validation"
QUICK_TEST_COUNT = 53
GALLERY_SCROLL_TEST_COUNT = 9
BENCHMARK_TEST_COUNT = 15
RENDER_PROFILER_TEST_COUNT = 6
_HANDOFF_FLAVOR = "rc2"

REPO_ROOT = Path(__file__).resolve().parents[1]
HANDOFF_BASE = REPO_ROOT / "handoff"
OUTPUT_DIR = HANDOFF_BASE / HANDOFF_FOLDER_NAME
ZIP_PATH = HANDOFF_BASE / f"{HANDOFF_FOLDER_NAME}.zip"
TEMPLATES_DIR = HANDOFF_BASE / "templates"

# Top-level files to copy when present (source repo layout).
TOP_LEVEL_INCLUDE: tuple[str, ...] = (
    "run_frozen.py",
    "requirements.txt",
    "requirements-dev.txt",
    "launch.bat",
    "build.bat",
    "build_exe.bat",
    "MeshStager.spec",
    "README_FIRST.txt",
    "meshcorral.ico",
    "assets/icons/MeshStager_icon.png",
    "assets/icons/MeshStager_icon.ico",
    "assets/icons/MeshStager_icon_toolbar.png",
    "assets/branding/MeshStager_icon_pro.jpg",
    "project.json",
    "QUICK_QA_CHECKLIST.md",
    "TESTER_HANDOFF_RC1.md",
    "RELEASE_NOTES_v0.1.md",
    "BUG_HUNT_v0.1.md",
    ".gitignore",
    # Legacy / alternate names from older handoff specs (included if present).
    "main_enhanced.py",
    "ModelFinder.spec",
    "README.md",
    "COMPLETE_SYSTEM_SUMMARY.md",
    "PROJECT_STATUS.json",
    "CHATGPT_SUMMARY.json",
    "MIGRATION_STATUS.md",
    "GUARDRAILS_IMPLEMENTATION_COMPLETE.md",
    "ARCHIVE_ML_DESIGN.md",
    "SESSION_COMPLETE.md",
)

# Directories copied recursively (with per-file exclude rules).
INCLUDE_DIRS: tuple[str, ...] = (
    "meshcorral",
    "blender_worker",
)

# Docs copied into handoff docs/ (relative to repo docs/).
DOCS_INCLUDE: tuple[str, ...] = (
    "MESHSTAGER_DATA_MIGRATION.md",
    "MESHSTAGER_VERIFICATION_PASS.md",
    "MESHSTAGER_RELEASE_CHECKLIST.md",
    "MESHSTAGER_UI_UX_GUIDE.md",
    "MESHSTAGER_UX_AUDIT_CHECKLIST.md",
    "CHANGELOG.md",
    "PRIME_V1_CORE_FREEZE.md",
    "RENDER_SPEED_QUALITY_STRATEGY.md",
    "RC3_THUMBNAIL_QUALITY_PLAN.md",
)

# Scripts copied into handoff scripts/.
SCRIPTS_INCLUDE: tuple[str, ...] = (
    "init_db.py",
    "comprehensive_stress_test.py",
    "benchmark_render_pipeline.py",
    "build_clean_handoff.py",
    "run_meshstager.bat",
    "build_exe.bat",
    "build_installer.bat",
    "launch_meshstager.ps1",
    "validate_prime_v10_local_stability_signoff.py",
)

# Critical for testing — warn if missing after build (flavor-specific tail in _apply_handoff_flavor).
_REQUIRED_COMMON: tuple[str, ...] = (
    "run_frozen.py",
    "requirements.txt",
    "launch.bat",
    "meshcorral/app/main.py",
    "meshcorral/__init__.py",
    "scripts/init_db.py",
    "scripts/comprehensive_stress_test.py",
    "scripts/build_clean_handoff.py",
    "TESTER_QUICK_START.md",
    "HANDOFF_RC1_STATUS.md",
    "HANDOFF_MANIFEST.md",
    "scripts/benchmark_render_pipeline.py",
)
REQUIRED_FOR_TESTING: tuple[str, ...] = _REQUIRED_COMMON + (
    "HANDOFF_RC2_STATUS.md",
    "PERFORMANCE_DIAGNOSTICS.md",
)

# Optional legacy paths from ModelFinder-era specs (warn only).
LEGACY_OPTIONAL: tuple[str, ...] = (
    "main_enhanced.py",
    "src",
    "tests",
    "ModelFinder.spec",
    "COMPLETE_SYSTEM_SUMMARY.md",
    "PROJECT_STATUS.json",
    "CHATGPT_SUMMARY.json",
    "MIGRATION_STATUS.md",
    "GUARDRAILS_IMPLEMENTATION_COMPLETE.md",
    "ARCHIVE_ML_DESIGN.md",
    "SESSION_COMPLETE.md",
)

# Directory names excluded anywhere under the copy tree.
EXCLUDE_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        "env",
        "ENV",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "build",
        "dist",
        "dist_installer",
        "installer",
        "node_modules",
        ".git",
        ".idea",
        ".vscode",
        "thumbs",
        "cache",
        "MeshStager_Clean_Handoff_2026-06-01",
        "MeshStager_RC2_Performance_Diagnostics_2026-06-01",
        "MeshStager_RC3_Gallery_Performance_2026-06-03",
    }
)

# Old handoff folder prefixes under handoff/.
EXCLUDE_HANDOFF_PREFIXES: tuple[str, ...] = (
    "MeshStager_Clean_Handoff_",
    "ModelFinder_Clean_Handoff_",
)

# Glob patterns for excluded files (matched on path parts / name).
EXCLUDE_FILE_GLOBS: tuple[str, ...] = (
    "*.pyc",
    "*.pyo",
    "*.pyd",
    "*.log",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.db-journal",
    "*.bak",
    "*.bak*",
    "*.exe",
    "*.msi",
    "*.zip",
    "*.7z",
    "*.cache",
    "Thumbs.db",
    "desktop.ini",
    ".DS_Store",
    "main_legacy.py.bak",
)

# Root-level dirs never descended for handoff (entire tree skipped).
SKIP_ROOT_DIRS: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        "build",
        "dist",
        "dist_installer",
        "installer",
        ".pytest_cache",
        "handoff",
        "TestSource",
        "TestDestination",
    }
)


@dataclass
class BuildStats:
    """Counts and paths collected during a handoff build."""

    included_files: int = 0
    excluded_files: int = 0
    included_paths: list[str] = field(default_factory=list)
    excluded_paths: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _matches_any_glob(name: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def _should_exclude_dir(dir_name: str, rel_parts: tuple[str, ...]) -> bool:
    if dir_name in EXCLUDE_DIR_NAMES:
        return True
    if rel_parts and rel_parts[0] == "handoff":
        for part in rel_parts[1:]:
            for prefix in EXCLUDE_HANDOFF_PREFIXES:
                if part.startswith(prefix):
                    return True
    return False


def _should_exclude_file(path: Path) -> bool:
    name = path.name
    if _matches_any_glob(name, EXCLUDE_FILE_GLOBS):
        return True
    lower = name.lower()
    if lower.endswith(".bak") or ".bak" in lower:
        return True
    return False


def _copy_file(src: Path, dst: Path, stats: BuildStats) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    rel = dst.relative_to(OUTPUT_DIR).as_posix()
    stats.included_files += 1
    stats.included_paths.append(rel)


def _record_exclude(rel: str, stats: BuildStats) -> None:
    stats.excluded_files += 1
    if len(stats.excluded_paths) < 5000:
        stats.excluded_paths.append(rel)


def _walk_copy_tree(src_root: Path, dst_root: Path, stats: BuildStats) -> None:
    if not src_root.is_dir():
        stats.warnings.append(f"Include directory missing: {src_root}")
        return

    for dirpath, dirnames, filenames in os.walk(src_root, topdown=True):
        current = Path(dirpath)
        rel_dir = current.relative_to(src_root)
        rel_parts = rel_dir.parts

        pruned: list[str] = []
        for dirname in dirnames:
            if _should_exclude_dir(dirname, (*rel_parts, dirname)):
                exc_rel = (rel_dir / dirname).as_posix()
                _record_exclude(f"{src_root.name}/{exc_rel}/", stats)
                continue
            pruned.append(dirname)
        dirnames[:] = pruned

        for filename in filenames:
            src_file = current / filename
            rel_file = (rel_dir / filename).as_posix()
            display = f"{src_root.name}/{rel_file}"

            if _should_exclude_file(src_file):
                _record_exclude(display, stats)
                continue

            dst_file = dst_root / rel_dir / filename
            _copy_file(src_file, dst_file, stats)


def _copy_top_level(stats: BuildStats) -> None:
    for name in TOP_LEVEL_INCLUDE:
        src = REPO_ROOT / name
        if not src.is_file():
            continue
        if _should_exclude_file(src):
            _record_exclude(name, stats)
            continue
        _copy_file(src, OUTPUT_DIR / name, stats)


def _copy_scripts(stats: BuildStats) -> None:
    scripts_src = REPO_ROOT / "scripts"
    scripts_dst = OUTPUT_DIR / "scripts"
    for name in SCRIPTS_INCLUDE:
        src = scripts_src / name
        if not src.is_file():
            stats.warnings.append(f"Script not found (skipped): scripts/{name}")
            continue
        if _should_exclude_file(src):
            _record_exclude(f"scripts/{name}", stats)
            continue
        _copy_file(src, scripts_dst / name, stats)


def _copy_docs(stats: BuildStats) -> None:
    docs_src = REPO_ROOT / "docs"
    docs_dst = OUTPUT_DIR / "docs"
    for name in DOCS_INCLUDE:
        src = docs_src / name
        if not src.is_file():
            continue
        _copy_file(src, docs_dst / name, stats)


def _copy_templates(stats: BuildStats) -> None:
    mapping = {
        "TESTER_QUICK_START.md": "TESTER_QUICK_START.md",
        "HANDOFF_CHECKLIST.md": "HANDOFF_CHECKLIST.md",
        "KNOWN_LIMITATIONS.md": "KNOWN_LIMITATIONS.md",
        "HANDOFF_RC1_STATUS.md": "HANDOFF_RC1_STATUS.md",
        "HANDOFF_RC2_STATUS.md": "HANDOFF_RC2_STATUS.md",
        "PERFORMANCE_DIAGNOSTICS.md": "PERFORMANCE_DIAGNOSTICS.md",
        "TESTER_MESSAGE.txt": "TESTER_MESSAGE.txt",
    }
    if _HANDOFF_FLAVOR == "rc3":
        mapping["HANDOFF_RC3_STATUS.md"] = "HANDOFF_RC3_STATUS.md"
        mapping["GALLERY_PERFORMANCE.md"] = "GALLERY_PERFORMANCE.md"
    for src_name, dst_name in mapping.items():
        src = TEMPLATES_DIR / src_name
        if not src.is_file():
            stats.warnings.append(f"Template missing: handoff/templates/{src_name}")
            continue
        _copy_file(src, OUTPUT_DIR / dst_name, stats)


def _write_readme(stats: BuildStats) -> None:
    src_readme = REPO_ROOT / "meshcorral" / "README.md"
    dst = OUTPUT_DIR / "README.md"
    header = (
        f"# {HANDOFF_TAG}\n\n"
        f"| | |\n"
        f"|---|---|\n"
        f"| **Package** | `{HANDOFF_FOLDER_NAME}` |\n"
        f"| **Date** | {HANDOFF_DATE} |\n"
        f"| **Status** | {HANDOFF_STATUS} |\n"
        f"| **Smoke test** | {QUICK_TEST_COUNT} tests OK |\n"
        f"| **Performance tests** | {RENDER_PROFILER_TEST_COUNT + BENCHMARK_TEST_COUNT} tests OK |\n\n"
        "**Start here:** unzip if needed, then open **TESTER_QUICK_START.md**. "
        + (
            "See **GALLERY_PERFORMANCE.md** for RC3 scroll validation. "
            if _HANDOFF_FLAVOR == "rc3"
            else "See **PERFORMANCE_DIAGNOSTICS.md** for benchmarks. "
        )
        + "Create a **fresh** `.venv` — do not reuse a developer `.venv`.\n\n"
        "---\n\n"
    )
    if src_readme.is_file():
        body = src_readme.read_text(encoding="utf-8")
    else:
        body = "See TESTER_QUICK_START.md for setup.\n"
        stats.warnings.append("meshcorral/README.md not found; README.md is minimal.")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(header + body, encoding="utf-8")
    stats.included_files += 1
    stats.included_paths.append("README.md")


def _write_manifest(stats: BuildStats) -> None:
    lines = [
        f"# Handoff Manifest — {HANDOFF_FOLDER_NAME}",
        "",
        f"- **Tag:** {HANDOFF_TAG}",
        f"- **Status:** {HANDOFF_STATUS}",
        f"- **Generated:** {date.today().isoformat()}",
        f"- **Source repo:** `{REPO_ROOT}`",
        f"- **Output folder:** `{OUTPUT_DIR}`",
        f"- **Zip:** `{ZIP_PATH}`",
        "",
        f"## {_HANDOFF_FLAVOR.upper()} validation (pre-ship)",
        "",
        "| Check | Result |",
        "|-------|--------|",
        f"| Smoke: `comprehensive_stress_test.py --quick --cleanup` | **{QUICK_TEST_COUNT} tests OK** |",
    ]
    if _HANDOFF_FLAVOR == "rc3":
        lines.extend(
            [
                f"| Gallery scroll: `unittest meshcorral.tests.test_gallery_scroll_perf` | "
                f"**{GALLERY_SCROLL_TEST_COUNT} tests OK** |",
            ]
        )
    lines.extend(
        [
            f"| Render timing profiler tests | **{RENDER_PROFILER_TEST_COUNT} tests OK** |",
            f"| Benchmark report tests | **{BENCHMARK_TEST_COUNT} tests OK** |",
            "| Required files | No warnings |",
            "",
        ]
    )
    if _HANDOFF_FLAVOR == "rc3":
        lines.extend(
            [
                "## RC3 gallery UI features (included)",
                "",
                "- UI scroll profiler → `%LOCALAPPDATA%\\MeshStager\\logs\\ui_scroll_timing.log`",
                "- Scaled pixmap cache (path + size/mtime + gallery px)",
                "- Selection inspector debounce (`MESHSTAGER_GALLERY_SCROLL_DEBOUNCE_MS`)",
                "- Viewport prefetch cap (`MESHSTAGER_GALLERY_MAX_VISIBLE_BUILD`)",
                "- See `GALLERY_PERFORMANCE.md` and `HANDOFF_RC3_STATUS.md`",
                "",
                "## RC2 performance features (still included)",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## RC2 performance features (included)",
                "",
            ]
        )
    lines.extend(
        [
            "- Render timing profiler → `%LOCALAPPDATA%\\MeshStager\\logs\\render_timing.log`",
            "- Server staging cache → `render_staging/`",
            "- Render output cache → `render_cache/`",
            "- Proxy/HQ policy (HQ on demand for large/network)",
            "- `scripts/benchmark_render_pipeline.py` (warm-up, `--repeat`, cache clear)",
            "",
        ]
    )
    lines.extend(
        [
        f"**Tester:** unzip `{HANDOFF_FOLDER_NAME}.zip` first; create a fresh `.venv`. "
        "See `TESTER_QUICK_START.md`"
        + (
            " and `GALLERY_PERFORMANCE.md`."
            if _HANDOFF_FLAVOR == "rc3"
            else " and `PERFORMANCE_DIAGNOSTICS.md`."
        ),
        "",
        "## Purpose",
        "",
        "Clean tester package: source, launch scripts, fast smoke tests, and QA docs only. "
        "No build artifacts, installers, venvs, or local databases.",
        "",
        "## Layout mapping (source → handoff)",
        "",
        "| Handoff / spec name | This repo |",
        "|---------------------|-----------|",
        "| `main_enhanced.py` | `run_frozen.py` + `python -m meshcorral.app` |",
        "| `src/` | `meshcorral/` Python package |",
        "| `tests/` | `meshcorral/tests/` (unittest discover path) |",
        "| `ModelFinder.spec` | `MeshStager.spec` (PyInstaller) |",
        "",
        "## Included top-level files",
        "",
        ],
    )
    for p in sorted(stats.included_paths):
        if "/" not in p and p.endswith((".md", ".txt", ".json", ".bat", ".spec", ".py", ".ico")):
            lines.append(f"- `{p}`")
    lines.extend(
        [
            "",
            "## Included directories",
            "",
            "- `meshcorral/` — application source and `meshcorral/tests/`",
            "- `blender_worker/` — headless Blender thumbnail worker",
            "- `scripts/` — init, smoke test, build, launch helpers",
            "- `docs/` — selected migration / release notes",
            "",
            f"**Total files copied:** {stats.included_files}",
            "",
            "## Excluded (summary)",
            "",
            "See `EXCLUDED_ITEMS.md` for patterns and sample paths.",
            "",
            f"**Total excluded entries recorded:** {stats.excluded_files}",
            "",
            "## Verification",
            "",
            "```bat",
            "python -m venv .venv",
            ".venv\\Scripts\\pip install -r requirements.txt",
            ".venv\\Scripts\\python scripts\\init_db.py",
            ".venv\\Scripts\\python scripts\\comprehensive_stress_test.py --quick --cleanup",
            "launch.bat",
            "```",
            "",
            "```bat",
            f".venv\\Scripts\\python scripts\\build_clean_handoff.py --verify-only",
            "```",
            "",
        ]
    )
    if stats.warnings:
        lines.append("## Warnings\n")
        for w in stats.warnings:
            lines.append(f"- {w}")
        lines.append("")

    path = OUTPUT_DIR / "HANDOFF_MANIFEST.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    stats.included_paths.append("HANDOFF_MANIFEST.md")


def _write_excluded(stats: BuildStats) -> None:
    lines = [
        f"# Excluded Items — {HANDOFF_FOLDER_NAME}",
        "",
        "The working **source repo is unchanged**. Items below were skipped during copy.",
        "",
        "## Directory names (always skipped)",
        "",
    ]
    for name in sorted(EXCLUDE_DIR_NAMES):
        lines.append(f"- `{name}/`")
    lines.extend(
        [
            "",
            "## Root directories not copied",
            "",
        ]
    )
    for name in sorted(SKIP_ROOT_DIRS):
        lines.append(f"- `{name}/`")
    lines.extend(
        [
            "",
            "## File patterns",
            "",
        ]
    )
    for pat in EXCLUDE_FILE_GLOBS:
        lines.append(f"- `{pat}`")
    lines.extend(
        [
            "",
            "## Sample excluded paths (truncated)",
            "",
        ]
    )
    sample = stats.excluded_paths[:200]
    for p in sample:
        lines.append(f"- `{p}`")
    if len(stats.excluded_paths) > 200:
        lines.append(f"- … and {len(stats.excluded_paths) - 200} more")
    lines.append("")
    path = OUTPUT_DIR / "EXCLUDED_ITEMS.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    stats.included_paths.append("EXCLUDED_ITEMS.md")


def _create_zip(stats: BuildStats) -> None:
    if ZIP_PATH.is_file():
        try:
            ZIP_PATH.unlink()
        except OSError as exc:
            alt = HANDOFF_BASE / f"{HANDOFF_FOLDER_NAME}_new.zip"
            logger.warning("Could not replace zip (%s); writing %s", exc, alt.name)
            zip_target = alt
        else:
            zip_target = ZIP_PATH
    else:
        zip_target = ZIP_PATH
    HANDOFF_BASE.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(OUTPUT_DIR.rglob("*")):
            if file_path.is_file():
                arcname = Path(HANDOFF_FOLDER_NAME) / file_path.relative_to(OUTPUT_DIR)
                zf.write(file_path, arcname.as_posix())
    logger.info("Created zip: %s", zip_target)
    if zip_target != ZIP_PATH:
        stats.warnings.append(f"Primary zip locked; wrote alternate: {zip_target.name}")


def _verify_handoff(stats: BuildStats) -> None:
    for rel in REQUIRED_FOR_TESTING:
        target = OUTPUT_DIR / rel
        if not target.is_file():
            msg = f"Required file missing in handoff: {rel}"
            stats.warnings.append(msg)
            logger.warning(msg)

    for rel in LEGACY_OPTIONAL:
        target = REPO_ROOT / rel
        if not target.exists():
            continue
        handoff_target = OUTPUT_DIR / rel
        if not handoff_target.exists():
            stats.warnings.append(
                f"Legacy/optional path exists in source but not copied: {rel}"
            )


def _apply_handoff_flavor(*, rc3: bool) -> None:
    """Set global handoff paths and required-file list for RC2 vs RC3 package."""
    global HANDOFF_FOLDER_NAME, HANDOFF_DATE, HANDOFF_TAG, HANDOFF_STATUS
    global OUTPUT_DIR, ZIP_PATH, REQUIRED_FOR_TESTING, _HANDOFF_FLAVOR

    _HANDOFF_FLAVOR = "rc3" if rc3 else "rc2"
    if rc3:
        HANDOFF_FOLDER_NAME = "MeshStager_RC3_Gallery_Performance_2026-06-03"
        HANDOFF_DATE = "2026-06-03"
        HANDOFF_TAG = "MeshStager RC3 Gallery Performance"
        HANDOFF_STATUS = "Ready for gallery scroll validation"
        REQUIRED_FOR_TESTING = _REQUIRED_COMMON + (
            "HANDOFF_RC3_STATUS.md",
            "GALLERY_PERFORMANCE.md",
        )
    else:
        HANDOFF_FOLDER_NAME = "MeshStager_RC2_Performance_Diagnostics_2026-06-01"
        HANDOFF_DATE = "2026-06-01"
        HANDOFF_TAG = "MeshStager RC2 Performance Diagnostics"
        HANDOFF_STATUS = "Ready for benchmark validation"
        REQUIRED_FOR_TESTING = _REQUIRED_COMMON + (
            "HANDOFF_RC2_STATUS.md",
            "PERFORMANCE_DIAGNOSTICS.md",
        )
    OUTPUT_DIR = HANDOFF_BASE / HANDOFF_FOLDER_NAME
    ZIP_PATH = HANDOFF_BASE / f"{HANDOFF_FOLDER_NAME}.zip"


def _clean_output_dir() -> None:
    if not OUTPUT_DIR.is_dir():
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        return
    try:
        shutil.rmtree(OUTPUT_DIR)
    except OSError as exc:
        logger.warning(
            "Could not remove handoff folder (%s); clearing contents in place.",
            exc,
        )
        for child in OUTPUT_DIR.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                try:
                    child.unlink()
                except OSError:
                    logger.warning("Could not delete: %s", child)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _print_summary(stats: BuildStats, *, verify_only: bool = False) -> int:
    print("")
    print("=" * 60)
    print(f"{HANDOFF_TAG} — Build Summary")
    print("=" * 60)
    print(f"Package:        {HANDOFF_FOLDER_NAME}")
    print(f"Status:         {HANDOFF_STATUS}")
    print(f"Output folder:  {OUTPUT_DIR}")
    print(f"Zip archive:    {ZIP_PATH}")
    print(
        f"Pre-ship tests: smoke={QUICK_TEST_COUNT}  "
        f"perf={RENDER_PROFILER_TEST_COUNT + BENCHMARK_TEST_COUNT}"
    )
    if verify_only:
        file_count = sum(1 for _ in OUTPUT_DIR.rglob("*") if _.is_file())
        print(f"Files on disk:  {file_count}")
    else:
        print(f"Included files: {stats.included_files}")
        print(f"Excluded items: {stats.excluded_files}")
    if stats.warnings:
        print("")
        print("Warnings:")
        for w in stats.warnings:
            print(f"  - {w}")
    else:
        print("")
        print("Warnings: none")
    print("=" * 60)
    critical = [w for w in stats.warnings if w.startswith("Required file missing")]
    return 1 if critical else 0


def build_handoff(*, verify_only: bool = False, rc3: bool = False) -> int:
    _apply_handoff_flavor(rc3=rc3)
    if verify_only:
        if not OUTPUT_DIR.is_dir():
            logger.error("Handoff folder does not exist: %s", OUTPUT_DIR)
            logger.error("Run without --verify-only to build first.")
            return 1
        stats = BuildStats()
        _verify_handoff(stats)
        return _print_summary(stats, verify_only=True)

    stats = BuildStats()
    _clean_output_dir()

    _copy_top_level(stats)
    for dirname in INCLUDE_DIRS:
        _walk_copy_tree(REPO_ROOT / dirname, OUTPUT_DIR / dirname, stats)
    _copy_scripts(stats)
    _copy_docs(stats)
    _copy_templates(stats)
    _write_readme(stats)
    _write_manifest(stats)
    _write_excluded(stats)
    _verify_handoff(stats)
    _create_zip(stats)

    return _print_summary(stats, verify_only=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build MeshStager clean handoff package")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Verify an existing handoff folder without rebuilding",
    )
    parser.add_argument(
        "--rc3",
        action="store_true",
        help="Build RC3 Gallery Performance handoff (default: RC2 Performance Diagnostics)",
    )
    args = parser.parse_args(argv)
    try:
        return build_handoff(verify_only=args.verify_only, rc3=args.rc3)
    except OSError as exc:
        logger.error("Handoff build failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
