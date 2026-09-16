"""
Packaging guards for the release build path (no PyInstaller run required).

RC3 shipped a portable ZIP whose ``_internal/`` had no ``scipy``, so the frozen app
reported "Native renderer unavailable: missing SciPy". Three things made that silent
failure possible, and each is pinned here:

* the build interpreter was allowed to be any ``python`` on PATH that had PyInstaller,
  even one without the project's runtime dependencies;
* the release build passed its own PyInstaller flags instead of using ``MeshStager.spec``,
  so nothing declared SciPy, which the app only reaches through a guarded import and
  ``importlib.util.find_spec``;
* the finished bundle was zipped without being checked.

These tests are pure file/spec inspection plus one subprocess import probe, so they stay
cheap enough to run on every release build.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = REPO_ROOT / "MeshStager.spec"
BUILD_SCRIPT_PATH = REPO_ROOT / "scripts" / "build_shareable_windows.py"

# SciPy modules the frozen app must be able to import: the top-level package for
# native_renderer_health / mesh_render_pipeline, and the subpackages trimesh uses.
REQUIRED_SPEC_HIDDEN_IMPORTS = ("scipy", "scipy.sparse", "scipy.sparse.csgraph", "scipy.spatial")

# Flags that would mean the release build had drifted back to its own dependency rules.
SPECLESS_BUILD_FLAGS = ("--onedir", "--windowed", "--name", "--icon", "--paths", "run_frozen.py")


def _load_build_script() -> ModuleType:
    """Import ``scripts/build_shareable_windows.py``, which is not on the package path."""
    spec = importlib.util.spec_from_file_location("_meshstager_build_script", BUILD_SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load build script at {BUILD_SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _spec_module_ast() -> ast.Module:
    """Parse ``MeshStager.spec`` as Python (a spec file is exec'd, so this is valid)."""
    return ast.parse(SPEC_PATH.read_text(encoding="utf-8"), filename=str(SPEC_PATH))


def _spec_assignment(name: str) -> object:
    """Return the literal value assigned to module-level *name* in the spec file."""
    for node in _spec_module_ast().body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{SPEC_PATH.name} has no module-level assignment for {name!r}")


def _analysis_keyword(name: str) -> ast.expr:
    """Return the AST node passed as keyword *name* to ``Analysis(...)`` in the spec."""
    for node in ast.walk(_spec_module_ast()):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id != "Analysis":
                continue
            for keyword in node.keywords:
                if keyword.arg == name:
                    return keyword.value
    raise AssertionError(f"{SPEC_PATH.name} does not pass {name!r} to Analysis()")


class TestSpecDeclaresScipy(unittest.TestCase):
    """``MeshStager.spec`` must name SciPy so PyInstaller does not have to infer it."""

    def test_spec_file_exists(self) -> None:
        self.assertTrue(SPEC_PATH.is_file(), f"missing canonical spec: {SPEC_PATH}")

    def test_hidden_imports_cover_the_native_renderer_stack(self) -> None:
        hidden = _spec_assignment("HIDDEN_IMPORTS")
        self.assertIsInstance(hidden, list)
        for module_name in REQUIRED_SPEC_HIDDEN_IMPORTS:
            self.assertIn(module_name, hidden, f"{module_name} must be a declared hidden import")

    def test_analysis_actually_receives_the_hidden_imports(self) -> None:
        """A declared-but-unwired list would silently reproduce the RC3 bundle."""
        node = _analysis_keyword("hiddenimports")
        self.assertIsInstance(node, ast.Name)
        self.assertEqual(getattr(node, "id", ""), "HIDDEN_IMPORTS")


class TestCanonicalBuildCommand(unittest.TestCase):
    """The release build must go through the spec, not its own PyInstaller flags."""

    def setUp(self) -> None:
        self._build = _load_build_script()

    def test_command_builds_from_the_spec(self) -> None:
        cmd = self._build.pyinstaller_command(Path("python.exe"))
        self.assertEqual(cmd[-1], SPEC_PATH.name)
        self.assertIn("-m", cmd)
        self.assertIn("PyInstaller", cmd)

    def test_command_declares_no_specless_flags(self) -> None:
        cmd = self._build.pyinstaller_command(Path("python.exe"))
        for flag in SPECLESS_BUILD_FLAGS:
            self.assertNotIn(flag, cmd, f"{flag} belongs in {SPEC_PATH.name}, not the command")

    def test_scipy_is_a_verified_bundle_requirement(self) -> None:
        self.assertIn("scipy", self._build.REQUIRED_BUNDLED_PACKAGES)
        self.assertIn("scipy", self._build.RUNTIME_IMPORT_CHECKS)


class TestBundleVerification(unittest.TestCase):
    """``missing_bundled_packages`` is the gate between a build and a release ZIP."""

    def setUp(self) -> None:
        self._build = _load_build_script()
        self._internal = Path(tempfile.mkdtemp(prefix="meshstager_internal_")) / "_internal"

    def _make_bundle(self, *, packages: tuple[str, ...], scipy_subpackages: tuple[str, ...]) -> Path:
        """Create a fake frozen ``_internal`` tree with the given contents."""
        for package in packages:
            (self._internal / package).mkdir(parents=True, exist_ok=True)
        for name in scipy_subpackages:
            (self._internal / "scipy" / name).mkdir(parents=True, exist_ok=True)
        return self._internal

    def test_complete_bundle_reports_nothing_missing(self) -> None:
        internal = self._make_bundle(
            packages=self._build.REQUIRED_BUNDLED_PACKAGES,
            scipy_subpackages=self._build.REQUIRED_SCIPY_SUBPACKAGES,
        )
        self.assertEqual(self._build.missing_bundled_packages(internal), ())

    def test_rc3_shaped_bundle_reports_scipy(self) -> None:
        """The exact shipped failure: numpy/PIL/trimesh present, scipy absent."""
        internal = self._make_bundle(
            packages=("numpy", "PIL", "trimesh"),
            scipy_subpackages=(),
        )
        self.assertEqual(self._build.missing_bundled_packages(internal), ("scipy",))

    def test_scipy_without_its_render_subpackages_reports_them(self) -> None:
        internal = self._make_bundle(
            packages=self._build.REQUIRED_BUNDLED_PACKAGES,
            scipy_subpackages=("sparse",),
        )
        self.assertEqual(self._build.missing_bundled_packages(internal), ("scipy.spatial",))

    def test_absent_internal_directory_reports_every_package(self) -> None:
        missing = self._build.missing_bundled_packages(self._internal / "does_not_exist")
        self.assertEqual(missing, self._build.REQUIRED_BUNDLED_PACKAGES)


class TestBuildInterpreterSelection(unittest.TestCase):
    """The build interpreter must be able to import everything that has to be frozen."""

    def setUp(self) -> None:
        self._build = _load_build_script()

    def test_venv_python_is_preferred_when_present(self) -> None:
        venv_python = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
        if not venv_python.is_file():
            self.skipTest("repo venv not present")
        self.assertEqual(self._build.build_python_candidates()[0], venv_python)

    def test_candidates_are_deduplicated(self) -> None:
        candidates = self._build.build_python_candidates()
        keys = [str(path.resolve()).casefold() for path in candidates]
        self.assertEqual(len(keys), len(set(keys)))

    def test_missing_modules_reports_only_unimportable_names(self) -> None:
        """One subprocess: a stdlib module resolves, a nonexistent one is reported."""
        missing = self._build.missing_modules(
            Path(sys.executable), ("json", "meshstager_no_such_module")
        )
        self.assertEqual(missing, ("meshstager_no_such_module",))


if __name__ == "__main__":
    unittest.main()
