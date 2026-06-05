"""Native lightweight thumbnail generation for common geometry formats."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from meshcorral.services.render.mesh_render_pipeline import MeshRenderPipeline
from meshcorral.services.thumbnails.thumbnail_backend_base import (
    ThumbnailBackend,
    ThumbnailBackendId,
    ThumbnailResult,
)

logger = logging.getLogger(__name__)


def _safe_resolve(p: Path) -> Path:
    try:
        return p.resolve()
    except OSError:
        return p


class NativeThumbnailBackend(ThumbnailBackend):
    """CPU-only, stability-first thumbnail backend (no Blender dependency)."""

    backend_id = ThumbnailBackendId.NATIVE

    _EXTS: frozenset[str] = frozenset({".stl", ".obj", ".ply", ".glb", ".gltf"})

    def __init__(self) -> None:
        self._pipeline = MeshRenderPipeline()

    def supports(self, path: Path) -> bool:
        return path.suffix.lower().strip() in self._EXTS

    def generate(
        self,
        path: Path,
        output_dir: Path,
        *,
        max_px: int = 512,
        render_profile: str = "cpu_native",
        high_quality: bool = False,
        for_auto_enqueue: bool = False,
    ) -> ThumbnailResult:
        src = _safe_resolve(Path(path))
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = out_dir / "thumbnail.png"
        log_path = out_dir / "log.txt"
        result_path = out_dir / "result.json"

        max_px = int(max(64, min(512, max_px)))

        try:
            png_bytes, timing, geometry_summary = self._pipeline.render_png_bytes(
                src,
                max_px=max_px,
                high_quality=high_quality,
                for_auto_enqueue=for_auto_enqueue,
            )
            thumb_path.write_bytes(png_bytes)
            timing_line = (
                f"mode={timing.render_mode} total={timing.total_s:.3f}s "
                f"network={timing.is_network_path} cached={timing.used_cached_output}\n"
            )
            payload = {
                "job_type": "native_thumbnail",
                "status": "complete",
                "source_file": str(src),
                "output_dir": str(_safe_resolve(out_dir)),
                "thumbnail_path": str(_safe_resolve(thumb_path)),
                "log_path": str(_safe_resolve(log_path)),
                "error_message": None,
                "thumbnail_backend": "cpu_native",
                "thumbnail_render_profile": render_profile,
                "fallback_reason": None,
                "render_timing": {
                    "stage_copy_s": timing.stage_copy_s,
                    "load_import_s": timing.load_import_s,
                    "geometry_metadata_s": timing.geometry_metadata_s,
                    "preview_proxy_s": timing.preview_proxy_s,
                    "render_hq_s": timing.render_hq_s,
                    "write_cache_s": timing.write_cache_s,
                    "total_s": timing.total_s,
                    "render_mode": timing.render_mode,
                },
            }
            result_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
            try:
                log_path.write_text("Native thumbnail: complete\n" + timing_line, encoding="utf-8")
            except OSError:
                pass
            return ThumbnailResult(
                backend_id=self.backend_id,
                source_file=src,
                output_dir=out_dir,
                thumbnail_path=thumb_path,
                ok=True,
                log_path=log_path,
                geometry_summary=geometry_summary,
            )
        except Exception as e:  # noqa: BLE001 - must not crash UI for thumbnail failures
            msg = f"Native thumbnail failed: {e}"
            logger.info("%s (%s)", msg, src)
            try:
                log_path.write_text(msg + "\n", encoding="utf-8")
            except OSError:
                pass
            payload2 = {
                "job_type": "native_thumbnail",
                "status": "failed",
                "source_file": str(src),
                "output_dir": str(_safe_resolve(out_dir)),
                "thumbnail_path": None,
                "log_path": str(_safe_resolve(log_path)),
                "error_message": msg,
                "thumbnail_backend": "cpu_native",
                "thumbnail_render_profile": render_profile,
                "fallback_reason": None,
            }
            try:
                result_path.write_text(json.dumps(payload2, indent=2, sort_keys=True), encoding="utf-8")
            except OSError:
                pass
            return ThumbnailResult(
                backend_id=self.backend_id,
                source_file=src,
                output_dir=out_dir,
                thumbnail_path=None,
                ok=False,
                error_message=msg,
                log_path=log_path,
            )
