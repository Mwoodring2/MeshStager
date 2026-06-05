# Roundup UI Wireframe Checklist

## Main window

- top toolbar with:
  - **Scan Source** (one action: pick folder or drive root)
  - Include Subfolders
  - Filter Results
  - Type filter
  - Extension filter
  - Folder filter
  - Export Current View
  - About
- scanned source summary label
- working-set summary label (rows visible vs current scan)
- results table
- **Move & copy** side panel: destination, move, copy, reveal, path copy
- move summary block (ready/conflict preview for the chosen destination)
- status bar

## Required actions

- Scan Source
- Export Current View
- Browse destination
- Move selected…
- Copy selected to…
- Reveal selected in Explorer
- Copy selected path (clipboard)

## Previews (unchanged idea)

- table listing source → dest + status + message
- Confirm (Move or Copy) / Cancel

## Workflow feel

- scan-first: one source action, then filter the current working set
- move and copy share the same plan shape and safety checks; copy does not remove files from the scan list
