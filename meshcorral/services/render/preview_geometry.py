"""Bounded binary-STL preprocessing and disposable, versioned triangle cache.

All work runs inside the existing render worker. Two sequential bounded reads
avoid memory maps (a concurrently truncated mapping can terminate a process).
Vertex clustering visits every triangle: unlike face subsampling it preserves
surface connectivity at the chosen thumbnail-scale grid resolution.
"""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import logging
import os
from pathlib import Path
import struct
import tempfile
import time
import numpy as np
from meshcorral.app.config import USER_DATA_DIR

logger = logging.getLogger(__name__)
PREVIEW_GEOMETRY_VERSION = "stl_cluster_v1"
PREVIEW_CACHE_DIR = USER_DATA_DIR / "cache" / "preview_geometry"
CHUNK_TRIANGLES = 32768
MAX_PREVIEW_TRIANGLES = 180000
STL_DTYPE = np.dtype([("normal", "<f4", (3,)), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])


@dataclass(frozen=True, slots=True)
class PreviewGeometry:
    triangles: np.ndarray
    normals: np.ndarray


def binary_triangle_count(path: Path) -> int | None:
    """Exact structural check; a binary header may legitimately start 'solid'."""
    try:
        with path.open("rb") as stream:
            header = stream.read(84)
            size = os.fstat(stream.fileno()).st_size
        if len(header) != 84:
            return None
        count = struct.unpack_from("<I", header, 80)[0]
        return count if count > 0 and size == 84 + 50 * count else None
    except OSError:
        return None


def cache_path(source: Path, mode: str) -> Path:
    stat = source.stat()
    identity = f"{os.path.normcase(str(source.resolve()))}|{stat.st_size}|{stat.st_mtime_ns}|{PREVIEW_GEOMETRY_VERSION}|{mode}"
    return PREVIEW_CACHE_DIR / (hashlib.sha256(identity.encode("utf-8")).hexdigest() + ".npy")


def read_preview(path: Path) -> PreviewGeometry | None:
    try:
        # A single non-pickled, uncompressed array: validate size before allocation.
        if path.stat().st_size > MAX_PREVIEW_TRIANGLES * 48 + 4096:
            return None
        with path.open("rb") as stream:
            version = np.lib.format.read_magic(stream)
            if version != (1, 0):
                return None
            shape, fortran, dtype = np.lib.format.read_array_header_1_0(stream)
            if (len(shape) != 3 or shape[1:] != (4, 3) or not 0 < shape[0] <= MAX_PREVIEW_TRIANGLES
                    or fortran or dtype != np.dtype("<f4")):
                return None
            size = int(np.prod(shape)) * 4
            raw = stream.read(size + 33)
            if len(raw) != size + 32:
                return None
        payload = raw[:size]
        if hashlib.sha256(payload).digest() != raw[size:]:
            return None
        data = np.frombuffer(payload, dtype="<f4").reshape(shape)
        if not np.isfinite(data).all() or np.abs(data).max() > 4:
            return None
        return PreviewGeometry(data[:, :3], data[:, 3])
    except (OSError, ValueError, EOFError, OverflowError):
        return None


def write_preview(path: Path, geometry: PreviewGeometry) -> None:
    """Atomic publication; permission failures never discard a rendered preview."""
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            data = np.concatenate((geometry.triangles, geometry.normals[:, None]), axis=1).astype("<f4")
            np.save(stream, data, allow_pickle=False)
            stream.write(hashlib.sha256(data.tobytes()).digest())
        os.replace(temporary, path)
    except OSError as exc:
        logger.debug("Preview geometry cache unavailable: %s", exc)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


def _records(stream, count, timings):
    stream.seek(84)
    for start in range(0, count, CHUNK_TRIANGLES):
        amount = min(CHUNK_TRIANGLES, count - start)
        read_started = time.perf_counter()
        raw = stream.read(amount * 50)
        timings["load_import"] = timings.get("load_import", 0.0) + time.perf_counter() - read_started
        if len(raw) != amount * 50:
            raise ValueError("STL changed or was truncated")
        yield np.frombuffer(raw, dtype=STL_DTYPE)["vertices"]


def build_preview(path: Path, mode: str, *, timings: dict[str, float] | None = None) -> PreviewGeometry | None:
    timings = timings if timings is not None else {}
    start = time.perf_counter()
    count = binary_triangle_count(path)
    timings["load_import"] = time.perf_counter() - start
    if count is None:
        return None
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        low = np.full(3, np.inf)
        high = -low
        for vertices in _records(stream, count, timings):
            if not np.isfinite(vertices).all():
                return None
            low = np.minimum(low, vertices.min(axis=(0, 1)))
            high = np.maximum(high, vertices.max(axis=(0, 1)))
        span = float(np.max(high - low))
        if not np.isfinite(span) or span <= 1e-20 or np.abs([low, high]).max() > 1e30:
            return None
        # Common isotropic grid retains proportions. Retry coarser if a pathological
        # model exceeds the strict retained-face budget; source arrays stay bounded.
        grid = {"proxy": 64, "balanced": 96, "high": 120}.get(mode, 64)
        while grid >= 16:
            keys = np.empty(0, dtype=np.uint64)
            normals = np.empty((0, 3), dtype=np.float32)
            overflow = False
            for vertices in _records(stream, count, timings):
                if not np.isfinite(vertices).all() or np.any(vertices < low) or np.any(vertices > high):
                    return None
                q = np.rint((vertices.astype(np.float64) - low) * (grid / span)).astype(np.uint64)
                ids = q[:, :, 0] | (q[:, :, 1] << 7) | (q[:, :, 2] << 14)
                good = (ids[:, 0] != ids[:, 1]) & (ids[:, 1] != ids[:, 2]) & (ids[:, 0] != ids[:, 2])
                ids = ids[good]
                tri = vertices[good].astype(np.float64)
                face_n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
                lengths = np.linalg.norm(face_n, axis=1)
                valid = lengths > 1e-30
                ids = ids[valid]
                face_n = (face_n[valid] / lengths[valid, None]).astype(np.float32)
                # Cyclic canonicalization merges duplicate clustered triangles while
                # preserving winding and intentionally distinct opposite faces.
                first = ids.argmin(axis=1)
                ids = np.take_along_axis(ids, (first[:, None] + np.arange(3)) % 3, axis=1)
                packed = ids[:, 0] | (ids[:, 1] << 21) | (ids[:, 2] << 42)
                combined = np.concatenate((keys, packed))
                keys, index = np.unique(combined, return_index=True)
                normals = np.concatenate((normals, face_n))[index]
                if len(keys) > MAX_PREVIEW_TRIANGLES:
                    overflow = True
                    break
            if not overflow:
                break
            grid //= 2
        if overflow or len(keys) == 0:
            return None
        after = os.fstat(stream.fileno())
        current = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or (before.st_size, before.st_mtime_ns) != (current.st_size, current.st_mtime_ns):
            return None
    ids = np.stack([keys & ((1 << 21)-1), (keys >> 21) & ((1 << 21)-1), keys >> 42], axis=1)
    q = np.stack([ids & 127, (ids >> 7) & 127, ids >> 14], axis=-1)
    triangles = (q.astype(np.float32) / grid - (high-low).astype(np.float32) / (2*span)).astype(np.float32)
    return PreviewGeometry(triangles, normals)
