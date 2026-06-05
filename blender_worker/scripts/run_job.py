# SPDX-License-Identifier: GPL-2.0-or-later
# flake8: noqa
# isort: skip_file
"""
Blender headless job entry: invoked as:

  blender --background --python run_job.py -- --job <path_to_job.json>
"""

from __future__ import annotations

import importlib.util
import json
import sys
import traceback
from pathlib import Path


def _job_json_path() -> Path:
    argv = list(sys.argv)
    for i, arg in enumerate(argv):
        if arg == "--job" and i + 1 < len(argv):
            return Path(argv[i + 1])
    for arg in reversed(argv):
        s = str(arg)
        if s.lower().endswith(".json") and Path(s).is_file():
            return Path(s)
    raise SystemExit(2)


def _write_log(out_dir: Path, line: str) -> None:
    p = out_dir / "log.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def _main() -> int:
    job_path = _job_json_path()
    with job_path.open(encoding="utf-8") as f:
        job: dict = json.load(f)

    out_dir = Path(str(job.get("output_dir", "")))
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_log(out_dir, f"run_job: loaded {job_path}")
    _write_log(out_dir, f"job_id={job.get('job_id')} type={job.get('job_type')}")

    if str(job.get("job_type", "")) not in ("generate_thumbnail",):
        err = f"Unsupported job_type: {job.get('job_type')}"
        _write_log(out_dir, err)
        (out_dir / "result.json").write_text(
            json.dumps(
                {
                    "job_id": str(job.get("job_id", "")),
                    "job_type": str(job.get("job_type", "unknown")),
                    "status": "failed",
                    "source_file": str(job.get("source_path", "")),
                    "output_dir": str(out_dir.resolve()),
                    "thumbnail_path": None,
                    "error_message": err,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return 1

    mod_path = Path(__file__).resolve().parent / "thumbnail_render.py"
    spec = importlib.util.spec_from_file_location("meshcorral_blender_thumb", mod_path)
    if spec is None or spec.loader is None:
        _write_log(out_dir, f"Could not load: {mod_path}")
        return 1
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    try:
        module.render_thumbnail(  # type: ignore[attr-defined]
            job=job,
            out_dir=out_dir,
            log=_write_log,
        )
    except Exception:  # noqa: BLE001
        tb = traceback.format_exc()
        _write_log(out_dir, tb)
        (out_dir / "result.json").write_text(
            json.dumps(
                {
                    "job_id": str(job.get("job_id", "")),
                    "job_type": str(job.get("job_type", "generate_thumbnail")),
                    "status": "failed",
                    "source_file": str(job.get("source_path", "")),
                    "output_dir": str(out_dir.resolve()),
                    "thumbnail_path": None,
                    "error_message": tb,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
