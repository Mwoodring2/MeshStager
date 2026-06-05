"""Module entrypoint.

This package lives at `meshcorral/app`, so:
- From repo root: `python -m meshcorral.app` (or `python -m app` with cwd set to
  the inner ``meshcorral/`` project folder on ``PYTHONPATH``)
- From inside the project folder: `python -m app`
"""

from __future__ import annotations

from .main import main


raise SystemExit(main())

