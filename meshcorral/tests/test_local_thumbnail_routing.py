"""Prime v1.0 — local thumbnail routing (native default for STL/OBJ)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings

from meshcorral.app.bridge.bridge_backpressure import (
    BridgeEnqueueReject,
    enqueue_tiered_bridge_thumbnails,
)
from meshcorral.models.file_record import FileRecord
from meshcorral.services.settings_service import SettingsService
from meshcorral.services.thumbnails.thumbnail_routing_policy import (
    ThumbnailManualOverride,
    ThumbnailRendererPreference,
    auto_enqueue_allowed,
    route_thumbnail,
    thumbnail_path_for_record,
)
from meshcorral.services.thumbnails.thumbnail_router import ThumbnailRouter
from meshcorral.tests.native_health_fixtures import patch_healthy_native_routing


def _rec(name: str, ext: str = ".stl") -> FileRecord:
    p = Path(f"C:/work/{name}")
    return FileRecord(
        path=p,
        name=name,
        extension=ext,
        parent_folder="work",
        size_bytes=1024,
        modified_time=0.0,
    )


class TestThumbnailRoutingPolicy(unittest.TestCase):
    """Routing rules for Auto recommended and manual overrides."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        ini = Path(self._tmp.name) / "routing.ini"
        self.settings = SettingsService(QSettings(str(ini), QSettings.Format.IniFormat))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_stl_routes_native_auto_recommended(self) -> None:
        with patch_healthy_native_routing():
            plan = route_thumbnail(Path("C:/a/part.stl"), self.settings)
        self.assertEqual(plan.backend, "native")
        self.assertEqual(plan.thumbnail_backend, "cpu_native")

    def test_obj_routes_native_auto_recommended(self) -> None:
        with patch_healthy_native_routing():
            plan = route_thumbnail(Path("C:/a/part.obj"), self.settings)
        self.assertEqual(plan.backend, "native")

    def test_fbx_routes_blender_when_configured(self) -> None:
        with patch(
            "meshcorral.services.thumbnails.thumbnail_routing_policy.find_blender_executable",
            return_value=Path("C:/Blender/blender.exe"),
        ):
            plan = route_thumbnail(Path("C:/a/prop.fbx"), self.settings)
        self.assertEqual(plan.backend, "blender")

    def test_blend_routes_blender_only(self) -> None:
        with patch(
            "meshcorral.services.thumbnails.thumbnail_routing_policy.find_blender_executable",
            return_value=Path("C:/Blender/blender.exe"),
        ):
            plan = route_thumbnail(Path("C:/a/scene.blend"), self.settings)
        self.assertEqual(plan.backend, "blender")
        self.assertTrue(plan.eligible_for_blender_idle_fill)

    def test_ma_open_only_no_thumbnail(self) -> None:
        plan = route_thumbnail(Path("C:/a/scene.ma"), self.settings)
        self.assertEqual(plan.backend, "none")

    def test_manual_blender_override(self) -> None:
        with patch(
            "meshcorral.services.thumbnails.thumbnail_routing_policy.find_blender_executable",
            return_value=Path("C:/Blender/blender.exe"),
        ):
            plan = route_thumbnail(
                Path("C:/a/part.stl"),
                self.settings,
                manual_override=ThumbnailManualOverride.BLENDER,
            )
        self.assertEqual(plan.backend, "blender")

    def test_manual_only_blocks_auto_enqueue(self) -> None:
        self.settings.set_thumbnail_renderer_preference(
            SettingsService.THUMBNAIL_RENDERER_MANUAL_ONLY
        )
        plan = route_thumbnail(
            Path("C:/a/part.stl"),
            self.settings,
            for_auto_enqueue=True,
        )
        self.assertEqual(plan.backend, "none")
        self.assertFalse(auto_enqueue_allowed(self.settings))

    def test_blender_first_stl_uses_blender(self) -> None:
        self.settings.set_thumbnail_renderer_preference(
            SettingsService.THUMBNAIL_RENDERER_BLENDER_FIRST
        )
        with patch(
            "meshcorral.services.thumbnails.thumbnail_routing_policy.find_blender_executable",
            return_value=Path("C:/Blender/blender.exe"),
        ):
            plan = route_thumbnail(Path("C:/a/part.stl"), self.settings)
        self.assertEqual(plan.backend, "blender")


