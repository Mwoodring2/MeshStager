"""Blender Bridge thumbnail backend wrapper (optional enhanced compatibility)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from meshcorral.app.bridge.job_runner import RESULT_BASENAME, run_job_now
from meshcorral.services.settings_service import SettingsService
from meshcorral.services.thumbnails.thumbnail_backend_base import (
    ThumbnailBackend,
    ThumbnailBackendId,
    ThumbnailResult,
)

logger = logging.getLogger(__name__)


class BlenderThumbnailBackend(ThumbnailBackend):
    """Direct (synchronous) Blender bridge runner used by the router when requested."""

    backend_id = ThumbnailBackendId.BLENDER

    def __init__(self, settings: SettingsService) -> None:
        self._settings = settings

    def supports(self, path: Path) -> bool:
        # The bridge can attempt many formats, but the app currently expects it for mesh formats.
        # Routing decisions are handled by ThumbnailRouter; this method is permissive.
        return bool(path.suffix)

    def generate(self, path: Path, output_dir: Path, *, max_px: int = 512) -> ThumbnailResult:
        # The existing bridge pipeline owns output directory selection via job JSON.
        _ = output_dir
        _ = max_px
        from meshcorral.app.bridge.job_runner import enqueue_generate_thumbnail_job

        try:
            job_path = enqueue_generate_thumbnail_job(Path(path), self._settings)
        except OSError as e:
            msg = f"Could not create Blender job file: {e}"
            logger.warning(msg)
            return ThumbnailResult(
                backend_id=self.backend_id,
                source_file=Path(path),
                output_dir=None,
                thumbnail_path=None,
                ok=False,
                error_message=msg,
                log_path=None,
            )

        result = run_job_now(job_path, self._settings)
        tp = Path(result.thumbnail_path) if result.thumbnail_path else None
        od = Path(result.output_dir) if result.output_dir else None
        lp = Path(result.log_path) if result.log_path else None

        # Ensure result.json exists (some error paths may have already written it).
        if od is not None:
            try:
                rj = od / RESULT_BASENAME
                if not rj.is_file():
                    rj.write_text(json.dumps(result.to_json_dict(), indent=2, sort_keys=True), encoding="utf-8")
            except OSError:
                pass

        return ThumbnailResult(
            backend_id=self.backend_id,
            source_file=Path(result.source_file) if result.source_file else Path(path),
            output_dir=od,
            thumbnail_path=tp if (tp is not None and tp.is_file()) else None,
            ok=result.status.value == "complete" and tp is not None and tp.is_file(),
            error_message=result.error_message,
            log_path=lp if (lp is not None and lp.is_file()) else lp,
        )

