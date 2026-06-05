"""
Safe MeshStager repo-root cleanup — dry-run by default, archive before delete.

Moves clutter into ``_archive_cleanup_2026-06-03/`` at the repository root.
Source trees, active RC2 handoff, and working ``.venv`` are never moved unless
you pass ``--include-venv`` (not recommended while developing).

Usage (from repo root)::

    python scripts/cleanup_repo_root.py
    python scripts/cleanup_repo_root.py --apply
    python scripts/cleanup_repo_root.py --apply --include-venv
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("cleanup_repo_root")

REPO_ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_DIR_NAME = "_archive_cleanup_2026-06-03"
ARCHIVE_ROOT = REPO_ROOT / ARCHIVE_DIR_NAME

# Never move these top-level directories (entire tree protected).
PROTECTED_TOP_DIRS: frozenset[str] = frozenset(
    {
        "meshcorral",
        "scripts",
        "docs",
        "blender_worker",
        "handoff",
    }
)

# Active RC2 handoff paths (under handoff/) — never move.
HANDOFF_RC2_KEEP: frozenset[str] = frozenset(
    {
        "MeshStager_RC2_Performance_Diagnostics_2026-06-01",
        "MeshStager_RC2_Performance_Diagnostics_2026-06-01.zip",
        "templates",
    }
)

# Top-level names always kept at repo root.
KEEP_TOP_FILES: frozenset[str] = frozenset(
    {
        ".gitignore",
        "requirements.txt",
        "requirements-dev.txt",
        "launch.bat",
        "build.bat",
        "build_exe.bat",
        "MeshStager.spec",
        "project.json",
        "README.md",
        "README_FIRST.txt",
        "QUICK_QA_CHECKLIST.md",
        "TESTER_MESSAGE.txt",
        "HANDOFF_RC2_STATUS.md",
        "run_frozen.py",
        "meshcorral.ico",
    }
)

# Entire top-level directories to archive when present.
ARCHIVE_TOP_DIRS: frozenset[str] = frozenset(
    {
        ".pytest_cache",
        "build",
        "dist",
        "dist_installer",
        "installer",
        "TestSource",
        "TestDestination",
        ".venv.broken_20260601_134404",
    }
)

# Top-level glob-style files to archive.
ARCHIVE_TOP_FILE_SUFFIXES: tuple[str, ...] = (".log",)
ARCHIVE_TOP_FILE_NAMES: frozenset[str] = frozenset(
    {
        "MeshCorral_v0.1.0_portable.zip",
        "Roundup_v0.1.0-rc1_portable.zip",
        "Roundup.spec",
        "BUG_HUNT_v0.1.md",
        "RELEASE_NOTES_v0.1.md",
        "TESTER_HANDOFF_RC1.md",
        "Mesh_Corral.png",
        "Mesh_corral_icon.png",
    }
)

# Under handoff/, move these (legacy RC1) into archive/handoff_legacy/
HANDOFF_ARCHIVE_NAMES: frozenset[str] = frozenset(
    {
        "MeshStager_Clean_Handoff_2026-06-01",
        "MeshStager_Clean_Handoff_2026-06-01.zip",
    }
)


@dataclass
class CleanupPlan:
    """Collected move operations."""

    to_move: list[tuple[Path, Path]] = field(default_factory=list)
    skipped_protected: list[str] = field(default_factory=list)
    skipped_missing: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _is_protected_top_dir(name: str) -> bool:
    return name in PROTECTED_TOP_DIRS


def _should_keep_top_file(path: Path) -> bool:
    name = path.name
    if name in KEEP_TOP_FILES:
        return True
    if name == "cleanup_repo_root.py":
        return True
    if name.startswith(".") and name not in {".gitignore"}:
        return False
    return False


def _archive_dest_for(source: Path) -> Path:
    """Map *source* under REPO_ROOT to a path under ARCHIVE_ROOT."""
    try:
        rel = source.relative_to(REPO_ROOT)
    except ValueError:
        rel = Path(source.name)
    return ARCHIVE_ROOT / rel


def _plan_handoff_legacy(plan: CleanupPlan) -> None:
    handoff = REPO_ROOT / "handoff"
    if not handoff.is_dir():
        return
    for entry in sorted(handoff.iterdir(), key=lambda p: p.name.lower()):
        name = entry.name
        if name in HANDOFF_RC2_KEEP:
            plan.skipped_protected.append(f"handoff/{name}")
            continue
        if name in HANDOFF_ARCHIVE_NAMES:
            dest = ARCHIVE_ROOT / "handoff_legacy" / name
            plan.to_move.append((entry, dest))
        elif entry.is_dir() and name not in HANDOFF_RC2_KEEP:
            plan.skipped_protected.append(
                f"handoff/{name} (not in archive list — review manually)"
            )


def _plan_root_entries(plan: CleanupPlan, *, include_venv: bool) -> None:
    if not REPO_ROOT.is_dir():
        plan.errors.append(f"Repo root does not exist: {REPO_ROOT}")
        return

    for child in sorted(REPO_ROOT.iterdir(), key=lambda p: p.name.lower()):
        name = child.name
        if name == ARCHIVE_DIR_NAME:
            plan.skipped_protected.append(name)
            continue
        if _is_protected_top_dir(name):
            plan.skipped_protected.append(name + "/")
            continue
        if child.is_file() and _should_keep_top_file(child):
            plan.skipped_protected.append(name)
            continue
        if name == ".venv":
            if include_venv:
                plan.to_move.append((child, _archive_dest_for(child)))
            else:
                plan.skipped_protected.append(
                    ".venv/ (skipped — working venv; use --include-venv to archive)"
                )
            continue
        if child.is_dir() and name in ARCHIVE_TOP_DIRS:
            plan.to_move.append((child, _archive_dest_for(child)))
            continue
        if child.is_file():
            if name in ARCHIVE_TOP_FILE_NAMES:
                plan.to_move.append((child, _archive_dest_for(child)))
                continue
            if any(name.endswith(suf) for suf in ARCHIVE_TOP_FILE_SUFFIXES):
                plan.to_move.append((child, _archive_dest_for(child)))
                continue
        if child.is_dir() and name == "__pycache__":
            plan.to_move.append((child, _archive_dest_for(child)))


def build_plan(*, include_venv: bool) -> CleanupPlan:
    plan = CleanupPlan()
    _plan_root_entries(plan, include_venv=include_venv)
    _plan_handoff_legacy(plan)
    return plan


def _unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    stem = dest.name
    parent = dest.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_dup{counter}"
        if not candidate.exists():
            return candidate
        counter += 1


def apply_plan(plan: CleanupPlan) -> int:
    """Execute moves. Returns count of successful moves."""
    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    moved = 0
    for src, dest in plan.to_move:
        if not src.exists():
            plan.skipped_missing.append(str(src.relative_to(REPO_ROOT)))
            continue
        dest = _unique_dest(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(src), str(dest))
            logger.info("Moved: %s -> %s", src.relative_to(REPO_ROOT), dest.relative_to(REPO_ROOT))
            moved += 1
        except OSError as exc:
            msg = f"Failed to move {src}: {exc}"
            logger.error(msg)
            plan.errors.append(msg)
    return moved


def write_report(plan: CleanupPlan, *, applied: bool) -> Path:
    ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
    report_path = ARCHIVE_ROOT / "CLEANUP_REPORT.md"
    lines = [
        f"# MeshStager Root Cleanup Report — {date.today().isoformat()}",
        "",
        f"- **Repo root:** `{REPO_ROOT}`",
        f"- **Archive folder:** `{ARCHIVE_ROOT}`",
        f"- **Mode:** {'APPLIED' if applied else 'DRY-RUN'}",
        "",
        "## Summary",
        "",
        f"- **Planned moves:** {len(plan.to_move)}",
        f"- **Protected (skipped):** {len(plan.skipped_protected)}",
        f"- **Errors:** {len(plan.errors)}",
        "",
        "## Items to move (or moved)",
        "",
    ]
    if plan.to_move:
        for src, dest in plan.to_move:
            try:
                rel_src = src.relative_to(REPO_ROOT)
            except ValueError:
                rel_src = src
            try:
                rel_dest = dest.relative_to(REPO_ROOT)
            except ValueError:
                rel_dest = dest
            lines.append(f"- `{rel_src}` → `{rel_dest}`")
    else:
        lines.append("- (none)")
    lines.extend(
        [
            "",
            "## Protected (not touched)",
            "",
        ]
    )
    for item in plan.skipped_protected:
        lines.append(f"- `{item}`")
    if plan.skipped_missing:
        lines.extend(["", "## Missing at apply time", ""])
        for item in plan.skipped_missing:
            lines.append(f"- `{item}`")
    if plan.errors:
        lines.extend(["", "## Errors", ""])
        for item in plan.errors:
            lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## Verify after apply",
            "",
            "```bat",
            "python scripts\\comprehensive_stress_test.py --quick --cleanup",
            "launch.bat",
            "```",
            "",
            "Confirm RC2 handoff still present:",
            "",
            "- `handoff/MeshStager_RC2_Performance_Diagnostics_2026-06-01/`",
            "- `handoff/MeshStager_RC2_Performance_Diagnostics_2026-06-01.zip`",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def run_cleanup(*, apply: bool, include_venv: bool) -> int:
    if ARCHIVE_ROOT.exists() and apply:
        if any(ARCHIVE_ROOT.iterdir()) and not (ARCHIVE_ROOT / "CLEANUP_REPORT.md").exists():
            logger.warning(
                "Archive folder already exists with content: %s", ARCHIVE_ROOT
            )

    plan = build_plan(include_venv=include_venv)
    print("")
    print("=" * 60)
    print("MeshStager root cleanup —", "APPLY" if apply else "DRY-RUN")
    print("=" * 60)
    print(f"Repo:    {REPO_ROOT}")
    print(f"Archive: {ARCHIVE_ROOT}")
    print(f"Moves:   {len(plan.to_move)}")
    print(f"Protected: {len(plan.skipped_protected)}")
    print("")

    if plan.to_move:
        print("Will move:")
        for src, dest in plan.to_move:
            print(f"  {src.relative_to(REPO_ROOT)}")
            print(f"    -> {dest.relative_to(REPO_ROOT)}")
    else:
        print("No items scheduled to move.")

    print("")
    print("Protected (sample):")
    for item in plan.skipped_protected[:15]:
        print(f"  {item}")
    if len(plan.skipped_protected) > 15:
        print(f"  ... and {len(plan.skipped_protected) - 15} more")

    if apply:
        moved = apply_plan(plan)
        print("")
        print(f"Applied {moved} move(s).")
    else:
        print("")
        print("Dry-run only. Re-run with --apply to move items into the archive folder.")

    report = write_report(plan, applied=apply)
    print(f"Report: {report}")
    print("=" * 60)

    if plan.errors:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safe MeshStager repo-root cleanup")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually move items into _archive_cleanup_2026-06-03/ (default is dry-run)",
    )
    parser.add_argument(
        "--include-venv",
        action="store_true",
        help="Also archive .venv/ (not recommended while actively developing)",
    )
    args = parser.parse_args(argv)
    return run_cleanup(apply=bool(args.apply), include_venv=bool(args.include_venv))


if __name__ == "__main__":
    raise SystemExit(main())