class TestThumbnailRouterDefault(unittest.TestCase):
    """Router uses policy without legacy env flag."""

    def test_stl_routes_native_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ini = Path(td) / "router.ini"
            settings = SettingsService(QSettings(str(ini), QSettings.Format.IniFormat))
            with patch.dict("os.environ", {}, clear=True), patch_healthy_native_routing():
                router = ThumbnailRouter(settings)
                decision = router.route_for(Path("C:/tmp/mesh.stl"))
                self.assertEqual(decision.selected, "native")


class TestBackgroundQueueSkipsBlenderForNative(unittest.TestCase):
    """Tiered enqueue should not call Blender for native-owned STL rows."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        ini = Path(self._tmp.name) / "routing.ini"
        self.settings = SettingsService(QSettings(str(ini), QSettings.Format.IniFormat))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_stl_auto_enqueue_uses_native_path(self) -> None:
        record = _rec("mesh.stl")
        enqueued_backends: list[str] = []

        def try_enqueue(rec: FileRecord) -> tuple[bool, str, BridgeEnqueueReject]:
            with patch_healthy_native_routing():
                plan = route_thumbnail(
                    rec.path,
                    self.settings,
                    for_auto_enqueue=True,
                )
            enqueued_backends.append(plan.backend)
            if plan.backend == "native":
                return True, "", BridgeEnqueueReject.OK
            if plan.backend == "blender":
                return False, "blender should not run", BridgeEnqueueReject.NOT_ROUTED
            return False, "none", BridgeEnqueueReject.NOT_ROUTED

        stats = enqueue_tiered_bridge_thumbnails(
            try_enqueue,
            {"selected": [record], "visible": [], "directional_preload": [], "idle_background": []},
            has_thumbnail=lambda _r: False,
            include_idle_tier=False,
        )
        self.assertEqual(stats.enqueued, 1)
        self.assertEqual(enqueued_backends, ["native"])

    def test_idle_tier_skips_native_supported_stl(self) -> None:
        record = _rec("mesh.stl")

        def try_enqueue(rec: FileRecord) -> tuple[bool, str, BridgeEnqueueReject]:
            with patch_healthy_native_routing():
                plan = route_thumbnail(rec.path, self.settings, for_auto_enqueue=True)
            if plan.backend == "native":
                return False, "idle skips native", BridgeEnqueueReject.NOT_ROUTED
            return True, "", BridgeEnqueueReject.OK

        stats = enqueue_tiered_bridge_thumbnails(
            try_enqueue,
            {"selected": [], "visible": [], "directional_preload": [], "idle_background": [record]},
            has_thumbnail=lambda _r: False,
            include_idle_tier=True,
        )
        self.assertEqual(stats.enqueued, 0)


class TestNativeFailureFallback(unittest.TestCase):
    """Native failure may schedule Blender when policy allows."""

    def test_auto_native_plan_allows_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            ini = Path(td) / "routing.ini"
            settings = SettingsService(QSettings(str(ini), QSettings.Format.IniFormat))
            with patch_healthy_native_routing(), patch(
                "meshcorral.services.thumbnails.thumbnail_routing_policy.find_blender_executable",
                return_value=Path("C:/Blender/blender.exe"),
            ):
                plan = route_thumbnail(Path("C:/a/part.stl"), settings)
            self.assertTrue(plan.fallback_to_blender_on_native_fail)


class TestThumbnailPathForRecord(unittest.TestCase):
    """Routing uses record.extension when path suffix is missing."""

    def test_extension_fallback_for_routing(self) -> None:
        rec = FileRecord(
            path=Path("C:/work/model"),
            name="model",
            extension=".stl",
            parent_folder="work",
            size_bytes=1,
            modified_time=0.0,
        )
        resolved = thumbnail_path_for_record(rec)
        self.assertEqual(resolved.suffix.lower(), ".stl")
        with tempfile.TemporaryDirectory() as td:
            ini = Path(td) / "routing.ini"
            settings = SettingsService(QSettings(str(ini), QSettings.Format.IniFormat))
            with patch_healthy_native_routing():
                plan = route_thumbnail(resolved, settings)
            self.assertEqual(plan.backend, "native")


if __name__ == "__main__":
    unittest.main()
