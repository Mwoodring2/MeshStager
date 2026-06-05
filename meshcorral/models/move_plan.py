"""Move planning model.

Moves are planned and reviewed (dry-run) before any filesystem changes happen.
The service layer builds a list of MovePlan items for preview and execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class MovePlan:
    """A single move action used for dry-run preview and execution."""

    source_path: Path
    destination_path: Path
    status: str
    message: str = ""

