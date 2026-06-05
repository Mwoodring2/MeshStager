"""Tests for native renderer dependency health (Prime v1.0 RC A4)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from meshcorral.services.environment.native_renderer_health import (
    NativeRendererHealth,
    check_native_renderer_health,
    check_startup_environment,
    reset_native_renderer_health_cache,
)


class TestNativeRendererHealth(unittest.TestCase):
    """Dependency probe and user-facing copy."""

    def tearDown(self) -> None:
        reset_native_renderer_health_cache()

    def test_available_when_all_imports_present(self) -> None:
        health = check_native_renderer_health(force=True)
        if not health.available:
            self.skipTest(f"native deps not installed in test env: {health.missing_dependencies}")
        self.assertTrue(health.can_render_stl_obj)
        self.assertEqual(health.fallback_backend, "native")
        self.assertEqual(health.settings_message, "Native renderer ready")

    def test_unavailable_when_numpy_missing(self) -> None:
        def fake_spec(name: str) -> object | None:
            if name == "numpy":
                return None
            return object()

        with patch(
            "meshcorral.services.environment.native_renderer_health.importlib.util.find_spec",
            side_effect=fake_spec,
        ):
            reset_native_renderer_health_cache()
            health = check_native_renderer_health(force=True)
        self.assertFalse(health.available)
        self.assertIn("numpy", health.missing_dependencies)
        self.assertEqual(health.fallback_backend, "blender")
        self.assertIn("NumPy", health.settings_message)
        self.assertIn("NumPy", health.jobs_message)

    def test_health_is_cached(self) -> None:
        calls = {"n": 0}

        def counting_spec(name: str) -> object | None:
            calls["n"] += 1
            return object()

        with patch(
            "meshcorral.services.environment.native_renderer_health.importlib.util.find_spec",
            side_effect=counting_spec,
        ):
            reset_native_renderer_health_cache()
            check_native_renderer_health(force=True)
            first = calls["n"]
            check_native_renderer_health()
            second = calls["n"]
        self.assertGreater(first, 0)
        self.assertEqual(first, second)

    def test_user_facing_copy_when_numpy_missing(self) -> None:
        def fake_spec(name: str) -> object | None:
            if name == "numpy":
                return None
            return object()

        with patch(
            "meshcorral.services.environment.native_renderer_health.importlib.util.find_spec",
            side_effect=fake_spec,
        ):
            reset_native_renderer_health_cache()
            health = check_native_renderer_health(force=True)
        self.assertEqual(
            health.settings_message,
            "Native renderer unavailable: missing NumPy",
        )
        self.assertEqual(
            health.jobs_message,
            "Native renderer unavailable. Missing dependency: NumPy.",
        )
        self.assertEqual(
            health.diagnostics_fallback_reason,
            "Native renderer unavailable: missing NumPy",
        )
        self.assertEqual(
            health.footer_blender_fallback_message,
            "Native thumbnails unavailable · Using slower fallback path",
        )
        self.assertIn("Install dependencies", health.manual_native_warning)

    def test_startup_environment_summary(self) -> None:
        import tempfile
        from pathlib import Path

        from PySide6.QtCore import QSettings

        from meshcorral.services.settings_service import SettingsService

        with tempfile.TemporaryDirectory() as td:
            ini = Path(td) / "env.ini"
            settings = SettingsService(QSettings(str(ini), QSettings.Format.IniFormat))
            summary = check_startup_environment(settings)
        self.assertIn(summary.native_renderer, ("Ready", "Unavailable"))
        self.assertTrue(summary.metadata_cache == "Ready")
        self.assertTrue(summary.thumbnail_cache == "Ready")


if __name__ == "__main__":
    unittest.main()
