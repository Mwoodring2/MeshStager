"""Typed Blender Bridge job models and JSON serialization."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class BridgeJobType(str, Enum):
    """Supported bridge job types (start small; expand later)."""

    GENERATE_THUMBNAIL = "generate_thumbnail"


class BridgeJobStatus(str, Enum):
    """Lifecycle state of a queued job."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class GenerateThumbnailParams:
    """Parameters for the proof-of-concept thumbnail job."""

    resolution_x: int = 512
    resolution_y: int = 512
    transparent: bool = True


@dataclass(frozen=True, slots=True)
class BridgeJobRequest:
    """
    A JSON-serializable job request written by the main app.

    Safety rules:
    - `source_path` is read-only input (never modified).
    - all outputs must be written under `output_dir`.
    """

    job_id: str
    job_type: BridgeJobType
    source_path: str
    output_dir: str
    params: GenerateThumbnailParams

    def to_json_dict(self) -> dict[str, Any]:
        """Return a JSON-ready dict (enums expanded to strings)."""
        raw = asdict(self)
        raw["job_type"] = self.job_type.value
        return raw

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> "BridgeJobRequest":
        """Parse a request from a decoded JSON object."""
        job_type = BridgeJobType(str(data["job_type"]))
        params_raw = data.get("params") or {}
        params = GenerateThumbnailParams(
            resolution_x=int(params_raw.get("resolution_x", 512)),
            resolution_y=int(params_raw.get("resolution_y", 512)),
            transparent=bool(params_raw.get("transparent", True)),
        )
        return cls(
            job_id=str(data["job_id"]),
            job_type=job_type,
            source_path=str(data["source_path"]),
            output_dir=str(data["output_dir"]),
            params=params,
        )

    def source_path_obj(self) -> Path:
        """Source mesh path as a `Path`."""
        return Path(self.source_path)

    def output_dir_obj(self) -> Path:
        """Output directory as a `Path`."""
        return Path(self.output_dir)


@dataclass(frozen=True, slots=True)
class BridgeJobResult:
    """
    Result written by the worker (``result.json``) and read back by the app.

    The worker must include: ``source_file`` and ``output_dir`` (absolute paths) for traceability.
    ``job_type`` is optional in older result files; history UI may fall back to ``"unknown"``.
    """

    job_id: str
    status: BridgeJobStatus
    job_type: str | None = None
    source_file: str | None = None
    output_dir: str | None = None
    thumbnail_path: str | None = None
    metadata_json_path: str | None = None
    log_path: str | None = None
    error_message: str | None = None
    thumbnail_backend: str | None = None
    thumbnail_render_profile: str | None = None
    fallback_reason: str | None = None

    def to_json_dict(self) -> dict[str, Any]:
        """Return a JSON-ready dict (enums expanded to strings)."""
        raw = asdict(self)
        raw["status"] = self.status.value
        return raw

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> "BridgeJobResult":
        """Parse a result from a decoded JSON object."""
        return cls(
            job_id=str(data["job_id"]),
            status=BridgeJobStatus(str(data["status"])),
            job_type=(str(data["job_type"]) if data.get("job_type") else None),
            source_file=(str(data["source_file"]) if data.get("source_file") else None),
            output_dir=(str(data["output_dir"]) if data.get("output_dir") else None),
            thumbnail_path=(str(data["thumbnail_path"]) if data.get("thumbnail_path") else None),
            metadata_json_path=(
                str(data["metadata_json_path"]) if data.get("metadata_json_path") else None
            ),
            log_path=(str(data["log_path"]) if data.get("log_path") else None),
            error_message=(str(data["error_message"]) if data.get("error_message") else None),
            thumbnail_backend=(
                str(data["thumbnail_backend"]) if data.get("thumbnail_backend") else None
            ),
            thumbnail_render_profile=(
                str(data["thumbnail_render_profile"])
                if data.get("thumbnail_render_profile")
                else None
            ),
            fallback_reason=(
                str(data["fallback_reason"]) if data.get("fallback_reason") else None
            ),
        )

