# Tier 2.3 — Collections

Collections are manually curated groups of assets independent of folders, tags,
favorites, and future saved searches. An asset may belong to multiple collections.
The displayed application version remains `0.1.0-rc1`.

## Architecture

- `services/collections/collection_repository.py`: one synchronous SQLite connection,
  schema setup, stable IDs, deterministic ordering, indexed membership lookups,
  atomic bulk writes, counts, and canonical paths.
- `services/collections/collection_service.py`: validated operations, safe user-facing
  errors, and immutable membership snapshots.
- `ui/collections/collection_controller.py`: owns the service and snapshot generation,
  coordinates dialogs, refreshes search and selection, and closes storage on shutdown.
- `ui/collections/collection_widgets.py`: compact sidebar and Metadata controls;
  responsive dialogs with scrollable content and pinned Save/Cancel actions.
- Existing search/filter functions accept optional collection data. MainWindow only
  wires the controller into the sidebar, shared context menu, filtering, and shutdown.

There are no new worker threads. Existing async search workers receive captured
in-memory collection providers, never a SQLite connection. Collection-aware requests
use independent indexes so overlapping generations cannot overwrite each other. Collection edits refresh
user metadata and the in-memory search index using the same rebuild boundary as Tags.
They do not start scans or touch thumbnail/metadata caches.

## Persistence

Database: `USER_DATA_DIR / cache / asset_collections.sqlite`, normally
`%LOCALAPPDATA%/MeshStager/cache/asset_collections.sqlite` on Windows.

Schema version 1:

- `collections`: autoincrement integer `id`, display `name`, unique case-folded
  `name_key`, UTC `created_at` and `modified_at` timestamps.
- `collection_members`: `(collection_id, asset_path)` composite primary key;
  foreign key to collections with `ON DELETE CASCADE` and a separate path index.
- `collection_meta`: schema version.

Names are trimmed, required, limited to 120 characters, and cannot contain control
characters. Unicode case-folding prevents case-insensitive duplicates. Renaming
preserves identity and membership. Deleting a collection only deletes its database
record and membership rows. No collection operation moves, deletes, or rewrites an
asset file. Bulk add/remove uses one transaction and returns the actual changed count.
Repeated adds and absent-member removals are safe.

Storage reuses `_norm_path_key`, the Tags/Favorites canonical path helper. It does not
require assets to exist and never prunes membership for missing files or offline drives.
The UI canonicalizes FileRecord paths with the same helper before membership lookup.
Collections and membership survive restart; the browser starts with All Assets rather
than restoring a collection filter. Existing source/workspace persistence is unchanged.

## UI and filter behavior

The Collections sidebar offers All Assets, alphabetically ordered collections with
total member counts, New, Rename, and Delete. Counts include offline/unloaded members.
Selection intersects the current loaded dataset with collection membership and all
existing filters, preserving source, asset mode, and browser sort order. All Assets or
Reset Filters clears collection selection. No rows are fabricated for missing members.

The existing empty-state renderer distinguishes an empty collection from a collection
whose members are outside the loaded dataset. If loaded members are excluded by other
filters, the existing No matching results copy remains in use.

The Metadata tab displays a compact collection summary and Add/Remove controls for a
single asset. The shared gallery/table context menu provides Add to Collection and
Remove from Collection for one or many selected assets. Each operation applies to all
selected assets; removal lists only collections present on at least one selected asset.
There is no three-state membership matrix. Deletion always asks for confirmation and
states that asset files remain on disk. Invalid input stays in the dialog for correction.
Storage failures use logging/status or inline dialog feedback without raw SQL details.

## Search

- `collection:"Print Ready"`
- `collection:PrintReady`
- `helmet tag:approved collection:"Client Review" ext:stl`

Collection names match exactly and case-insensitively, following Tag predicate behavior.
Spaces use the existing double-quote parser convention. Collection names do not enter
plain-text search, so unrelated queries retain their prior meaning. Collection and
sidebar filters intersect. Rename and membership edits refresh the index without scans.

## Validation

New tests cover schema/reopen, Unicode duplicate prevention, rename, cascade deletion,
file safety, missing paths, canonicalization, batch idempotency, counts, transaction
rollback, safe errors, immutable snapshots, sidebar/inspector/dialog behavior, search
composition, async delivery, and real MainWindow source/mode/filter/lifecycle behavior.

