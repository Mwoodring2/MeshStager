"""PyInstaller / frozen entry (same behavior as ``python -m meshcorral.app`` for Roundup)."""

from __future__ import annotations

from meshcorral.app.main import main

if __name__ == "__main__":
    raise SystemExit(main())
