"""High-level API for submitting Blender Bridge jobs."""

from __future__ import annotations

from pathlib import Path

from meshcorral.app.bridge.job_models import BridgeJobResult
from meshcorral.app.bridge.job_runner import enqueue_generate_thumbnail_job, run_job_now
from meshcorral.services.settings_service import SettingsService


def generate_thumbnail_for_mesh(
    source_mesh_path: Path,
    settings: SettingsService,
    *,
    resolution_x: int = 512,
    resolution_y: int = 512,
    transparent: bool = True,
) -> BridgeJobResult:
    """
    Proof-of-concept bridge call: render a thumbnail for `source_mesh_path`.

    This writes a job JSON, runs Blender headless, and returns a typed result.
    """
    job_path = enqueue_generate_thumbnail_job(
        source_mesh_path,
        settings,
        resolution_x=resolution_x,
        resolution_y=resolution_y,
        transparent=transparent,
    )
    return run_job_now(job_path, settings)

