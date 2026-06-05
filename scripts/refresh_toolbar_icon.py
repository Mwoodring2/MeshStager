"""Build header/toolbar-optimized PNG from ``assets/icons/MeshStager_icon.png``."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "assets" / "icons" / "MeshStager_icon.png"
OUT = REPO / "assets" / "icons" / "MeshStager_icon_toolbar.png"
PREVIEW_SIZES: tuple[int, ...] = (24, 32, 40)
BLACK_CUTOFF = 28
CROP_MARGIN_RATIO = 0.04
CYAN_GAIN = 1.35
CYAN_MIN_CHANNEL = 90


def _rgba_array(img: Image.Image) -> np.ndarray:
    """Return an RGBA uint8 array for *img*."""
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return np.asarray(img, dtype=np.uint8)


def _transparent_background(rgba: np.ndarray) -> np.ndarray:
    """Drop near-black padding so the header icon sits on the strip background."""
    out = rgba.copy()
    rgb = out[..., :3].astype(np.int16)
    max_channel = rgb.max(axis=2)
    min_channel = rgb.min(axis=2)
    dark = (max_channel <= BLACK_CUTOFF) & (max_channel - min_channel <= 12)
    out[dark, 3] = 0
    return out


def _boost_cyan_silhouette(rgba: np.ndarray) -> np.ndarray:
    """Strengthen cyan edges for small header sizes without changing layout assets."""
    out = rgba.copy().astype(np.float32)
    rgb = out[..., :3]
    alpha = out[..., 3]
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    cyan_mask = (g >= CYAN_MIN_CHANNEL) & (b >= CYAN_MIN_CHANNEL) & ((g + b) > (r * 1.6))
    visible = alpha > 0
    boost = cyan_mask & visible
    rgb[boost, 1] = np.clip(rgb[boost, 1] * CYAN_GAIN, 0, 255)
    rgb[boost, 2] = np.clip(rgb[boost, 2] * CYAN_GAIN, 0, 255)
    rgb[boost, 0] = np.clip(rgb[boost, 0] * 0.85, 0, 255)
    out[..., :3] = rgb
    return out.astype(np.uint8)


def _tight_crop(rgba: np.ndarray) -> np.ndarray:
    """Crop to the cube/platform silhouette with a small, even margin."""
    visible = rgba[..., 3] > 8
    if not visible.any():
        return rgba
    rows = np.where(visible.any(axis=1))[0]
    cols = np.where(visible.any(axis=0))[0]
    top, bottom = int(rows[0]), int(rows[-1])
    left, right = int(cols[0]), int(cols[-1])
    height = bottom - top + 1
    width = right - left + 1
    margin_y = max(2, int(height * CROP_MARGIN_RATIO))
    margin_x = max(2, int(width * CROP_MARGIN_RATIO))
    h, w = rgba.shape[:2]
    top = max(0, top - margin_y)
    bottom = min(h - 1, bottom + margin_y)
    left = max(0, left - margin_x)
    right = min(w - 1, right + margin_x)
    return rgba[top : bottom + 1, left : right + 1]


def _preview_sizes_ok(img: Image.Image) -> bool:
    """Ensure the toolbar asset stays readable at common header sizes."""
    for size in PREVIEW_SIZES:
        preview = img.resize((size, size), Image.Resampling.LANCZOS)
        alpha = np.asarray(preview.getchannel("A"))
        if int((alpha > 16).sum()) < max(24, size * 4):
            return False
    return True


def build_toolbar_icon(source: Path = SRC, output: Path = OUT) -> Path:
    """Create the toolbar/header PNG and return its path."""
    if not source.is_file():
        raise FileNotFoundError(f"Missing source icon: {source}")
    with Image.open(source) as opened:
        rgba = _tight_crop(_boost_cyan_silhouette(_transparent_background(_rgba_array(opened))))
        result = Image.fromarray(rgba, mode="RGBA")
        if not _preview_sizes_ok(result):
            raise RuntimeError("Toolbar icon failed readability preview checks")
        output.parent.mkdir(parents=True, exist_ok=True)
        result.save(output, format="PNG", optimize=True)
    return output


def main() -> None:
    """Generate ``MeshStager_icon_toolbar.png`` from the official app icon."""
    path = build_toolbar_icon()
    print(f"Wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
