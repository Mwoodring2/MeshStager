"""Prime v1.0 RC — production thumbnail UX copy and preview mapping."""

from __future__ import annotations

import unittest

from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.models.thumb_visual_state import ThumbVisualState
from meshcorral.ui.inspector.preview_panel import PreviewPanel
from meshcorral.ui.preview_state_copy import PREVIEW_UNSUPPORTED_SUBTITLE
from meshcorral.ui.thumbnails.thumbnail_ux_copy import (
    build_preview_thumb_ux,
    classify_bridge_error_kind,
    format_thumbnail_failure_footer_concise,
    infer_thumbnail_backend_label,
)
from PySide6.QtWidgets import QApplication


def _qapp() -> QApplication:
    inst = QApplication.instance()
    if inst is None:
        return QApplication([])
    return inst


class TestClassifyBridgeErrorKind(unittest.TestCase):
    def test_timeout_keyword(self) -> None:
        self.assertEqual(
            classify_bridge_error_kind("Worker timed out after 120s"),
            "timeout",
        )

    def test_corrupt_hint(self) -> None:
        self.assertEqual(
            classify_bridge_error_kind("Invalid STL header (truncated)"),
            "corrupt",
        )

    def test_failed_default(self) -> None:
        self.assertEqual(classify_bridge_error_kind("Unknown blender error"), "failed")


class TestBuildPreviewThumbUx(unittest.TestCase):
    def test_unsupported_no_retry(self) -> None:
        ux = build_preview_thumb_ux(
            health=ThumbHealth.UNSUPPORTED,
            visual=ThumbVisualState.UNSUPPORTED,
            generating=False,
            queued=False,
            decoding=False,
            can_mesh_thumbnail=False,
            has_blender_thumbnail=False,
            bridge_error_message=None,
            thumb_perf_deferred=False,
        )
        self.assertIn("no preview", ux.headline.lower())
        self.assertEqual(ux.body, PREVIEW_UNSUPPORTED_SUBTITLE)
        self.assertFalse(ux.show_retry)

    def test_deferred_not_failure(self) -> None:
        ux = build_preview_thumb_ux(
            health=ThumbHealth.PENDING,
            visual=ThumbVisualState.PLACEHOLDER,
            generating=False,
            queued=False,
            decoding=False,
            can_mesh_thumbnail=True,
            has_blender_thumbnail=False,
            bridge_error_message=None,
            thumb_perf_deferred=True,
        )
        self.assertIn("deferred", ux.headline.lower())
        self.assertTrue(ux.show_retry)

    def test_bridge_failed_not_corrupt_visual(self) -> None:
        ux = build_preview_thumb_ux(
            health=ThumbHealth.FAILED_THUMBNAIL,
            visual=ThumbVisualState.FAILED,
            generating=False,
            queued=False,
            decoding=False,
            can_mesh_thumbnail=True,
            has_blender_thumbnail=False,
            bridge_error_message="no renderable mesh",
            thumb_perf_deferred=False,
        )
        self.assertIn("failed", ux.headline.lower())
        self.assertTrue(ux.show_retry)

    def test_decode_failed_corrupt_copy(self) -> None:
        ux = build_preview_thumb_ux(
            health=ThumbHealth.MISSING_THUMBNAIL,
            visual=ThumbVisualState.FAILED,
            generating=False,
            queued=False,
            decoding=False,
            can_mesh_thumbnail=True,
            has_blender_thumbnail=False,
            bridge_error_message=None,
            thumb_perf_deferred=False,
        )
        self.assertIn("corrupt", ux.headline.lower())
        self.assertIn("unreadable", ux.body.lower())


class TestPreviewRetryVisibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _qapp()

    def test_failed_mesh_shows_retry_button(self) -> None:
        panel = PreviewPanel()
        ux = build_preview_thumb_ux(
            health=ThumbHealth.FAILED_THUMBNAIL,
            visual=ThumbVisualState.FAILED,
            generating=False,
            queued=False,
            decoding=False,
            can_mesh_thumbnail=True,
            has_blender_thumbnail=False,
            bridge_error_message="boom",
            thumb_perf_deferred=False,
        )
        panel.apply(
            name="a.stl",
            extension_badge="STL",
            thumbnail_state="ignored",
            preview_kind="",
            preview_subline="",
            pixmap=None,
            missing_file=False,
            preview_blocked_message=None,
            can_regenerate=True,
            blender_enabled=False,
            preview_thumb_headline=ux.headline,
            preview_thumb_body=ux.body,
            preview_show_retry_thumbnail=ux.show_retry,
            preview_retry_button_label=ux.retry_button_label,
        )
        self.assertFalse(panel._btn_regenerate.isHidden())
        self.assertTrue(panel._btn_regenerate.isEnabled())


class TestFooterConcise(unittest.TestCase):
    def test_footer(self) -> None:
        msg = format_thumbnail_failure_footer_concise(source_filename="x.stl")
        self.assertIn("x.stl", msg)
        self.assertIn("Jobs", msg)


class TestInferBackend(unittest.TestCase):
    def test_blender(self) -> None:
        self.assertIn("Blender", infer_thumbnail_backend_label("Blender HQ"))

    def test_native(self) -> None:
        self.assertIn("native", infer_thumbnail_backend_label("native fast").lower())


if __name__ == "__main__":
    unittest.main()
