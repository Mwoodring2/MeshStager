# Warm Repository Reopen

## Previous behavior and implementation

Previously every reopen needed a filesystem walk before it could populate records. The existing metadata cache only described individual assets, without proof that a source scan had completed. Scan-time cache reads/writes were per asset. A live Qt regression also demonstrated that the scan-start lambda dispatched work on the GUI thread; the connection now targets a QObject-bound worker slot.

The existing FolderScanRunner/QThread now reads a complete catalog before filesystem validation, emits cached records to the existing models, then verifies with the existing scanner. Source selection and startup restoration automatically reopen only previously completed matching sources. First-time folders retain the existing Scan Source workflow. The existing filters, sort, Tags, Favorites and Collections still process the same FileRecord objects. Status reads “Verifying source…” until completion. No new UI or database was introduced.

## Schema and completeness

Metadata cache schema version advances from 1 to 2 without deleting existing asset rows. Two tables are added inside metadata_cache.sqlite:

- source_catalog_state: source_root primary key, recursive, extensions_signature, last_completed_scan, cached_record_count, snapshot_complete.
- source_catalog_members: composite primary key (source_root, path).

The membership table is needed because enrichment and overlapping-root scans can update the same per-asset rows. It preserves the last completed membership independently without duplicating asset metadata. Source identity is lexical absolute/case-normalized; extension signatures are sorted and normalized. Only a matching root, recursive setting, extension signature and complete marker can load warm. An incomplete/pruned membership fails closed to a normal scan. Only the most recent mode/signature for each root is retained.

One joined SELECT obtains all rows and thumbnail hints. Lightweight FileRecords are constructed without stat or resolve calls and sorted with the existing case-insensitive path ordering. Read connections are private and closed explicitly. After successful traversal, one transaction batches verified records through a temporary table, updates metadata, membership and completion state, and marks missing prior members. There are no per-asset SELECTs or commits in this publication path. Existing metadata enrichment remains unchanged.

## Verification, cancellation and thumbnails

Warm verification reads fresh size/mtime using the existing scanner. Unchanged records retain their cached objects; new/changed rows replace them; genuinely missing rows leave the browser and are marked file_exists=0. A single final model/filter refresh reconciles the results without duplicate append batches. Thumbnail hints survive for unchanged stat fingerprints; changed fingerprints discard stale persisted hints and evict only that source from the existing in-memory thumbnail caches/index. Disk PNG and geometry caches are not deleted, versioned or redesigned.

Hints prime the existing ready cache on the worker after cached-record emission. Warm startup and completion skip the thumbnail-directory index rebuild and redundant metadata enrichment; automatic rendering is suppressed while warm verification runs, then normal queue policies resume. No geometry is loaded by the catalog reader.

Cancellation is checked during traversal and immediately before transaction commit; cancellation before publication rolls back and retains the previous snapshot. A cancellation arriving after a successful commit does not undo the already-complete snapshot. Failed/root-offline scans do not publish or mark missing. The scanner retains its traversal but uses opt-in error propagation because previously swallowed directory/stat errors could falsely authorize removals. The existing offline-source UX is retained; no offline library was added. ESC tokens and shutdown coordination are unchanged.

## Benchmark

Measured locally on Windows with Python 3.13.14, using scripts/benchmark_warm_catalog.py and synthetic SQLite rows (no mesh files). Single measured read per size, including SQL retrieval, FileRecord construction and sorting; excludes snapshot insertion, filesystem verification and Qt model paint:

| Rows | SQLite to FileRecords |
| ---: | ---: |
| 1,000 | 8.719 ms |
| 10,000 | 76.192 ms |
| 50,000 | 451.263 ms |

These are local measurements, not NAS verification or end-to-end UI guarantees.

## Validation

New focused regressions cover completeness, matching scope, stable order, 10k no-stat batch reads, transaction rollback, failed/canceled/offline scans, additions/removals/changes, object reuse, duplicate prevention, hints, overlapping roots, strict traversal errors, and a real QThread/UI display-before-verification test. Existing scan, ESC, source persistence, lifecycle, collection and thumbnail-cache tests are included in the focused run.

