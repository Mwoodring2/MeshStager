"""
CPU mesh preview rasterization (no GPU).

* **balanced** / **high**: solid shaded triangle surface (professional default).
* **proxy**: fast improved vertex splat for large/network files.
"""

from __future__ import annotations

import io
import math
from typing import Any

import numpy as np


def prepare_mesh_arrays(mesh: Any) -> tuple[np.ndarray, np.ndarray]:
    """Normalize mesh to centered unit-scale vertices and normals (Nx3 each)."""
    if not hasattr(mesh, "vertices") or mesh.vertices is None:
        raise RuntimeError("Mesh has no vertices.")
    v = np.asarray(mesh.vertices, dtype=np.float32)
    if v.size == 0:
        raise RuntimeError("Mesh has no vertices.")

    n_raw = getattr(mesh, "vertex_normals", None)
    if n_raw is not None:
        n = np.asarray(n_raw, dtype=np.float32)
        if n.shape != v.shape:
            n = _normals_from_mesh(mesh, v)
    else:
        n = _normals_from_mesh(mesh, v)

    c = v.mean(axis=0)
    v = v - c
    scale = float(np.max(np.linalg.norm(v, axis=1)))
    if not math.isfinite(scale) or scale <= 1e-8:
        scale = 1.0
    v = v / scale
    n = n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-8)
    return v, n


def _normals_from_mesh(mesh: Any, v: np.ndarray) -> np.ndarray:
    """Smooth vertex normals when the loader did not provide them."""
    faces = getattr(mesh, "faces", None)
    if faces is None or len(faces) == 0:
        return v.copy()
    faces_a = np.asarray(faces, dtype=np.int32)
    accum = np.zeros_like(v, dtype=np.float32)
    counts = np.zeros((v.shape[0],), dtype=np.float32)
    for f0, f1, f2 in faces_a:
        e1 = v[f1] - v[f0]
        e2 = v[f2] - v[f0]
        fn = np.cross(e1, e2)
        norm = float(np.linalg.norm(fn))
        if norm < 1e-12:
            continue
        fn = (fn / norm).astype(np.float32)
        for idx in (int(f0), int(f1), int(f2)):
            accum[idx] += fn
            counts[idx] += 1.0
    mask = counts > 0
    accum[mask] /= counts[mask, None]
    accum[~mask] = v[~mask]
    return accum


def compute_geometry_metadata(mesh: Any) -> dict[str, int | float | None]:
    """Cheap stats used for diagnostics (faces, vertices, bounds volume)."""
    vertices = getattr(mesh, "vertices", None)
    faces = getattr(mesh, "faces", None)
    vertex_count = int(len(vertices)) if vertices is not None else 0
    face_count = int(len(faces)) if faces is not None else None
    bounds = getattr(mesh, "bounds", None)
    volume: float | None = None
    if bounds is not None and len(bounds) >= 2:
        extents = bounds[1] - bounds[0]
        volume = float(extents[0] * extents[1] * extents[2])
    return {
        "vertex_count": vertex_count,
        "face_count": face_count,
        "bounds_volume": volume,
    }


