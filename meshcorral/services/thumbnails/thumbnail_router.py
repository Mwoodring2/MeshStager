"""Hybrid thumbnail routing: native first, optional Blender fallback."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from meshcorral.app.bridge.job_models import BridgeJobResult, BridgeJobStatus
from meshcorral.app.bridge.job_runner import RESULT_BASENAME, resolve_bridge_paths
from meshcorral.services.settings_service import SettingsService
from meshcorral.services.thumbnails.blender_thumbnail_backend import BlenderThumbnailBackend
from meshcorral.services.thumbnails.native_thumbnail_backend import NativeThumbnailBackend
from meshcorral.services.thumbnails.thumbnail_routing_policy import (
    ThumbnailManualOverride,
    ThumbnailRoutePlan,
    route_thumbnail,
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ThumbnailRouteDecision:
    """Explainable routing decision (useful for tests and UI messaging)."""

    selected: str  # "native" | "blender" | "none"
    reason: str
    plan: ThumbnailRoutePlan | None = None


def _safe_resolve(p: Path) -> Path:
    try:
        return p.resolve()
    except OSError:
        return p


class ThumbnailRouter:
    """
    Select a backend and produce outputs into the existing on-disk thumbnail cache.

    Design constraints:
    - native thumbnails should not require Blender
    - Blender bridge remains available as an optional fallback
    - output should be compatible with the existing ``BlenderThumbPathIndex`` indexer
    """

    def __init__(self, settings: SettingsService) -> None:
        self._settings = settings
        self._native = NativeThumbnailBackend()
        self._blender = BlenderThumbnailBackend(settings)

    def native_supports(self, path: Path) -> bool:
        """True when the native CPU backend can attempt *path*."""
        return self._native.supports(path)

    def route_for(
        self,
        source_path: Path,
        *,
        manual_override: ThumbnailManualOverride = ThumbnailManualOverride.DEFAULT,
        for_auto_enqueue: bool = False,
    ) -> ThumbnailRouteDecision:
        """Return routing decision for *source_path* using Prime v1.0 policy."""
        plan = route_thumbnail(
            source_path,
            self._settings,
            manual_override=manual_override,
            for_auto_enqueue=for_auto_enqueue,
        )
        return ThumbnailRouteDecision(
            selected=plan.backend,
            reason=plan.reason,
            plan=plan,
        )

    def generate_to_cache(
        self,
        source_path: Path,
        *,
        max_px: int = 512,
        manual_override: ThumbnailManualOverride = ThumbnailManualOverride.DEFAULT,
        for_auto_enqueue: bool = False,
    ) -> BridgeJobResult:
        """
        Generate a thumbnail and write a ``result.json`` compatible with the thumb index.

        Returns a :class:`BridgeJobResult` to integrate cleanly with existing UI code.
        """
        src = _safe_resolve(Path(source_path))
        decision = self.route_for(
            src,
            manual_override=manual_override,
            for_auto_enqueue=for_auto_enqueue,
        )
        if decision.selected == "none" or decision.plan is None:
            msg = decision.reason or "Thumbnail unavailable for this format."
            return BridgeJobResult(
                job_id="",
                status=BridgeJobStatus.FAILED,
                job_type="thumbnail_router",
                source_file=str(src),
                output_dir=None,
                thumbnail_path=None,
                log_path=None,
                error_message=msg,
            )

        paths = resolve_bridge_paths()
        job_id = str(uuid.uuid4())
        out_dir = (paths.outputs_root / job_id).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)

        if decision.selected == "native":
            hq = manual_override == ThumbnailManualOverride.NATIVE
            return self._generate_native_result(
                src,
                out_dir,
                job_id=job_id,
                max_px=max_px,
                plan=decision.plan,
                high_quality=hq,
                for_auto_enqueue=for_auto_enqueue,
            )

        res2 = self._blender.generate(src, out_dir, max_px=int(max_px))
        status2 = BridgeJobStatus.COMPLETE if res2.ok else BridgeJobStatus.FAILED
        return self._build_result(
            job_id=job_id,
            status=status2,
            job_type="generate_thumbnail",
            source_file=str(src),
            output_dir=str(_safe_resolve(res2.output_dir)) if res2.output_dir else str(out_dir),
            thumbnail_path=str(_safe_resolve(res2.thumbnail_path)) if res2.thumbnail_path else None,
            log_path=str(_safe_resolve(res2.log_path)) if res2.log_path else None,
            error_message=res2.error_message,
            plan=decision.plan,
        )

    def generate_native_to_cache(
        self,
        source_path: Path,
        *,
        job_id: str | None = None,
        max_px: int = 512,
        fallback_on_fail: bool = False,
        for_auto_enqueue: bool = False,
        high_quality: bool = False,
    ) -> tuple[BridgeJobResult, object]:
        """Force native CPU generation (background native queue).

        Returns ``(bridge_result, geometry_summary_or_none)``.
        """
        src = _safe_resolve(Path(source_path))
        plan = route_thumbnail(
            src,
            self._settings,
            manual_override=ThumbnailManualOverride.NATIVE,
        )
        paths = resolve_bridge_paths()
        jid = job_id or str(uuid.uuid4())
        out_dir = (paths.outputs_root / jid).resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        manual_hq = high_quality or plan.thumbnail_render_profile in (
            "studio",
            "high",
            "manual",
        )
        return self._generate_native_result(
            src,
            out_dir,
            job_id=jid,
            max_px=max_px,
            plan=plan,
            fallback_on_fail=fallback_on_fail,
            high_quality=manual_hq,
            for_auto_enqueue=for_auto_enqueue,
        )

    def generate_blender_to_cache(
        self,
        source_path: Path,
        *,
        max_px: int = 512,
    ) -> BridgeJobResult:
        """Force Blender generation (manual high-quality path)."""
        return self.generate_to_cache(
            source_path,
            max_px=max_px,
            manual_override=ThumbnailManualOverride.BLENDER,
        )

    def _generate_native_result(
        self,
        src: Path,
        out_dir: Path,
        *,
        job_id: str,
        max_px: int,
        plan: ThumbnailRoutePlan,
        fallback_on_fail: bool = False,
        high_quality: bool = False,
        for_auto_enqueue: bool = False,
    ) -> tuple[BridgeJobResult, object]:
        res = self._native.generate(
            src,
            out_dir,
            max_px=int(max_px),
            render_profile=plan.thumbnail_render_profile,
            high_quality=bool(high_quality),
            for_auto_enqueue=bool(for_auto_enqueue),
        )
        status = BridgeJobStatus.COMPLETE if res.ok else BridgeJobStatus.FAILED
        fallback_reason = None
        if not res.ok and fallback_on_fail and plan.fallback_to_blender_on_native_fail:
            fallback_reason = res.error_message or "native failed"
        br = self._build_result(
            job_id=job_id,
            status=status,
            job_type="native_thumbnail",
            source_file=str(src),
            output_dir=str(_safe_resolve(out_dir)),
            thumbnail_path=str(_safe_resolve(res.thumbnail_path)) if res.thumbnail_path else None,
            log_path=str(_safe_resolve(res.log_path)) if res.log_path else None,
            error_message=res.error_message,
            plan=plan,
            fallback_reason=fallback_reason,
        )
        try:
            (out_dir / RESULT_BASENAME).write_text(
                json.dumps(br.to_json_dict(), indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except OSError:
            pass
        return br, res.geometry_summary

    @staticmethod
    def _build_result(
        *,
        job_id: str,
        status: BridgeJobStatus,
        job_type: str,
        source_file: str,
        output_dir: str | None,
        thumbnail_path: str | None,
        log_path: str | None,
        error_message: str | None,
        plan: ThumbnailRoutePlan,
        fallback_reason: str | None = None,
    ) -> BridgeJobResult:
        return BridgeJobResult(
            job_id=job_id,
            status=status,
            job_type=job_type,
            source_file=source_file,
            output_dir=output_dir,
            thumbnail_path=thumbnail_path,
            log_path=log_path,
            error_message=error_message,
            thumbnail_backend=plan.thumbnail_backend,
            thumbnail_render_profile=plan.thumbnail_render_profile,
            fallback_reason=fallback_reason,
        )
