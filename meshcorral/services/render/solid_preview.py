"""Supersampled solid compact triangles using Pillow's C polygon rasterizer."""
from __future__ import annotations
import io
import numpy as np
from PIL import Image, ImageDraw
from meshcorral.services.render.mesh_rasterizer import _rotation_mats
from meshcorral.services.render.preview_geometry import PreviewGeometry


def render_solid_preview(geometry: PreviewGeometry, size_px: int):
    """Return RGBA image, keeping PNG encoding separately measurable.

Depth-sorted small clustered faces approximate visibility without Python pixel
loops. Original face normals provide neutral directional shading. No wireframe,
point splats, floor, grid, or morphology that could fill intentional openings.
"""
    scale = 3 if size_px <= 192 else 2
    side = int(size_px) * scale
    rotation, _ = _rotation_mats()
    triangles = geometry.triangles @ rotation.T
    xy = triangles[:, :, :2]
    low = xy.min(axis=(0, 1))
    high = xy.max(axis=(0, 1))
    span = float(np.max(high-low))
    if span <= 1e-12:
        raise ValueError("Empty preview projection")
    xy = (xy-(low+high)*0.5) * (side*0.88/span)
    xy[:, :, 0] += side*0.5
    xy[:, :, 1] = side*0.5-xy[:, :, 1]
    light = np.array([0.3, 0.58, 0.78], dtype=np.float32)
    light /= np.linalg.norm(light)
    lambert = np.clip((geometry.normals @ rotation.T) @ light, 0, 1)
    shade = (48+192*(0.28+0.72*lambert)).astype(np.uint8)
    order = np.argsort(triangles[:, :, 2].mean(axis=1), kind="stable")
    image = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    # Conversion once avoids three NumPy scalar conversions per vertex in loop.
    polygons = xy[order].reshape(-1, 6).tolist()
    for polygon, value in zip(polygons, shade[order].tolist()):
        draw.polygon(polygon, fill=(value, value, value, 255))
    return image.resize((size_px, size_px), Image.Resampling.LANCZOS)


def encode_preview_png(image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
