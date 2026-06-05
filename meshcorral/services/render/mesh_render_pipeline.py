"""Timed mesh preview pipeline: staging, load, geometry, proxy/HQ render, cache."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from meshcorral.services.render.mesh_rasterizer import (
    compute_geometry_metadata,
    prepare_mesh_arrays,
    rasterize_mesh_preview,
)
from meshcorral.services.render.render_cache import (
    file_stat_fingerprint,
    read_cached_png,
    write_cached_png,
)
from meshcorral.services.render.render_pipeline_policy import (
    effective_max_faces,
    effective_max_points,
    effective_max_px,
    file_size_bytes,
    resolve_render_mode,
)
from meshcorral.services.render.render_staging_cache import stage_network_file
from meshcorral.services.render.render_status import render_status_callback
from meshcorral.services.metadata.asset_metadata_summary import AssetMetadataSummary
from meshcorral.services.metadata.geometry_metadata import summary_from_loaded_mesh
from meshcorral.services.render.render_timing_profiler import RenderTimingProfiler, RenderTimingRecord
from meshcorral.utils.path_perf import is_network_like_path

logger = logging.getLogger(__name__)

_STATUS_COPY = "Copying from server"
_STATUS_LOAD = "Loading mesh"
_STATUS_GEOMETRY = "Computing geometry"
_STATUS_PROXY = "Rendering proxy preview"
_STATUS_BALANCED = "Rendering balanced preview"
_STATUS_HQ = "Rendering HQ preview"
_STATUS_CACHE = "Using cached preview"
_STATUS_WRITE_PROXY = "Saving proxy preview cache"
_STATUS_WRITE_BALANCED = "Saving balanced preview cache"


class MeshRenderPipeline:
    """Profiled native mesh thumbnail / preview renderer."""

    def render_png_bytes(
        self,
        source_path: Path,
        *,
        max_px: int = 512,
        high_quality: bool = False,
        for_auto_enqueue: bool = False,
        status_callback: Callable[[str], None] | None = None,
        write_timing_log: bool = True,
    ) -> tuple[bytes, RenderTimingRecord, AssetMetadataSummary | None]:
        """
        Render mesh to PNG with per-stage timing logged to ``render_timing.log``.

        Returns ``(png_bytes, timing_record)``. Raises on failure after logging.
        Set ``write_timing_log=False`` for benchmark warm-up passes only.
        """
        src = Path(source_path)
        size_bytes = file_size_bytes(src)
        file_mb = size_bytes / (1024.0 * 1024.0) if size_bytes > 0 else 0.0
        ext = src.suffix.lower()
        network = is_network_like_path(src)
        callback = status_callback or render_status_callback()

        profiler = RenderTimingProfiler(
            src,
            file_size_mb=file_mb,
            extension=ext,
            is_network_path=network,
            status_callback=callback,
        )

        try:
            mtime = file_stat_fingerprint(src)[1]
        except OSError as exc:
            record = profiler.finish(error_message=str(exc), write_log=write_timing_log)
            raise RuntimeError(str(exc)) from exc

        render_mode = resolve_render_mode(
            src,
            size_bytes=size_bytes,
            high_quality=high_quality,
            for_auto_enqueue=for_auto_enqueue,
        )
        profiler.set_render_mode(render_mode)
        out_px = effective_max_px(render_mode, max_px)
        max_points = effective_max_points(render_mode)
        max_faces = effective_max_faces(render_mode, size_bytes=size_bytes)

        cached = read_cached_png(
            src,
            size_bytes=size_bytes,
            mtime=mtime,
            max_px=out_px,
            render_mode=render_mode,
        )
        if cached is not None:
            profiler.set_used_cached_output(True)
            profiler.emit_status(_STATUS_CACHE)
            record = profiler.finish(error_message=None, write_log=write_timing_log)
            return cached, record, None

        work_path = src
        if network:
            profiler.emit_status(_STATUS_COPY)
            with profiler.measure("stage_copy"):
                staged = stage_network_file(src)
            profiler.set_used_staging(True, staged.local_path)
            profiler.add_stage_seconds("stage_copy", staged.elapsed_s)
            work_path = staged.local_path

        profiler.emit_status(_STATUS_LOAD)
        with profiler.measure("load_import"):
            mesh = self._load_mesh(work_path)

        profiler.emit_status(_STATUS_GEOMETRY)
        render_summary: AssetMetadataSummary | None = None
        with profiler.measure("geometry_metadata"):
            meta = compute_geometry_metadata(mesh)
            logger.debug("geometry metadata %s: %s", src.name, meta)
            render_summary = summary_from_loaded_mesh(
                src,
                mesh,
                metadata_source="render",
                cache_status="render",
            )

        v, n = prepare_mesh_arrays(mesh)

        if render_mode == "proxy":
            profiler.emit_status(_STATUS_PROXY)
            stage = "preview_proxy"
        elif render_mode == "high":
            profiler.emit_status(_STATUS_HQ)
            stage = "render_hq"
        else:
            profiler.emit_status(_STATUS_BALANCED)
            stage = "preview_balanced"

        with profiler.measure(stage):
            png_bytes = rasterize_mesh_preview(
                mesh,
                v,
                n,
                size_px=out_px,
                render_mode=render_mode,
                max_points=max_points,
                max_faces=max_faces,
            )

        save_status = _STATUS_WRITE_PROXY if render_mode == "proxy" else _STATUS_WRITE_BALANCED
        profiler.emit_status(save_status)
        with profiler.measure("write_cache"):
            write_cached_png(
                src,
                size_bytes=size_bytes,
                mtime=mtime,
                max_px=out_px,
                render_mode=render_mode,
                png_bytes=png_bytes,
            )

        record = profiler.finish(error_message=None, write_log=write_timing_log)
        return png_bytes, record, render_summary

    @staticmethod
    def _load_mesh(path: Path) -> Any:
        try:
            import trimesh  # type: ignore[import-not-found]
        except ImportError as e:
            raise RuntimeError("Missing dependency: trimesh") from e
        try:
            import scipy  # type: ignore[import-not-found]  # noqa: F401
        except ImportError as e:
            raise RuntimeError("Missing dependency: scipy") from e

        load_kwargs: dict[str, object] = {"force": "mesh", "skip_materials": True}
        mesh = trimesh.load(str(path), **load_kwargs)
        if mesh is None:
            raise RuntimeError("Could not load mesh.")
        if hasattr(mesh, "dump") and not hasattr(mesh, "vertices"):
            try:
                mesh = mesh.dump(concatenate=True)  # type: ignore[assignment]
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"Unsupported scene content: {e}") from e
        return mesh