Focused validation passed: 124 broader regressions in 397.836 s; final core/startup checks, 29 tests in 15.196 s; Tags/Favorites, 14 tests in 0.282 s. The latter runs cover final adjustments and overlap the broader selection. The complete suite ran exactly once: 817 tests in 1062.773 s, with one failure and two expected skips. The failure was the new live UI test's timing-sensitive harness: it used a four-second event-processing deadline and an automatic five-second verification release. Under the full suite's queued Qt work, the assertion could run after that release or before the cached signal was serviced. The test now holds verification until explicitly released in the assertion/finally block and gives queued events a bounded 30-second allowance. No production code changed after the full run.

Final targeted rerun: 29 warm/source/worker-lifecycle tests passed in 30.495 s. The full suite was not repeated, per the one-run constraint; it must not be described as an entirely green full-suite run.

The two skips were missing TestSource/TestDestination acceptance fixtures and the physical multi-monitor sizing test on this single-monitor host. Log audit: zero Qt/thread/deleted-object warnings and zero UserWarning/RuntimeWarning/DeprecationWarning matches. The full log contains the one unittest assertion traceback described above; final focused logs contain zero failures or tracebacks. git diff --check passed.

Logs are in the Windows temporary directory: meshstager-warm-focused.log, meshstager-warm-core.log, meshstager-warm-tags-favorites.log, meshstager-warm-full.log and meshstager-warm-final-focused.log.

## Limits and preserved systems

Old installations need one successful scan to acquire a completion marker. Full filesystem verification still costs one walk plus per-file stats and may be slow on NAS, but it runs off the UI thread. The batch read/sort/model refresh requires memory proportional to catalog size. Root availability checks retain existing source UI behavior. File identity changes are detected by size/mtime, matching existing cache semantics. This does not add content hashing, incremental model machinery, a second cache, or a filesystem watcher.

APP_VERSION, thumbnail style version, rendering/routing/preview geometry, Blender execution, scan traversal order, cancellation token, enrichment architecture, gallery/table architecture, Inspector, Tags/Favorites/Collections, search parser, layouts/dialogs, transfer operations, shutdown and rebrand behavior are preserved. The bounded changes to scan error propagation, worker dispatch and per-source in-memory invalidation address demonstrated correctness defects needed for warm verification.

## Files changed for this task

- meshcorral/services/metadata_cache.py
- meshcorral/services/scan_cache_diagnostics.py
- meshcorral/services/scanner.py
- meshcorral/ui/scan_runner.py
- meshcorral/ui/main_window.py
- meshcorral/ui/thumbnail_controller.py
- meshcorral/app/bridge/thumb_index.py
- meshcorral/tests/test_warm_repository_reopen.py
- scripts/benchmark_warm_catalog.py
- docs/WARM_REPOSITORY_REOPEN.md

Earlier heavy-mesh/STL changes already present in the working tree were preserved.

## Subsequent verification closure (2026-09-12)

The required new full baseline ran 817 tests in 1057.198 s: 814 passed, one live test-harness failure, zero errors, two expected skips. Investigation isolated the live test from explicitly organization-scoped SettingsService preferences and unrelated native-health/autotrim startup callbacks; construction events are drained before testing cached display. Warm production code was unchanged. The corrected settings/warm/worker-lifecycle focused group passed 45 tests in 11.404 s with no specified runtime-warning matches. Phase A was closed using the mission's test-harness-only exception; the final Housekeeping full regression also rechecks this frozen baseline.

Final Housekeeping regression closure: 867 tests in 2634.946 s; 865 passed, zero failures/errors, two known fixture/environment skips. The corrected warm-reopen UI test passed within this complete run. The required Qt/Python warning audit, including ResourceWarning, was clean. Warm production architecture was not changed by this mission.
