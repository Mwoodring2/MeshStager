"""Regenerate Windows ICO files from ``assets/icons/MeshStager_icon.png``."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "assets" / "icons" / "MeshStager_icon.png"
OUT_ASSETS = REPO / "assets" / "icons" / "MeshStager_icon.ico"
OUT_LEGACY = REPO / "meshcorral.ico"
SIZES: list[tuple[int, int]] = [
    (16, 16),
    (32, 32),
    (48, 48),
    (64, 64),
    (128, 128),
    (256, 256),
]


def _write_ico(path: Path, img: Image.Image) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, format="ICO", sizes=SIZES)
    print(f"Wrote {path} ({path.stat().st_size} bytes)")


def main() -> None:
    """Build official and legacy ICO paths from the PNG source asset."""
    if not SRC.is_file():
        raise SystemExit(f"Missing {SRC}")
    opened = Image.open(SRC)
    if opened.mode not in ("RGB", "RGBA"):
        opened = opened.convert("RGBA")
    _write_ico(OUT_ASSETS, opened)
    _write_ico(OUT_LEGACY, opened)


if __name__ == "__main__":
    main()
