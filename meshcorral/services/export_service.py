"""Export file lists to CSV (single source of truth: ``ui.file_columns``)."""

from __future__ import annotations

import csv
from pathlib import Path

from meshcorral.models.file_record import FileRecord
from meshcorral.services.metadata.metadata_summary_registry import MetadataSummaryRegistry
from meshcorral.ui.file_columns import export_headers, export_row_for_record


def export_records_to_csv(
    records: list[FileRecord],
    output_path: str | Path,
    *,
    metadata_registry: MetadataSummaryRegistry | None = None,
) -> None:
    """Write records to a UTF-8 CSV: same columns and display values as the table."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(export_headers())
        for record in records:
            summary = (
                metadata_registry.get(record.path) if metadata_registry is not None else None
            )
            writer.writerow(export_row_for_record(record, summary))


class ExportService:
    """Thin wrapper for UI call sites; delegates to :func:`export_records_to_csv`."""

    def export_csv(
        self,
        records: list[FileRecord],
        target_csv: Path,
        *,
        metadata_registry: MetadataSummaryRegistry | None = None,
    ) -> None:
        """Write the current visible rows to a CSV file."""
        export_records_to_csv(records, target_csv, metadata_registry=metadata_registry)
