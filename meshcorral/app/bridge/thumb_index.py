"""
Map source mesh paths to Blender ``thumbnail.png`` using ``result.json`` in bridge outputs.

Scans each ``outputs/blender_bridge/<job_id>/result.json``; for ``status == complete`` and
existing ``thumbnail_path``, maps ``source_file`` (absolute) → thumbnail path. Failed
thumbnail jobs (same ``source_file``, no newer successful thumb on disk) are tracked for
health badges and filters. Newer ``result.json`` mtimes win when the same source appears
more than once.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from meshcorral.app.bridge.job_models import BridgeJobResult, BridgeJobStatus, BridgeJobType
from meshcorral.app.bridge.job_runner import resolve_bridge_paths
from meshcorral.models.file_record import FileRecord
from meshcorral.models.thumb_health import ThumbHealth, classify_thumb_health

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ThumbFailureInfo:
    """Last recorded failed Blender thumbnail job for a source file (from ``result.json``)."""

    output_dir: str | None
    log_path: str | None
    error_message: str | None
    result_json_mtime: float


def _is_thumbnail_job_type(job_type: str | None) -> bool:
    """True when *job_type* refers to a thumbnail render (legacy results may omit it)."""
    if job_type is None:
        return True
    jt = str(job_type).strip().lower()
    if not jt:
        return True
    if jt == BridgeJobType.GENERATE_THUMBNAIL.value:
        return True
    return "thumbnail" in jt


def _is_thumbnail_result_dict(data: dict[str, object]) -> bool:
    """Parse ``job_type`` from a raw ``result.json`` object."""
    raw = data.get("job_type")
    if raw is None:
        return True
    return _is_thumbnail_job_type(str(raw) if raw is not None else None)


def _norm_path_key(p: str | Path) -> str:
    try:
        return str(Path(p).resolve())
    except OSError:
        return str(Path(p))


class BlenderThumbPathIndex:
    """
    In-memory index: absolute source file path → path to ``thumbnail.png``.

    Rebuilt on :meth:`refresh` and incrementally updated from completed job results.
    """

    def __init__(self) -> None:
        self._source_to_thumb: dict[str, Path] = {}
        self._source_mtime: dict[str, float] = {}
        self._source_to_metadata: dict[str, Path] = {}
        self._failures: dict[str, ThumbFailureInfo] = {}

    def clear(self) -> None:
        """Drop all entries."""
        self._source_to_thumb.clear()
        self._source_mtime.clear()
        self._source_to_metadata.clear()
        self._failures.clear()

    def forget_source(self, source: str | Path) -> None:
        """Forget a changed source in memory without deleting any disk cache."""
        key = _norm_path_key(source)
        self._source_to_thumb.pop(key, None)
        self._source_mtime.pop(key, None)
        self._source_to_metadata.pop(key, None)
        self._failures.pop(key, None)

    def refresh(self) -> int:
        """
        Rebuild from ``result.json`` files under the bridge output root.

        Returns the number of unique source paths with a resolvable thumbnail file.
        """
        self._source_to_thumb.clear()
        self._source_mtime.clear()
        self._source_to_metadata.clear()
        self._failures.clear()
        out_root = resolve_bridge_paths().outputs_root
        if not out_root.is_dir():
            return 0
        for child in out_root.iterdir():
            rj = child / "result.json"
            if not rj.is_file():
                continue
            try:
                mtime = rj.stat().st_mtime
                data = json.loads(rj.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as e:
                logger.debug("Skip thumb index %s: %s", rj, e)
                continue
            if str(data.get("status", "")) != "complete":
                continue
            src = data.get("source_file")
            thumb = data.get("thumbnail_path")
            if not src or not thumb:
                continue
            tp = Path(str(thumb))
            if not tp.is_file():
                continue
            key = _norm_path_key(src)
            prev = self._source_mtime.get(key)
            if prev is not None and prev >= mtime:
                continue
            self._source_to_thumb[key] = tp
            self._source_mtime[key] = mtime
            meta = data.get("metadata_json_path")
            if meta:
                mpath = Path(str(meta))
                if mpath.is_file():
                    self._source_to_metadata[key] = mpath
                else:
                    self._source_to_metadata.pop(key, None)
            else:
                self._source_to_metadata.pop(key, None)
        for child in out_root.iterdir():
            rj = child / "result.json"
            if not rj.is_file():
                continue
            try:
                mtime = rj.stat().st_mtime
                data = json.loads(rj.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as e:
                logger.debug("Skip thumb failure index %s: %s", rj, e)
                continue
            if str(data.get("status", "")).lower() != "failed":
                continue
            if not isinstance(data, dict):
                continue
            if not _is_thumbnail_result_dict(data):
                continue
            src = data.get("source_file")
            if not src:
                continue
            key = _norm_path_key(str(src))
            if key in self._source_to_thumb:
                continue
            prev = self._failures.get(key)
            if prev is not None and mtime <= prev.result_json_mtime:
                continue
            err = data.get("error_message")
            self._failures[key] = ThumbFailureInfo(
                output_dir=str(data["output_dir"]) if data.get("output_dir") else None,
                log_path=str(data["log_path"]) if data.get("log_path") else None,
                error_message=str(err) if err is not None else None,
                result_json_mtime=mtime,
            )
        return len(self._source_to_thumb)

    def _result_json_mtime(self, result: BridgeJobResult) -> float:
        if not result.output_dir:
            return 0.0
        p = Path(result.output_dir) / "result.json"
        if not p.is_file():
            return 0.0
        try:
            return float(p.stat().st_mtime)
        except OSError:
            return 0.0

    def register_job_result(self, result: BridgeJobResult) -> str | None:
        """
        Apply a finished job to the in-memory index.

        Returns the normalized source key when table or gallery rows should refresh.
        """
        if not result.source_file:
            return None
        key = _norm_path_key(result.source_file)
        if result.status == BridgeJobStatus.COMPLETE:
            return self._register_complete(key, result)
        if result.status == BridgeJobStatus.FAILED:
            return self._register_failed(key, result)
        return None

    def _register_complete(self, key: str, result: BridgeJobResult) -> str | None:
        if not result.thumbnail_path:
            return key
        tp = Path(result.thumbnail_path)
        if not tp.is_file():
            return key
        self._failures.pop(key, None)
        self._source_to_thumb[key] = tp
        rpath = (
            Path(result.output_dir) / "result.json"
            if result.output_dir
            else None
        )
        if rpath and rpath.is_file():
            try:
                self._source_mtime[key] = rpath.stat().st_mtime
            except OSError:
                pass
        if result.metadata_json_path:
            mp = Path(result.metadata_json_path)
            if mp.is_file():
                self._source_to_metadata[key] = mp
            else:
                self._source_to_metadata.pop(key, None)
        else:
            self._source_to_metadata.pop(key, None)
        return key

    def _register_failed(self, key: str, result: BridgeJobResult) -> str | None:
        if not _is_thumbnail_job_type(result.job_type):
            return None
        src_path = Path(result.source_file)
        if self.has_thumbnail_for(src_path):
            self._failures.pop(key, None)
            return key
        self._failures[key] = ThumbFailureInfo(
            output_dir=result.output_dir,
            log_path=result.log_path,
            error_message=result.error_message,
            result_json_mtime=self._result_json_mtime(result),
        )
        return key

    def thumbnail_path_indexed(self, source_file: Path) -> Path | None:
        """Return indexed ``thumbnail.png`` without a disk stat (not for prime paint paths)."""
        return self._source_to_thumb.get(_norm_path_key(source_file))

    def thumbnail_path_for(self, source_file: Path) -> Path | None:
        """Return ``thumbnail.png`` for ``source_file`` if known and still on disk."""
        p = self.thumbnail_path_indexed(source_file)
        if p is None or not p.is_file():
            return None
        return p

    def iter_indexed_thumbnails(self) -> list[tuple[str, Path]]:
        """Return ``(source_key, thumbnail_path)`` pairs from the in-memory index."""
        return list(self._source_to_thumb.items())

    def has_thumbnail_for(self, source_file: Path) -> bool:
        """True if a thumbnail is indexed and the file still exists."""
        return self.thumbnail_path_for(source_file) is not None

    def metadata_path_for(self, source_file: Path) -> Path | None:
        """Return optional job ``metadata.json`` for *source_file* if known and on disk."""
        key = _norm_path_key(source_file)
        p = self._source_to_metadata.get(key)
        if p is None or not p.is_file():
            return None
        return p

    def failure_info_for(self, source_file: Path) -> ThumbFailureInfo | None:
        """Return the latest failed thumbnail job info for *source_file*, if any."""
        key = _norm_path_key(source_file)
        return self._failures.get(key)

    def thumb_health(self, record: FileRecord) -> ThumbHealth:
        """Combine on-disk thumb, recorded failure, and extension into a :class:`ThumbHealth`."""
        has_thumb = self.thumbnail_path_for(record.path) is not None
        key = _norm_path_key(record.path)
        has_fail = key in self._failures
        return classify_thumb_health(
            has_resolved_thumbnail=has_thumb,
            has_recorded_failure=has_fail,
            record=record,
        )


def _pick_stat(data: dict, *keys: str) -> object | None:
    """Get first available key from *data*, then ``mesh`` / ``stats`` subdicts when present."""
    for k in keys:
        if k in data and data[k] is not None:
            return data[k]
    for subk in ("mesh", "stats", "statistics", "summary"):
        sub = data.get(subk)
        if isinstance(sub, dict):
            for k in keys:
                if k in sub and sub[k] is not None:  # type: ignore[index]
                    return sub[k]  # type: ignore[no-any-return]
    return None


def _format_bounds_dimensions(data: dict[str, object]) -> str | None:
    b = _pick_stat(data, "bounds", "bbox", "bound_box", "aabb")
    if isinstance(b, dict):
        lo = b.get("min") or b.get("min_corner") or b.get("p_min")
        hi = b.get("max") or b.get("max_corner") or b.get("p_max")
        if lo is not None and hi is not None:
            return f"min {lo}  max {hi}"
        if "center" in b and "size" in b:
            return f"center {b.get('center')}  size {b.get('size')}"
    if isinstance(b, (list, tuple)) and len(b) >= 2:
        return f"{b[0]} … {b[-1]}"
    dim = _pick_stat(data, "dimensions", "dimension", "size", "extents")
    if isinstance(dim, (list, tuple)) and len(dim) >= 1:
        parts = [str(x) for x in dim[:4]]
        return " × ".join(parts)
    if isinstance(dim, dict):
        w = dim.get("x") or dim.get("width")
        h = dim.get("y") or dim.get("height")
        d = dim.get("z") or dim.get("depth")
        if w is not None and h is not None:
            rest = f" × {d}" if d is not None else ""
            return f"{w} × {h}{rest}"
    return None


def _format_materials(data: dict[str, object]) -> str | None:
    m = _pick_stat(data, "materials", "material_count", "num_materials", "mat_count")
    if m is None and isinstance(data.get("materials"), list):
        m = len(data["materials"])
    if m is not None:
        return str(m)
    mlist = data.get("materials")
    if isinstance(mlist, list) and mlist:
        return f"{len(mlist)} ({', '.join(str(x) for x in mlist[:5])}{'…' if len(mlist) > 5 else ''})"
    return None


def metadata_display_tuple(metadata_file: Path | None) -> tuple[str, str]:
    """
    Return ``(tags_line, mesh_line)`` for an optional Blender-side metadata JSON (legacy one-line).
    """
    tags, body, _copy = inspector_metadata_format(metadata_file)
    one = body.replace("\n", "  ") if body and body.strip() else "—"
    return tags, one


def inspector_metadata_format(
    metadata_file: Path | None,
) -> tuple[str, str, str]:
    """
    Return ``(tags_line, multiline_display_body, full_copy_text)`` for bridge metadata.

    *multiline* lists vertices, faces, triangles, materials, dimensions/bounds when present.
    *copy* includes the same plus pretty-printed JSON when the file is readable.
    """
    if metadata_file is None or not metadata_file.is_file():
        return (
            "—",
            "No sidecar metadata on disk for this asset.",
            "No sidecar metadata on disk for this asset.",
        )
    try:
        raw = metadata_file.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return "—", "(Could not read metadata file.)", "(Could not read metadata file.)"

    if not isinstance(data, dict):
        return "—", str(data), str(data)

    tags_raw = data.get("tags")
    if isinstance(tags_raw, list):
        tags = ", ".join(str(t) for t in tags_raw) if tags_raw else "—"
    elif tags_raw is not None and str(tags_raw).strip():
        tags = str(tags_raw)
    else:
        tags = "—"

    lines: list[str] = []
    label_map = [
        ("vertices", "Vertices", ("verts", "vertex_count", "vert_count", "num_vertices")),
        ("faces", "Faces", ("face_count", "num_faces", "n_faces")),
        (
            "triangles",
            "Triangles",
            ("tris", "triangle_count", "num_triangles", "tri_count"),
        ),
    ]
    for _primary, display, alts in label_map:
        val = _pick_stat(data, _primary, *alts)
        if val is not None:
            lines.append(f"{display}: {val}")

    mat_s = _format_materials(data)
    if mat_s is not None:
        lines.append(f"Materials: {mat_s}")

    dim_s = _format_bounds_dimensions(data)
    if dim_s is not None:
        lines.append(f"Dimensions / bounds: {dim_s}")

    if not any(
        ln.startswith("Vertices:") or ln.startswith("Faces:") for ln in lines
    ) and isinstance(data.get("mesh"), dict):
        m: dict = data["mesh"]
        for k, lab in (("vertices", "Vertices"), ("faces", "Faces"), ("tris", "Triangles")):
            if k in m and m[k] is not None:
                lines.append(f"{lab}: {m[k]}")

    body = "\n".join(lines) if lines else "— (no mesh stats in metadata file)"
    copy_parts = [
        "MeshStager — asset metadata",
        f"Source file: {metadata_file}",
        f"Tags: {tags}",
        "",
        body,
        "",
    ]
    try:
        pretty = json.dumps(data, indent=2, ensure_ascii=False)
        if len(pretty) > 14000:
            pretty = pretty[:14000] + "\n… (truncated)"
        copy_parts.append("— JSON —")
        copy_parts.append(pretty)
    except (TypeError, ValueError):
        copy_parts.append(str(data))
    copy_text = "\n".join(copy_parts)
    return tags, body, copy_text