Run focused tests before the full suite:

```powershell
python -m unittest meshcorral.tests.test_collection_repository meshcorral.tests.test_collection_service -v
python -m unittest meshcorral.tests.test_collection_ui meshcorral.tests.test_collection_search -v
python -m unittest meshcorral.tests.test_collection_main_window -v
python -m unittest discover -s meshcorral/tests -t . -v
```

Final validation on Python 3.13.14 / PySide6 6.11.2:

| Check | Result |
| --- | --- |
| New Collections tests | 55 passed |
| Final focused run, including existing search regressions | 70 passed (8.451 seconds) |
| Full suite | 759 tests, OK (1087.973 seconds), 2 skips |
| Requested Qt/error-pattern scan | 0 matches |
| Task-specific whitespace check | Clean |

The skips are the existing missing TestSource/TestDestination acceptance fixture and
`test_settings_dialog_sized_for_parent_screen_not_primary`, which requires multiple
screens. Qt exposed one screen in this environment; synthetic geometry tests passed.
Thus the requested single-skip target requires a multi-monitor validation host.

The first full run exposed an order-dependent async test callback wait. The test was
isolated from unrelated application timers and the final full run above passed. No
production behavior was weakened and no existing tests were removed or relaxed.

The warning scan covered `QThread:`, `QFont::`, `Traceback`, `has been deleted`,
`Internal C++`, `QObject::`, and `QWidget:`. Manual acceptance status follows below. The original local `.venv` was broken; an isolated `.venv-collections` with
Python 3.13 was provisioned for validation without replacing it.

## Manual acceptance status

Automated tests exercise create/rename/delete, multiple memberships, bulk add/remove,
file safety, source/mode preservation, search refresh, restart persistence, and shutdown.
The new controls were rendered offscreen with Segoe UI and visually inspected.

The source build was launched after the final tests; its MeshStager window was
present and responding. The interactive 22-step desktop acceptance checklist remains pending: the Computer Use
runtime could not start because its Windows sandbox helper failed during setup.
The test environment also exposes only one Qt screen, so physical multi-monitor checks
cannot run here. No manual UI checks are claimed as completed.

To run the updated source with the isolated Python 3.13 environment from the project root:

```powershell
.\.venv-collections\Scripts\python.exe -m meshcorral.app
```

The existing frozen executable was not rebuilt by this task.

## Changed-file inventory

Added:

- `meshcorral/services/collections/__init__.py`
- `meshcorral/services/collections/collection_repository.py`
- `meshcorral/services/collections/collection_service.py`
- `meshcorral/ui/collections/__init__.py`
- `meshcorral/ui/collections/collection_controller.py`
- `meshcorral/ui/collections/collection_widgets.py`
- `meshcorral/tests/test_collection_repository.py`
- `meshcorral/tests/test_collection_service.py`
- `meshcorral/tests/test_collection_search.py`
- `meshcorral/tests/test_collection_ui.py`
- `meshcorral/tests/test_collection_main_window.py`
- `docs/TIER2_COLLECTIONS.md`

Modified for this feature:

- `meshcorral/services/search_service.py`
- `meshcorral/ui/search/query_parser.py`
- `meshcorral/ui/search/search_index.py`
- `meshcorral/ui/search/async_filter_engine.py`
- `meshcorral/ui/main_window.py`
- `meshcorral/ui/asset_inspector.py`
- `meshcorral/ui/inspector/inspector_tabs.py`
- `meshcorral/ui/inspector/metadata_panel.py`
- `meshcorral/ui/empty_states.py`
- `docs/CHANGELOG.md`

Pre-existing uncommitted hardening changes were preserved. The scan pipeline,
thumbnail routing/cache, metadata cache, gallery/table architecture, inspector shell,
dialog placement, and shutdown architecture were not redesigned. Only the listed
additive filter, widget-accessor, and lifecycle integration points were introduced.

## Current limits and extension boundary

Collections filter loaded assets; they do not discover files, track external renames,
watch drives, or synchronize multiple running MeshStager processes. Membership follows
the established path identity rules. Nested groups, manual ordering, covers, cloud sync,
notes, smart collections, and saved searches are outside Tier 2.3. Stable IDs and the
repository/service boundary allow later schema evolution without speculative columns.
