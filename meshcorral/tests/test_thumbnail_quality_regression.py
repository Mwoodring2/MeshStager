"""RC3 thumbnail quality regression — balanced default, cache versioning, safeguards."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from meshcorral.services.render.mesh_rasterizer import (
    prepare_mesh_arrays,
    rasterize_mesh_preview,
    rasterize_vertices_splat,
)
from meshcorral.services.render.render_cache import (
    THUMBNAIL_STYLE_VERSION,
    build_fingerprint,
    read_cached_png,
    write_cached_png,
)
from meshcorral.services.render.render_pipeline_policy import (
    ALL_QUALITY_MODES,
    LARGE_MESH_PROXY_BYTES,
    QUALITY_BALANCED_PREVIEW,
    QUALITY_FAST_PROXY,
    QUALITY_HQ_PREVIEW,
    SMALL_FILE_BALANCED_BYTES,
    effective_max_faces,
    quality_mode_display_label,
    resolve_render_mode,
)
from meshcorral.ui.preview_state_copy import PREVIEW_BALANCED, PREVIEW_PROXY
from meshcorral.ui.thumbnails.thumbnail_confidence import (
    ThumbConfidenceState,
    confidence_state_for,
)
from meshcorral.models.thumb_visual_state import ThumbVisualState


class _FakeMesh:
    def __init__(self) -> None:
        self.vertices = np.array(
            [
                [-0.5, -0.5, 0.0],
                [0.5, -0.5, 0.0],
                [0.5, 0.5, 0.0],
                [-0.5, 0.5, 0.0],
                [0.0, 0.0, 0.8],
            ],
            dtype=np.float32,
        )
        self.faces = np.array(
            [
                [0, 1, 4],
                [1, 2, 4],
                [2, 3, 4],
                [3, 0, 4],
                [0, 1, 2],
                [0, 2, 3],
            ],
            dtype=np.int32,
        )
        self.vertex_normals = None


class TestThumbnailStyleCache(unittest.TestCase):
    def test_fingerprint_includes_style_version(self) -> None:
        fp = build_fingerprint(
            Path("C:/a.stl"),
            size_bytes=100,
            mtime=1.0,
            max_px=256,
            render_mode="balanced",
        )
        legacy_raw = "C:\\a.stl|100|1.000000|256|balanced"
        import hashlib

        legacy = hashlib.sha256(legacy_raw.encode("utf-8")).hexdigest()[:32]
        self.assertNotEqual(fp, legacy)
        self.assertEqual(THUMBNAIL_STYLE_VERSION, "thumbnail_style_v4")

    def test_mode_separates_cache_keys(self) -> None:
        base = dict(
            source_path=Path("C:/a.stl"),
            size_bytes=100,
            mtime=1.0,
            max_px=256,
        )
        proxy = build_fingerprint(**base, render_mode="proxy")
        balanced = build_fingerprint(**base, render_mode="balanced")
        hq = build_fingerprint(**base, render_mode="high")
        self.assertNotEqual(proxy, balanced)
        self.assertNotEqual(balanced, hq)

    def test_style_bump_invalidates_prior_cache_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "cube.stl"
            src.write_bytes(b"solid x\nendsolid x\n")
            st = src.stat()
            cache_dir = Path(tmp) / "cache"
            with mock.patch(
                "meshcorral.services.render.render_cache.RENDER_CACHE_DIR",
                cache_dir,
            ):
                write_cached_png(
                    src,
                    size_bytes=st.st_size,
                    mtime=st.st_mtime,
                    max_px=256,
                    render_mode="proxy",
                    png_bytes=b"\x89PNG\r\n",
                )
                hit = read_cached_png(
                    src,
                    size_bytes=st.st_size,
                    mtime=st.st_mtime,
                    max_px=256,
                    render_mode="proxy",
                )
                self.assertEqual(hit, b"\x89PNG\r\n")
                with mock.patch(
                    "meshcorral.services.render.render_cache.THUMBNAIL_STYLE_VERSION",
                    "thumbnail_style_v1",
                ):
                    miss = read_cached_png(
                        src,
                        size_bytes=st.st_size,
                        mtime=st.st_mtime,
                        max_px=256,
                        render_mode="proxy",
                    )
                self.assertIsNone(miss)


class TestBalancedQualityPolicy(unittest.TestCase):
    def test_small_local_file_uses_balanced(self) -> None:
        mode = resolve_render_mode(
            Path("C:/small.stl"),
            size_bytes=SMALL_FILE_BALANCED_BYTES - 1,
            high_quality=False,
            for_auto_enqueue=False,
        )
        self.assertEqual(mode, "balanced")

    def test_large_file_stays_proxy(self) -> None:
        mode = resolve_render_mode(
            Path("C:/big.stl"),
            size_bytes=LARGE_MESH_PROXY_BYTES,
            high_quality=False,
            for_auto_enqueue=False,
        )
        self.assertEqual(mode, "proxy")

    def test_large_file_does_not_auto_hq(self) -> None:
        mode = resolve_render_mode(
            Path("C:/big.stl"),
            size_bytes=LARGE_MESH_PROXY_BYTES * 2,
            high_quality=False,
            for_auto_enqueue=False,
        )
        self.assertEqual(mode, "proxy")
        self.assertNotEqual(mode, "high")

    def test_manual_hq_only_when_requested(self) -> None:
        mode = resolve_render_mode(
            Path("C:/big.stl"),
            size_bytes=LARGE_MESH_PROXY_BYTES * 2,
            high_quality=True,
            for_auto_enqueue=False,
        )
        self.assertEqual(mode, "high")

    def test_network_small_file_uses_balanced_not_proxy(self) -> None:
        mode = resolve_render_mode(
            Path(r"\\srv\share\a.stl"),
            size_bytes=1024,
            high_quality=False,
            for_auto_enqueue=True,
        )
        self.assertEqual(mode, QUALITY_BALANCED_PREVIEW)

    def test_network_large_file_stays_proxy(self) -> None:
        mode = resolve_render_mode(
            Path(r"\\srv\share\big.stl"),
            size_bytes=LARGE_MESH_PROXY_BYTES,
            high_quality=False,
            for_auto_enqueue=True,
        )
        self.assertEqual(mode, QUALITY_FAST_PROXY)

    def test_network_path_does_not_auto_hq(self) -> None:
        mode = resolve_render_mode(
            Path(r"\\srv\share\a.stl"),
            size_bytes=1024,
            high_quality=False,
            for_auto_enqueue=True,
        )
        self.assertNotEqual(mode, QUALITY_HQ_PREVIEW)

    def test_small_file_gets_higher_face_budget(self) -> None:
        small = effective_max_faces("balanced", size_bytes=1024)
        medium = effective_max_faces("balanced", size_bytes=SMALL_FILE_BALANCED_BYTES + 1)
        self.assertGreater(small, medium)


class TestNativeRasterQuality(unittest.TestCase):
    def test_balanced_surface_png_non_empty(self) -> None:
        mesh = _FakeMesh()
        v, n = prepare_mesh_arrays(mesh)
        png = rasterize_mesh_preview(
            mesh,
            v,
            n,
            size_px=128,
            render_mode="balanced",
            max_points=5000,
            max_faces=200,
        )
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertGreater(len(png), 200)

    def test_proxy_splat_differs_from_balanced_surface(self) -> None:
        mesh = _FakeMesh()
        v, n = prepare_mesh_arrays(mesh)
        proxy = rasterize_mesh_preview(
            mesh,
            v,
            n,
            size_px=128,
            render_mode="proxy",
            max_points=5000,
            max_faces=200,
        )
        balanced = rasterize_mesh_preview(
            mesh,
            v,
            n,
            size_px=128,
            render_mode="balanced",
            max_points=5000,
            max_faces=200,
        )
        self.assertNotEqual(proxy, balanced)

    def test_improved_proxy_less_sparse_than_legacy_defaults(self) -> None:
        mesh = _FakeMesh()
        v, n = prepare_mesh_arrays(mesh)
        fast = rasterize_vertices_splat(v, n, size_px=96, max_points=5000, fast=True)
        slow = rasterize_vertices_splat(v, n, size_px=96, max_points=5000, fast=False)
        self.assertNotEqual(fast, slow)


class TestDeferredPolicyIntact(unittest.TestCase):
    def test_deferred_confidence_copy_unchanged_intent(self) -> None:
        state = confidence_state_for(ThumbVisualState.PLACEHOLDER, deferred=True)
        self.assertEqual(state, ThumbConfidenceState.DEFERRED)
        subtitle = state.card_subtitle()
        self.assertIn("Deferred", subtitle)

    def test_preview_labels_locked(self) -> None:
        self.assertEqual(PREVIEW_BALANCED, "Balanced Preview")
        self.assertEqual(PREVIEW_PROXY, "Proxy Preview")

    def test_quality_mode_constants_and_labels(self) -> None:
        self.assertEqual(
            ALL_QUALITY_MODES,
            frozenset({"proxy", "balanced", "high"}),
        )
        self.assertEqual(quality_mode_display_label("balanced"), PREVIEW_BALANCED)
        self.assertEqual(quality_mode_display_label("proxy"), PREVIEW_PROXY)
        self.assertEqual(quality_mode_display_label("high"), "HQ Preview")


if __name__ == "__main__":
    unittest.main()