def _rotation_mats() -> tuple[np.ndarray, np.ndarray]:
    rz = math.radians(45.0)
    rx = math.radians(35.264)
    cz, sz = math.cos(rz), math.sin(rz)
    cx, sx = math.cos(rx), math.sin(rx)
    rmat = np.array(
        [[cz, -sz, 0.0], [sz, cz, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float32,
    )
    xmat = np.array(
        [[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]],
        dtype=np.float32,
    )
    return xmat @ rmat, rmat


def _project_vertices(
    v: np.ndarray,
    n: np.ndarray,
    *,
    size_px: int,
    pad: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, int, int]:
    """Return rotated vertices, normals, pixel coords (float), depth, width, height."""
    rot, _ = _rotation_mats()
    v2 = (rot @ v.T).T
    n2 = (rot @ n.T).T
    xy = v2[:, :2]
    z = v2[:, 2].astype(np.float32)

    lo = xy.min(axis=0)
    hi = xy.max(axis=0)
    span = np.maximum(hi - lo, 1e-6)
    w = h = int(size_px)
    usable = (1.0 - 2.0 * pad) * float(min(w, h))
    s = float(usable) / float(max(span[0], span[1]))
    xy_n = (xy - (lo + hi) * 0.5) * s
    px = (xy_n[:, 0] + (w * 0.5)).astype(np.float32)
    py = ((h * 0.5) - xy_n[:, 1]).astype(np.float32)
    return v2, n2, px, py, z, w, h


def rasterize_mesh_preview(
    mesh: Any,
    v: np.ndarray,
    n: np.ndarray,
    *,
    size_px: int,
    render_mode: str,
    max_points: int,
    max_faces: int,
) -> bytes:
    """Dispatch raster style by render mode."""
    mode = (render_mode or "balanced").strip().lower()
    if mode == "proxy":
        return rasterize_vertices_splat(
            v,
            n,
            size_px=size_px,
            max_points=max_points,
            fast=True,
        )
    surface = rasterize_mesh_surface(
        mesh,
        v,
        n,
        size_px=size_px,
        max_faces=max_faces,
        high_quality=(mode == "high"),
    )
    if surface is not None:
        return surface
    return rasterize_vertices_splat(
        v,
        n,
        size_px=size_px,
        max_points=max_points,
        fast=False,
    )


def rasterize_vertices_splat(
    v: np.ndarray,
    n: np.ndarray,
    *,
    size_px: int,
    max_points: int,
    fast: bool,
) -> bytes:
    """Improved vertex splat for proxy/fast paths (not speckle-first)."""
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError("Missing dependency: Pillow") from e

    pad = 0.07 if fast else 0.06
    _v2, n2, px, py, z, w, h = _project_vertices(v, n, size_px=size_px, pad=pad)

    if px.shape[0] > max_points:
        step = max(1, int(px.shape[0] / max_points))
        px = px[::step]
        py = py[::step]
        z = z[::step]
        n2 = n2[::step]

    px_i = px.astype(np.int32)
    py_i = py.astype(np.int32)
    inside = (px_i >= 0) & (px_i < w) & (py_i >= 0) & (py_i < h)
    if not bool(np.any(inside)):
        raise RuntimeError("Projection produced no visible points.")
    px_i = px_i[inside]
    py_i = py_i[inside]
    z = z[inside]
    n2 = n2[inside]

    light = np.array([0.35, 0.55, 0.75], dtype=np.float32)
    light = light / float(np.linalg.norm(light) + 1e-8)
    nn = n2 / (np.linalg.norm(n2, axis=1, keepdims=True) + 1e-8)
    lambert = np.clip((nn @ light).astype(np.float32), 0.0, 1.0)
    ambient = 0.32 if fast else 0.28
    val = (50.0 + 190.0 * (ambient + (1.0 - ambient) * lambert)).astype(np.uint8)

    order = np.argsort(z)
    px_i = px_i[order]
    py_i = py_i[order]
    val = val[order]

    img = np.zeros((h, w, 4), dtype=np.uint8)
    splat = 2 if fast else 3
    for dx in range(-splat, splat + 1):
        for dy in range(-splat, splat + 1):
            if fast and (abs(dx) + abs(dy) > splat):
                continue
            x2 = px_i + dx
            y2 = py_i + dy
            ok = (x2 >= 0) & (x2 < w) & (y2 >= 0) & (y2 < h)
            x2 = x2[ok]
            y2 = y2[ok]
            v2c = val[ok]
            img[y2, x2, 0] = v2c
            img[y2, x2, 1] = v2c
            img[y2, x2, 2] = v2c
            img[y2, x2, 3] = 255

    im = Image.fromarray(img, mode="RGBA")
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    out = buf.getvalue()
    if not out:
        raise RuntimeError("Failed to encode PNG.")
    return out


def rasterize_mesh_surface(
    mesh: Any,
    v: np.ndarray,
    n: np.ndarray,
    *,
    size_px: int,
    max_faces: int,
    high_quality: bool,
) -> bytes | None:
    """Solid shaded triangle raster for balanced/HQ thumbnails."""
    faces_raw = getattr(mesh, "faces", None)
    if faces_raw is None:
        return None
    faces = np.asarray(faces_raw, dtype=np.int32)
    if faces.ndim != 2 or faces.shape[1] != 3 or faces.shape[0] == 0:
        return None

    try:
        from PIL import Image, ImageDraw  # type: ignore[import-not-found]
    except ImportError as e:
        raise RuntimeError("Missing dependency: Pillow") from e

    pad = 0.06
    v2, _n2, px, py, z, w, h = _project_vertices(v, n, size_px=size_px, pad=pad)
    if faces.shape[0] > max_faces:
        step = max(1, int(faces.shape[0] / max_faces))
        faces = faces[::step]

    rot, _ = _rotation_mats()
    light = np.array([0.3, 0.58, 0.78], dtype=np.float32)
    light = light / float(np.linalg.norm(light) + 1e-8)

    zbuf = np.full((h, w), -1e9, dtype=np.float64)
    shade = np.zeros((h, w), dtype=np.uint8)
    alpha = np.zeros((h, w), dtype=np.uint8)

    edge = 1 if high_quality else 0
    ambient = 0.22 if high_quality else 0.26

    for f0, f1, f2 in faces:
        i0, i1, i2 = int(f0), int(f1), int(f2)
        tri = np.array(
            [
                [px[i0], py[i0], z[i0]],
                [px[i1], py[i1], z[i1]],
                [px[i2], py[i2], z[i2]],
            ],
            dtype=np.float64,
        )
        e1 = v2[i1] - v2[i0]
        e2 = v2[i2] - v2[i0]
        fn = np.cross(e1, e2)
        fn_len = float(np.linalg.norm(fn))
        if fn_len < 1e-12:
            continue
        fn = fn / fn_len
        lambert = float(np.clip(np.dot(fn, light), 0.0, 1.0))
        val = int(48 + 192 * (ambient + (1.0 - ambient) * lambert))
        val = max(0, min(255, val))

        xmin = int(max(0, math.floor(min(tri[:, 0])) - edge))
        xmax = int(min(w - 1, math.ceil(max(tri[:, 0])) + edge))
        ymin = int(max(0, math.floor(min(tri[:, 1])) - edge))
        ymax = int(min(h - 1, math.ceil(max(tri[:, 1])) + edge))
        if xmin > xmax or ymin > ymax:
            continue

        x0, y0, z0p = tri[0]
        x1, y1, z1p = tri[1]
        x2, y2, z2p = tri[2]
        area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if abs(area) < 1e-8:
            continue

        for yi in range(ymin, ymax + 1):
            for xi in range(xmin, xmax + 1):
                w0 = ((x1 - x0) * (yi - y0) - (xi - x0) * (y1 - y0)) / area
                w1 = ((x2 - x1) * (yi - y1) - (xi - x1) * (y2 - y1)) / area
                w2 = 1.0 - w0 - w1
                if w0 < -0.001 or w1 < -0.001 or w2 < -0.001:
                    continue
                z_interp = w0 * z0p + w1 * z1p + w2 * z2p
                if z_interp <= zbuf[yi, xi]:
                    continue
                zbuf[yi, xi] = z_interp
                shade[yi, xi] = val
                alpha[yi, xi] = 255

    if not bool(np.any(alpha)):
        return None

    img = np.zeros((h, w, 4), dtype=np.uint8)
    img[:, :, 0] = shade
    img[:, :, 1] = shade
    img[:, :, 2] = shade
    img[:, :, 3] = alpha

    if high_quality and edge:
        rgba = Image.fromarray(img, mode="RGBA")
        draw = ImageDraw.Draw(rgba)
        outline = int(max(40, 68))
        for f0, f1, f2 in faces[:: max(1, len(faces) // 2000)]:
            pts = [
                (float(px[int(f0)]), float(py[int(f0)])),
                (float(px[int(f1)]), float(py[int(f1)])),
                (float(px[int(f2)]), float(py[int(f2)])),
            ]
            draw.polygon(pts, outline=(outline, outline, outline, 90))
        buf = io.BytesIO()
        rgba.save(buf, format="PNG", optimize=True)
        return buf.getvalue()

    im = Image.fromarray(img, mode="RGBA")
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def rasterize_vertices(
    v: np.ndarray,
    n: np.ndarray,
    *,
    size_px: int,
    max_points: int,
) -> bytes:
    """Backward-compatible entry: improved splat (non-fast)."""
    return rasterize_vertices_splat(
        v,
        n,
        size_px=size_px,
        max_points=max_points,
        fast=False,
    )
