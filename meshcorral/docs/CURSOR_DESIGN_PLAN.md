# Roundup Cursor Design Plan

## Core interaction model

Roundup is **scan-first**, not search-first.

Expected user flow:

1. pick source folder or drive
2. scan
3. work from the scanned result set
4. refine with lightweight filters
5. move selected files safely

## UI rules

- scanning must be the primary action in the top bar
- the text field is **Filter Results** (post-scan), not a primary “search the disk” action
- filters apply only to the current scanned working set
- scanning a new source replaces the previous working set
- move summary must update live
- no hidden automation
- no assert statements in production code

## Architecture outline

- `models/`: dataclasses (`FileRecord`, `MovePlan`)
- `services/`: pure-Python services
  - `scanner.py`: filesystem traversal → `FileRecord`
  - `search_service.py`: in-memory filtering
  - `move_service.py`: build and execute move plans
  - `export_service.py`: CSV export
- `ui/`: PySide6
  - `file_table_model.py`, `main_window.py` (scan-first layout)
  - `dialogs.py`: move preview
  - `theme.py`
- `app/`: entrypoint, config, logging

## Scope guardrails

- do not add ML, GPU preview, or smart renaming in v1
- keep patches small and readable
- no database for v1 unless clearly needed later
