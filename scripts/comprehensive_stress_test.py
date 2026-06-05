"""
Fast automated smoke tests for MeshStager handoff verification.

Usage (from repo / handoff root)::

    python scripts/comprehensive_stress_test.py --quick --cleanup

``--quick`` runs a curated subset of unit tests (no full GUI sign-off).
``--cleanup`` removes temporary directories created by this script.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("comprehensive_stress_test")

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Fast, mostly non-interactive modules (no long Prime sign-off).
QUICK_TEST_MODULES: tuple[str, ...] = (
    "meshcorral.tests.test_rebrand_smoke",
    "meshcorral.tests.test_dialog_placement",
    "meshcorral.tests.test_thumbnail_quality_regression",
    "meshcorral.tests.test_gallery_scroll_perf",
    "meshcorral.tests.test_scanner_lightweight",
    "meshcorral.tests.test_scanner_allowed_extensions",
    "meshcorral.tests.test_validators",
    "meshcorral.tests.test_asset_mode_config",
    "meshcorral.tests.test_file_record_name_lower",
    "meshcorral.tests.test_move_service",
    "meshcorral.tests.test_data_migration",
    "meshcorral.tests.test_settings_service",
    "meshcorral.tests.test_search_service",
)

_TEMP_MARKERS = ("meshstager_stress_", "roundup_stress_", "meshcorral_stress_")


def _run_quick_tests() -> bool:
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    errors: list[str] = []

    for name in QUICK_TEST_MODULES:
        try:
            suite.addTests(loader.loadTestsFromName(name))
        except Exception as exc:  # noqa: BLE001 — collect all import/load failures
            errors.append(f"{name}: {exc}")

    if errors:
        for msg in errors:
            logger.error("Failed to load tests: %s", msg)
        return False

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        logger.error(
            "Quick tests finished: failures=%s errors=%s",
            len(result.failures),
            len(result.errors),
        )
    return result.wasSuccessful()


def _cleanup_temp_dirs() -> int:
    removed = 0
    for base in (Path(tempfile.gettempdir()), REPO_ROOT):
        if not base.is_dir():
            continue
        try:
            for child in base.iterdir():
                if not child.is_dir():
                    continue
                if any(marker in child.name for marker in _TEMP_MARKERS):
                    shutil.rmtree(child, ignore_errors=True)
                    logger.info("Removed temp dir: %s", child)
                    removed += 1
        except OSError as exc:
            logger.warning("Cleanup skip %s: %s", base, exc)
    return removed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MeshStager quick stress / smoke tests")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run fast unit-test subset (default when no other mode given)",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Remove temp directories created for stress testing",
    )
    args = parser.parse_args(argv)

    if not args.quick and not args.cleanup:
        args.quick = True

    ok = True
    if args.quick:
        logger.info("Running quick test modules (%d)...", len(QUICK_TEST_MODULES))
        ok = _run_quick_tests()

    if args.cleanup:
        count = _cleanup_temp_dirs()
        logger.info("Cleanup removed %d temp director(ies).", count)

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
