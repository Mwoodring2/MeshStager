"""
Scan Blender Bridge output folders for ``result.json`` files (no database).

Each job has its own directory under ``outputs/blender_bridge/<job_id>/``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from meshcorral.app.bridge.job_runner import resolve_bridge_paths

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BlenderJobHistoryItem:
    """One row in the job history list (read from a ``result.json`` on disk)."""

    job_id: str
    job_type: str
    source_filename: str
    status: str
    output_dir: str
    error_message: str | None
    thumbnail_path: str | None
    result_path: Path
    modified_at: float

    @property
    def log_path(self) -> Path:
        """Per-job log next to ``result.json`` (written by the bridge runner or worker)."""
        return Path(self.output_dir) / "log.txt"


def list_recent_blender_bridge_jobs(*, limit: int = 100) -> list[BlenderJobHistoryItem]:
    """
    Return recent jobs with a ``result.json`` under the bridge output root, newest first.

    Does not require Blender; missing or empty output directory yields an empty list.
    """
    if limit < 1:
        return []
    out_root = resolve_bridge_paths().outputs_root
    if not out_root.is_dir():
        return []

    scored: list[tuple[float, BlenderJobHistoryItem]] = []
    try:
        for child in out_root.iterdir():
            if not child.is_dir():
                continue
            result_file = child / "result.json"
            if not result_file.is_file():
                continue
            try:
                mtime = result_file.stat().st_mtime
                data = json.loads(result_file.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as e:
                logger.debug("Skip unreadable result: %s (%s)", result_file, e)
                continue

            job_id = str(data.get("job_id", child.name))
            jt = str(data.get("job_type", "unknown"))
            st = str(data.get("status", "unknown"))
            source_full = str(data.get("source_file", ""))
            out_dir = str(data.get("output_dir", str(child.resolve())))
            err_raw = data.get("error_message")
            err: str | None
            if err_raw is None or err_raw is False:
                err = None
            else:
                err = str(err_raw)
            thumb_raw = data.get("thumbnail_path")
            thumb: str | None
            if thumb_raw:
                thumb = str(thumb_raw)
            else:
                thumb = None
            source_name = Path(source_full).name if source_full else "—"
            item = BlenderJobHistoryItem(
                job_id=job_id,
                job_type=jt,
                source_filename=source_name,
                status=st,
                output_dir=out_dir,
                error_message=err,
                thumbnail_path=thumb,
                result_path=result_file,
                modified_at=mtime,
            )
            scored.append((mtime, item))
    except OSError as e:
        logger.warning("Could not list bridge output: %s", e)
        return []

    scored.sort(key=lambda t: -t[0])
    return [p[1] for p in scored[:limit]]
