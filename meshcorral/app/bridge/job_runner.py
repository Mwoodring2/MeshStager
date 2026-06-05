"""Job queue + execution for the optional Blender Bridge."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from pathlib import Path

from meshcorral.app import config
from meshcorral.app.bridge.blender_locator import find_blender_executable
from meshcorral.app.bridge.job_models import (
    BridgeJobRequest,
    BridgeJobResult,
    BridgeJobStatus,
    BridgeJobType,
    GenerateThumbnailParams,
)
from meshcorral.services.settings_service import SettingsService

logger = logging.getLogger(__name__)

# Single output filename in each job's folder (per proof-of-concept spec).
RESULT_BASENAME = "result.json"


@dataclass(frozen=True, slots=True)
class BridgePaths:
    """Resolved on-disk folders used by the bridge."""

    jobs_pending: Path
    jobs_running: Path
    jobs_complete: Path
    jobs_failed: Path
    jobs_cancelled: Path
    outputs_root: Path


def _bridge_root_dir() -> Path:
    """
    Root folder for bridge runtime artifacts.

    Uses user data directory by default so the app works as a portable EXE, but can be
    overridden for development via `ROUNDUP_BRIDGE_ROOT`.
    """
    override = os.environ.get("ROUNDUP_BRIDGE_ROOT", "").strip()
    if override:
        return Path(override)
    return config.USER_DATA_DIR / "bridge"


def bridge_runtime_root() -> Path:
    """Expose the bridge filesystem root (``.../<USER_DATA>/bridge`` unless overridden)."""
    return _bridge_root_dir().resolve()


def resolve_bridge_paths() -> BridgePaths:
    """
    Create and return all required bridge folders (``data/jobs/...`` and ``outputs/...``).
    """
    root = _bridge_root_dir()
    jobs_root = root / "data" / "jobs"
    outputs_root = root / "outputs" / "blender_bridge"

    paths = BridgePaths(
        jobs_pending=jobs_root / "pending",
        jobs_running=jobs_root / "running",
        jobs_complete=jobs_root / "complete",
        jobs_failed=jobs_root / "failed",
        jobs_cancelled=jobs_root / "cancelled",
        outputs_root=outputs_root,
    )
    for p in (
        paths.jobs_pending,
        paths.jobs_running,
        paths.jobs_complete,
        paths.jobs_failed,
        paths.jobs_cancelled,
        paths.outputs_root,
    ):
        p.mkdir(parents=True, exist_ok=True)
    return paths


def _job_filename(job_id: str) -> str:
    return f"{job_id}.job.json"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _worker_script_path() -> Path:
    """``blender_worker/scripts/run_job.py`` next to the ``meshcorral`` package root."""
    return (Path(__file__).resolve().parents[3] / "blender_worker" / "scripts" / "run_job.py").resolve()


def _write_failure_result(
    req: BridgeJobRequest,
    output_dir: Path,
    log_text: str,
    error_message: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "log.txt"
    with log_path.open("w", encoding="utf-8") as f:
        f.write(log_text)
    result = {
        "job_id": req.job_id,
        "job_type": req.job_type.value,
        "status": "failed",
        "source_file": str(Path(req.source_path).resolve()),
        "output_dir": str(output_dir.resolve()),
        "thumbnail_path": None,
        "error_message": error_message,
    }
    _write_json(output_dir / RESULT_BASENAME, result)


def _write_cancelled_result(
    req: BridgeJobRequest,
    output_dir: Path,
    reason: str,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "log.txt"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"Cancelled: {reason}\n")
    result = {
        "job_id": req.job_id,
        "job_type": req.job_type.value,
        "status": "cancelled",
        "source_file": str(Path(req.source_path).resolve()),
        "output_dir": str(output_dir.resolve()),
        "thumbnail_path": None,
        "error_message": reason,
    }
    _write_json(output_dir / RESULT_BASENAME, result)


def job_id_from_job_filename(job_path: Path) -> str:
    """Parse ``<job_id>.job.json`` → ``job_id``."""
    m = re.fullmatch(r"(.+)\.job\.json", job_path.name, re.IGNORECASE)
    return m.group(1) if m else job_path.stem


def cancel_pending_job_file(job_path: Path) -> bool:
    """
    Remove a job that is still in ``pending/``: write ``cancelled`` result, move job to ``cancelled/``.

    Returns True if a pending file was found and moved.
    """
    paths = resolve_bridge_paths()
    try:
        resolved = job_path.resolve()
        pending_root = paths.jobs_pending.resolve()
    except OSError:
        return False
    if not resolved.is_file() or pending_root not in resolved.parents:
        return False
    if resolved.parent != pending_root:
        return False
    try:
        job_data = _read_json(resolved)
        req = BridgeJobRequest.from_json_dict(job_data)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logger.warning("Could not read job to cancel %s: %s", job_path, e)
        try:
            resolved.unlink()
        except OSError:
            pass
        return True

    out_dir = req.output_dir_obj().resolve()
    _write_cancelled_result(req, out_dir, "Removed from queue by user before execution.")
    dst = paths.jobs_cancelled / resolved.name
    if dst.exists():
        dst = paths.jobs_cancelled / f"{req.job_id}.{uuid.uuid4()}.job.json"
    try:
        shutil.move(str(resolved), str(dst))
    except OSError as e:
        logger.warning("Cancel move failed: %s", e)
        return False
    return True


def enqueue_generate_thumbnail_job(
    source_path: Path,
    settings: SettingsService,
    *,
    resolution_x: int = 512,
    resolution_y: int = 512,
    transparent: bool = True,
) -> Path:
    """
    Create a thumbnail job file under ``data/jobs/pending/``.

    The job is safe by construction: it references the source file read-only and writes all
    outputs into a unique per-job output directory.
    """
    _ = settings
    paths = resolve_bridge_paths()
    job_id = str(uuid.uuid4())
    output_dir = (paths.outputs_root / job_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    req = BridgeJobRequest(
        job_id=job_id,
        job_type=BridgeJobType.GENERATE_THUMBNAIL,
        source_path=str(source_path.resolve()),
        output_dir=str(output_dir),
        params=GenerateThumbnailParams(
            resolution_x=resolution_x,
            resolution_y=resolution_y,
            transparent=transparent,
        ),
    )
    job_path = paths.jobs_pending / _job_filename(job_id)
    _write_json(job_path, req.to_json_dict())
    logger.info("Enqueued Blender Bridge job %s (%s)", job_id, req.job_type.value)
    return job_path


def run_job_now(
    job_path: Path,
    settings: SettingsService | None = None,
    *,
    blender_executable: Path | None = None,
) -> BridgeJobResult:
    """
    Move pending → running, run Blender with the job JSON, then move to complete or failed.
    Per-job log is ``<output_dir>/log.txt``; result is ``<output_dir>/result.json``.

    If ``blender_executable`` is set (e.g. resolved on the main thread), it is used instead
    of :func:`find_blender_executable` to avoid off-thread :class:`QSettings` access.
    """
    paths = resolve_bridge_paths()
    if not job_path.is_file():
        jid = job_id_from_job_filename(job_path)
        return BridgeJobResult(
            job_id=jid,
            status=BridgeJobStatus.CANCELLED,
            job_type=None,
            source_file=None,
            output_dir=None,
            thumbnail_path=None,
            log_path=None,
            error_message="Job file is missing (it may have been cancelled).",
        )

    job_data = _read_json(job_path)
    req = BridgeJobRequest.from_json_dict(job_data)
    output_dir = req.output_dir_obj().resolve()
    out_log = output_dir / "log.txt"

    script_path = _worker_script_path()
    if not script_path.is_file():
        err = f"Blender worker script is missing: {script_path}"
        logger.error(err)
        _write_failure_result(req, output_dir, err + "\n", err)
        if job_path.parent == paths.jobs_pending:
            shutil.move(str(job_path), str(paths.jobs_failed / job_path.name))
        return BridgeJobResult(
            job_id=req.job_id,
            status=BridgeJobStatus.FAILED,
            job_type=req.job_type.value,
            source_file=str(Path(req.source_path).resolve()),
            output_dir=str(output_dir),
            thumbnail_path=None,
            log_path=str(out_log),
            error_message=err,
        )

    if blender_executable is not None:
        blender_candidate = Path(blender_executable)
        blender_exe = blender_candidate if blender_candidate.is_file() else None
    else:
        blender_exe = find_blender_executable(settings) if settings is not None else None
    if blender_exe is None:
        msg = "Blender executable not found. Install Blender or set the path in Settings (optional bridge)."
        logger.warning("Blender Bridge: %s", msg)
        _write_failure_result(req, output_dir, msg + "\n", msg)
        if job_path.parent == paths.jobs_pending:
            shutil.move(str(job_path), str(paths.jobs_failed / job_path.name))
        return BridgeJobResult(
            job_id=req.job_id,
            status=BridgeJobStatus.FAILED,
            job_type=req.job_type.value,
            source_file=str(Path(req.source_path).resolve()),
            output_dir=str(output_dir),
            thumbnail_path=None,
            log_path=str(out_log),
            error_message=msg,
        )

    # Pending → running
    if job_path.parent == paths.jobs_pending:
        running_path = paths.jobs_running / job_path.name
        if running_path.exists():
            running_path = paths.jobs_running / f"{req.job_id}.{uuid.uuid4()}.job.json"
        shutil.move(str(job_path), str(running_path))
        work_job_path = running_path
    else:
        work_job_path = job_path

    cmd = [
        str(blender_exe),
        "--background",
        "--factory-startup",
        "--python",
        str(script_path),
        "--",
        "--job",
        str(work_job_path),
    ]
    with out_log.open("w", encoding="utf-8") as logf:
        header = " ".join(cmd) + "\n\n"
        logf.write(header)
        logf.flush()
        run_kw: dict = {
            "stdout": logf,
            "stderr": subprocess.STDOUT,
            "cwd": str(paths.outputs_root),
            "check": False,
        }
        if os.name == "nt":
            run_kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            proc = subprocess.run(cmd, **run_kw)  # noqa: S603
        except OSError as e:
            err = f"Failed to start Blender: {e}"
            logger.error(err)
            work_job_path2 = work_job_path
            _write_failure_result(
                req,
                output_dir,
                (out_log.read_text(encoding="utf-8") if out_log.is_file() else "")
                + f"\n{err}\n",
                err,
            )
            if work_job_path2.parent == paths.jobs_running:
                shutil.move(str(work_job_path2), str(paths.jobs_failed / work_job_path2.name))
            return BridgeJobResult(
                job_id=req.job_id,
                status=BridgeJobStatus.FAILED,
                job_type=req.job_type.value,
                source_file=str(Path(req.source_path).resolve()),
                output_dir=str(output_dir),
                thumbnail_path=None,
                log_path=str(out_log),
                error_message=err,
            )

    result_path = output_dir / RESULT_BASENAME
    result: BridgeJobResult
    if result_path.is_file():
        data = _read_json(result_path)
        data.setdefault("source_file", str(Path(req.source_path).resolve()))
        data.setdefault("output_dir", str(output_dir))
        try:
            parsed = BridgeJobResult.from_json_dict(data)
        except (KeyError, TypeError, ValueError) as e:
            err = f"Invalid result.json: {e}"
            _write_failure_result(
                req,
                output_dir,
                (out_log.read_text(encoding="utf-8") if out_log.is_file() else "")
                + f"\n{err}\n",
                err,
            )
            result = BridgeJobResult(
                job_id=req.job_id,
                status=BridgeJobStatus.FAILED,
                job_type=req.job_type.value,
                source_file=str(Path(req.source_path).resolve()),
                output_dir=str(output_dir),
                thumbnail_path=None,
                log_path=str(out_log),
                error_message=err,
            )
        else:
            result = BridgeJobResult(
                job_id=parsed.job_id,
                status=parsed.status,
                job_type=parsed.job_type or req.job_type.value,
                source_file=parsed.source_file
                or str(Path(req.source_path).resolve()),
                output_dir=parsed.output_dir or str(output_dir),
                thumbnail_path=parsed.thumbnail_path,
                metadata_json_path=parsed.metadata_json_path,
                log_path=str(out_log),
                error_message=parsed.error_message,
            )
            if proc.returncode != 0 and result.status != BridgeJobStatus.FAILED:
                err = f"Blender exited with code {proc.returncode}."
                _write_json(
                    result_path,
                    {
                        "job_id": result.job_id,
                        "job_type": result.job_type or req.job_type.value,
                        "status": "failed",
                        "source_file": result.source_file,
                        "output_dir": result.output_dir,
                        "thumbnail_path": result.thumbnail_path,
                        "error_message": err
                        if not result.error_message
                        else f"{result.error_message} ({err})",
                    },
                )
                data2 = _read_json(result_path)
                result = BridgeJobResult(
                    job_id=result.job_id,
                    status=BridgeJobStatus(str(data2["status"])),
                    job_type=data2.get("job_type") or result.job_type,
                    source_file=result.source_file,
                    output_dir=result.output_dir,
                    thumbnail_path=data2.get("thumbnail_path"),
                    log_path=str(out_log),
                    error_message=data2.get("error_message"),
                )
    else:
        err = (
            f"Blender exited with code {proc.returncode} and did not write result.json."
            if proc.returncode != 0
            else "Blender did not write result.json."
        )
        _write_failure_result(
            req,
            output_dir,
            (out_log.read_text(encoding="utf-8") if out_log.is_file() else "")
            + f"\n{err}\n",
            err,
        )
        result = BridgeJobResult(
            job_id=req.job_id,
            status=BridgeJobStatus.FAILED,
            job_type=req.job_type.value,
            source_file=str(Path(req.source_path).resolve()),
            output_dir=str(output_dir),
            thumbnail_path=None,
            log_path=str(out_log),
            error_message=err,
        )

    if work_job_path.parent == paths.jobs_running:
        if result.status == BridgeJobStatus.COMPLETE:
            job_dst = paths.jobs_complete
        elif result.status == BridgeJobStatus.CANCELLED:
            job_dst = paths.jobs_cancelled
        else:
            job_dst = paths.jobs_failed
        shutil.move(str(work_job_path), str(job_dst / work_job_path.name))
        if (output_dir / RESULT_BASENAME).is_file():
            try:
                shutil.copy2(
                    str(output_dir / RESULT_BASENAME),
                    str(job_dst / f"{req.job_id}.{RESULT_BASENAME}"),
                )
            except OSError as e:
                logger.debug("Could not copy result to job state folder: %s", e)

    return result