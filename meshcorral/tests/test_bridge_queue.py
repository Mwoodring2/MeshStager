"""Tests for :mod:`meshcorral.app.bridge.queue_manager` and cancel helpers."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import QSettings

from meshcorral.app.bridge import job_runner
from meshcorral.app.bridge.bridge_backpressure import BridgeEnqueueReject
from meshcorral.app.bridge.job_origin import JobOrigin
from meshcorral.app.bridge.queue_manager import BridgeQueueManager
from meshcorral.services.settings_service import SettingsService
from meshcorral.services.thumbnails.thumbnail_routing_policy import ThumbnailManualOverride
from meshcorral.tests.native_health_fixtures import patch_healthy_native_routing


class TestJobFilenameParse(unittest.TestCase):
    """Round-trip parsing of bridge job filenames."""

    def test_job_id_from_job_filename(self) -> None:
        """Filename ``abc-123.job.json`` should map back to id ``abc-123``."""
        p = Path("/x/y/abc-123.job.json")
        self.assertEqual(job_runner.job_id_from_job_filename(p), "abc-123")


class TestBridgeQueueEnqueue(unittest.TestCase):
    """End-to-end enqueue tests using a temp QSettings backing store."""

    def setUp(self) -> None:
        """Create a temp QSettings ini and an isolated bridge runtime root."""
        self._tmp = tempfile.TemporaryDirectory()
        self._ini = str(Path(self._tmp.name) / "t.ini")
        self._qs = QSettings(self._ini, QSettings.Format.IniFormat)
        self._qs.clear()
        self._svc = SettingsService(self._qs)
        self._prev_bridge_root = os.environ.get("ROUNDUP_BRIDGE_ROOT")
        os.environ["ROUNDUP_BRIDGE_ROOT"] = str(Path(self._tmp.name) / "bridge")

    def tearDown(self) -> None:
        """Reset the bridge root override and the temp QSettings store."""
        if self._prev_bridge_root is None:
            os.environ.pop("ROUNDUP_BRIDGE_ROOT", None)
        else:
            os.environ["ROUNDUP_BRIDGE_ROOT"] = self._prev_bridge_root
        self._qs.clear()
        self._tmp.cleanup()

    def test_rejects_when_no_blender(self) -> None:
        """If Blender cannot be located, enqueue must fail with a UI-ready message."""
        with patch("meshcorral.app.bridge.queue_manager.find_blender_executable", return_value=None):
            mgr = BridgeQueueManager(self._svc)
            p = Path(self._tmp.name) / "f.stl"
            p.write_text("x", encoding="utf-8")
            ok, msg, _reject = mgr.try_enqueue_thumbnail(
                p,
                manual_override=ThumbnailManualOverride.BLENDER,
            )
        mgr.shutdown(timeout=0.2, close_enqueue=False)
        self.assertFalse(ok)
        self.assertIn("Blender", msg)

    def test_rejects_auto_stl_for_native_policy(self) -> None:
        """Auto-recommended STL must not enter the Blender queue directly."""
        with patch(
            "meshcorral.app.bridge.queue_manager.find_blender_executable",
            return_value=Path(self._tmp.name) / "blender.exe",
        ), patch_healthy_native_routing():
            mgr = BridgeQueueManager(self._svc)
            p = Path(self._tmp.name) / "native.stl"
            p.write_text("x", encoding="utf-8")
            ok, msg, reject = mgr.try_enqueue_thumbnail(p)
        mgr.shutdown(timeout=0.2, close_enqueue=False)
        self.assertFalse(ok)
        self.assertIn("Native CPU", msg)
        self.assertEqual(reject, BridgeEnqueueReject.NOT_ROUTED)


class TestBridgeQueueOriginTracking(unittest.TestCase):
    """:class:`BridgeQueueManager` should record per-job :class:`JobOrigin`."""

    def setUp(self) -> None:
        """Create temp QSettings and a self-contained bridge root."""
        self._tmp = tempfile.TemporaryDirectory()
        self._ini = str(Path(self._tmp.name) / "t.ini")
        self._qs = QSettings(self._ini, QSettings.Format.IniFormat)
        self._qs.clear()
        self._svc = SettingsService(self._qs)
        self._prev_bridge_root = os.environ.get("ROUNDUP_BRIDGE_ROOT")
        os.environ["ROUNDUP_BRIDGE_ROOT"] = str(Path(self._tmp.name) / "bridge")
        self._fake_blender = Path(self._tmp.name) / "blender.exe"
        self._fake_blender.write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        """Restore environment so other tests are not affected."""
        if self._prev_bridge_root is None:
            os.environ.pop("ROUNDUP_BRIDGE_ROOT", None)
        else:
            os.environ["ROUNDUP_BRIDGE_ROOT"] = self._prev_bridge_root
        self._qs.clear()
        self._tmp.cleanup()

    def _enqueue(self, mgr: BridgeQueueManager, name: str, origin: JobOrigin) -> str:
        """Enqueue a thumbnail job and return its job_id (helper)."""
        p = Path(self._tmp.name) / name
        p.write_text("dummy", encoding="utf-8")
        ok, msg, _reject = mgr.try_enqueue_thumbnail(
            p,
            origin=origin,
            manual_override=ThumbnailManualOverride.BLENDER,
        )
        self.assertTrue(ok, msg)
        # The newest job is at the end of the items list.
        with mgr._cond:  # type: ignore[attr-defined]
            job_path, _ = mgr._items[-1]  # type: ignore[attr-defined]
        return job_runner.job_id_from_job_filename(job_path)

    def test_origin_recorded_per_enqueue(self) -> None:
        """Each enqueue must register its origin under the freshly assigned job_id."""
        with patch(
            "meshcorral.app.bridge.queue_manager.find_blender_executable",
            return_value=self._fake_blender,
        ):
            mgr = BridgeQueueManager(self._svc)
            mgr.shutdown(timeout=0.05, close_enqueue=False)  # Stop worker; keep enqueue open.
            jid_a = self._enqueue(mgr, "a.stl", JobOrigin.BACKGROUND_AUTO)
            jid_b = self._enqueue(mgr, "b.stl", JobOrigin.MANUAL_SINGLE)
            jid_c = self._enqueue(mgr, "c.stl", JobOrigin.MANUAL_BATCH)

        self.assertEqual(mgr.job_origin_for_job_id(jid_a), JobOrigin.BACKGROUND_AUTO)
        self.assertEqual(mgr.job_origin_for_job_id(jid_b), JobOrigin.MANUAL_SINGLE)
        self.assertEqual(mgr.job_origin_for_job_id(jid_c), JobOrigin.MANUAL_BATCH)

    def test_pop_origin_consumes_entry(self) -> None:
        """``pop_job_origin_for_job_id`` should return the value once and then ``None``."""
        with patch(
            "meshcorral.app.bridge.queue_manager.find_blender_executable",
            return_value=self._fake_blender,
        ):
            mgr = BridgeQueueManager(self._svc)
            mgr.shutdown(timeout=0.05, close_enqueue=False)
            jid = self._enqueue(mgr, "z.stl", JobOrigin.MANUAL_SINGLE)

        self.assertEqual(mgr.pop_job_origin_for_job_id(jid), JobOrigin.MANUAL_SINGLE)
        self.assertIsNone(mgr.pop_job_origin_for_job_id(jid))
        self.assertIsNone(mgr.job_origin_for_job_id(jid))

    def test_unknown_job_id_returns_none(self) -> None:
        """Origins for unknown ids are reported as ``None`` (treated as background)."""
        with patch(
            "meshcorral.app.bridge.queue_manager.find_blender_executable",
            return_value=self._fake_blender,
        ):
            mgr = BridgeQueueManager(self._svc)
            mgr.shutdown(timeout=0.05, close_enqueue=False)

        self.assertIsNone(mgr.job_origin_for_job_id("does-not-exist"))

    def test_default_origin_is_manual_single(self) -> None:
        """Backwards-compat default keeps single user actions surfacing modals."""
        with patch(
            "meshcorral.app.bridge.queue_manager.find_blender_executable",
            return_value=self._fake_blender,
        ):
            mgr = BridgeQueueManager(self._svc)
            mgr.shutdown(timeout=0.05, close_enqueue=False)
            p = Path(self._tmp.name) / "default.stl"
            p.write_text("x", encoding="utf-8")
            ok, _, _reject = mgr.try_enqueue_thumbnail(
                p,
                manual_override=ThumbnailManualOverride.BLENDER,
            )
            self.assertTrue(ok)
            with mgr._cond:  # type: ignore[attr-defined]
                jp, _ = mgr._items[-1]  # type: ignore[attr-defined]
            jid = job_runner.job_id_from_job_filename(jp)

        self.assertEqual(mgr.job_origin_for_job_id(jid), JobOrigin.MANUAL_SINGLE)

    def test_cancel_clears_origin(self) -> None:
        """Cancelling a queued job removes its origin entry from the in-memory map."""
        with patch(
            "meshcorral.app.bridge.queue_manager.find_blender_executable",
            return_value=self._fake_blender,
        ):
            mgr = BridgeQueueManager(self._svc)
            mgr.shutdown(timeout=0.05, close_enqueue=False)
            jid = self._enqueue(mgr, "to-cancel.stl", JobOrigin.MANUAL_BATCH)

        cancel_target = (
            "meshcorral.app.bridge.queue_manager.job_runner.cancel_pending_job_file"
        )
        with patch(cancel_target, return_value=True):
            cancelled = mgr.cancel_queued_job_id(jid)
        self.assertTrue(cancelled)
        self.assertIsNone(mgr.job_origin_for_job_id(jid))


if __name__ == "__main__":
    unittest.main()
