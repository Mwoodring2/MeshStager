"""File record model.

Roundup v1 keeps file info intentionally lightweight:
- no parsing of 3D file contents
- no heavy metadata extraction
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from meshcorral.services.asset_family import detect_asset_family


@dataclass(frozen=True, slots=True)
class FileRecord:
    """
    Lightweight record for a filesystem asset file.

    Prime Performance v0.7: ``size_bytes`` and ``modified_time`` are optional so the
    UI can render filenames immediately while a background enrichment pass fills in
    stat metadata for visible rows.
    """

    path: Path
    name: str
    extension: str
    parent_folder: str
    size_bytes: int | None = None
    modified_time: float | None = None
    metadata_source: str | None = None
    """``\"cache\"`` when stat fields were hydrated from SQLite; ``\"stat\"`` after enrichment."""
    name_lower: str = field(init=False)
    asset_family: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name_lower", self.name.lower())
        object.__setattr__(self, "asset_family", detect_asset_family(self.extension or self.name))

    def with_metadata(
        self,
        *,
        size_bytes: int | None,
        modified_time: float | None,
        metadata_source: str | None = "stat",
    ) -> FileRecord:
        """Return a new record carrying fresh stat metadata (frozen dataclass copy)."""
        return FileRecord(
            path=self.path,
            name=self.name,
            extension=self.extension,
            parent_folder=self.parent_folder,
            size_bytes=size_bytes,
            modified_time=modified_time,
            metadata_source=metadata_source,
        )

    def is_metadata_enriched(self) -> bool:
        """True when stat-backed metadata has been resolved at least once."""
        return self.size_bytes is not None and self.modified_time is not None

    @staticmethod
    def from_path(path: Path) -> FileRecord:
        """Create a record from a filesystem path.

        Raises:
            FileNotFoundError: if the file does not exist.
            OSError: for permission issues or stat failures.
            ValueError: if the provided path is not a file.
        """
        if not path.exists():
            raise FileNotFoundError(str(path))
        if not path.is_file():
            raise ValueError(f"Path is not a file: {path}")

        stat = path.stat()
        return FileRecord(
            path=path,
            name=path.name,
            extension=path.suffix.lower(),
            parent_folder=path.parent.name,
            size_bytes=int(stat.st_size),
            modified_time=float(stat.st_mtime),
        )

