# Repository Housekeeping

## Purpose and safety

Housekeeping is generated classification over the existing indexed FileRecords. The left-side Housekeeping section filters the same Gallery/Table browser. It is separate from user Tags and manually curated Collections. Analyze Repository is explicit: opening a source loads previously generated findings, never automatically hashes it.

Analysis has no deletion, rename, move, overwrite, extraction, execution, or quarantine path. Asset files are opened read-only. Ignore/Restore only changes the findings store. No automatic choice of a preferred duplicate is made. Quarantine was deliberately omitted because it would expand this analysis milestone into file operations.

## Storage and completed generations

The disposable system store is USER_DATA_DIR/cache/asset_housekeeping.sqlite (the existing MeshStager local application data convention). Schema version 1 has:

- runs: canonical source root, completed generation UUID, completion timestamp, asset count.
- findings: source, stable finding ID, canonical asset path, type, severity, optional group ID, material identity, JSON details, generation, created/updated timestamps.
- suppressions: source, finding ID, material identity and ignore timestamp.

A service owns analysis orchestration; a repository owns SQLite. Each operation uses and closes its own connection. A completed analysis replaces that source's generated rows in one transaction using executemany; generation and rows commit together. Cancellation before commit rolls back. An unavailable source or fatal analysis/storage error retains the previous completed generation. Individual inaccessible/changed candidate files are skipped with an operational summary instead of being called broken. The new generation covers the analyzable indexed catalog; skipped checks remain explicitly incomplete evidence.

Suppression is keyed narrowly by finding and material identity. Exact duplicates use SHA-256 content identity; other findings use catalog size/mtime. Unchanged ignored findings remain ignored after restart/reanalysis, while changed identities reappear. Ignore and Restore are available in the existing Inspector. Ignored Findings is also a sidebar category. Clearing this disposable DB would remove its findings and suppression history; no automatic purge was added.

## Categories and evidence

| Category | Evidence / scope |
| --- | --- |
| Exact Duplicates | Same positive size, then matching complete SHA-256 hashes of distinct regular files. Stable content-derived group IDs. |
| Possible Duplicates | Same extension and normalized copy/version stem, within 1% size, with at least one copy/version suffix. Content identity is explicitly unproven. Exact matches are excluded from this category. |
| Archive + Extracted | Existing ZIP manifest member path/name and size matches a catalog asset beside the archive or beneath its stem-named folder. This is path/size evidence, not a content hash. |
| Broken Files | Very narrow MVP: short binary-looking STL containing NUL bytes and shorter than the 84-byte minimum header. No deep mesh validation. |
| Zero-byte Files | Indexed supported asset size is zero. |
| Missing Companion Files | OBJ mtllib references and simple MTL local texture references. Findings attach to the indexed OBJ when its companion MTL is not itself indexed. |
| Naming Issues | Token-bounded copy, numbered-copy, repeated-final, backup, old, temp/tmp and new suffixes. Words such as oldham, newton and copyright are not substring-matched. |
| Large Assets | Informational size at least 128 MiB; the threshold is centralized in policy/model code. Large printing assets are not considered inherently bad. |

Rules primarily use cached catalog metadata. Unknown sizes are not guessed or fetched for every asset. Rescan first if the catalog is stale. No geometry load or new renderer is involved.

## Candidate hashing and filesystem safety

The analyzer groups positive sizes before opening candidates. Singleton sizes are never hashed. Hashing reads 1 MiB chunks, checks cancellation between chunks, rejects nonregular/link/junction candidates, verifies cached stats before hashing, and checks file identity/size/mtime after reading. Growth beyond the initial size aborts that hash. Hard-link aliases are not counted as redundant physical copies. Cryptographic hashes distinguish same-size different-content files.

Worst case, every file shares a candidate size and all require hashing; the optimization avoids blind full-catalog hashing, not that unavoidable worst case. Hashes are recomputed on explicit analysis; no additional hash-cache architecture was added.

OBJ/MTL text reads are capped at 2 MiB per file. An incomplete trailing line is discarded. Malformed/binary text and ambiguous option-bearing texture references are skipped conservatively. Supported texture directives include map_Kd/map_Ka/map_Ks/map_d, map_bump/bump, disp/decal/norm with a single simple or double-quoted local filename. Universal DCC dependency resolution, URLs, arbitrary external references and complex map options are outside MVP.

Archive matching performs one read-only joined query over the existing archive-manifest cache. It verifies archive size/mtime, ignores unsafe absolute/traversing/drive-qualified/NUL member names, and never opens a ZIP for extraction or decompression. Archives absent from the asset catalog are described on their extracted assets; this does not inject archive rows into the scanner/browser. Uncached archives are left for the existing archive indexing infrastructure.

## Browser, Inspector, progress and lifecycle

The Housekeeping category predicate is one additive argument to the existing filter pipeline, composing with text/structured search, Tags, Favorites, Collections, extension/folder/category filters and sorting. It does not change source, initiate a scan, change Gallery/Table mode, or clear unrelated search. Counts are unique current-catalog assets per category. Reset Filters also resets Housekeeping.

The existing left panel now scrolls vertically when its sections exceed available height; its previous usable width is retained alongside the scrollbar. This prevents compressed controls without changing splitter ownership or workspace order. A small generated-findings section in the existing Metadata Inspector offers finding details, Ignore/Restore, and View Group. View Group sets a filter in the main browser; no duplicate window or modal browser exists. Asset-derived details use plain text.

One owned QThread performs loading, analysis and suppression publication. Stage signals update the section and existing status footer; there is no per-file signal flood. Cancel is explicit in the section so ESC retains its existing source-scan meaning. Analysis is unavailable during a normal scan, and source changes/rescans cancel active analysis. Completed previous results survive cancellation. Source-mismatched and post-close signals do not update UI.

Shutdown follows the existing bounded-cancellation pattern. A read blocked by the operating system cannot be forcibly interrupted; its thread remains retained until it drains rather than destroying a running QThread or terminating file I/O. No shared user-store connections or renderer workers are repurposed.

## Measured performance

Windows, Python 3.13.14, scripts/benchmark_housekeeping.py. Cheap-pass timings include tracemalloc instrumentation, which adds overhead. Peak memory is incremental traced analysis memory, excluding preconstructed catalog rows. No synthetic mesh files are created for the cheap passes.

| Catalog assets | Cheap pass | Peak traced memory | Findings | Files hashed |
| ---: | ---: | ---: | ---: | ---: |
| 10,000 | 0.3975 s | 8.386 MiB | 1,000 | 0 |
| 50,000 | 2.2486 s | 41.657 MiB | 5,000 | 0 |
| 100,000 | 5.4871 s | 83.346 MiB | 10,000 | 0 |

Candidate strategy: 1,000 catalog assets, 6 size candidates, 6 actually hashed, 768 bytes read, 6 exact findings (three pairs), 0.0296 s. Only those six temporary candidate files were created; 994 unique-size synthetic records were not opened. These are local measurements, not NAS timing guarantees.

## Verification

Phase A full baseline: 817 total, 814 passed, one live UI-harness failure, zero errors, two expected skips, 1057.198 s. The test's QCoreApplication settings sandbox did not isolate the explicitly organization-scoped SettingsService; unrelated startup callbacks also remained queued. The harness now supplies isolated typed settings, stubs unrelated native-health/autotrim callbacks and drains construction events before the worker assertion. No warm production code changed. The settings/warm/worker-lifecycle focused run passed all 45 tests in 11.404 s; its specified warning audit was clean. This follows the mission's test-harness-only exception before starting Phase B. The final full regression also passed that corrected warm-reopen UI test.

Final focused validation: 78 tests passed in 69.553 s (50 Housekeeping tests plus existing DPI/Inspector checks). Existing browser/filter/Tags/Favorites/Collections/source/scan/lifecycle integration: 133 tests passed in 617.591 s. Final complete regression: 867 total, 865 passed, zero failures, zero errors, two expected skips, 2634.946 s. No production code changed after this full run. The two skips require the absent TestSource/TestDestination fixtures and a physical multi-monitor host. Final focused, integration and full logs contain zero occurrences of QThread:, QFont::, Traceback, has been deleted, QObject::, QWidget::, Internal C++, UserWarning, RuntimeWarning, DeprecationWarning or ResourceWarning. The Phase A baseline log contains only the one assertion traceback already described; its corrected focused run is clean. Tests cover atomic rollback, persistence, corrupt rows, SHA-256 groups, differing content, bounded reads, concurrent changes, cancellation, offline/permission failures, path guards, naming false positives, archive namespace checks, companions, suppression invalidation, 10k publication, UI composition, duplicate-group browsing, explicit analysis, and lifecycle/deleted-object safety.

## Changed files and preserved systems

Added:

- meshcorral/services/housekeeping/{__init__,models,repository,service,naming,analyzer}.py
- meshcorral/ui/housekeeping/{__init__,widgets,controller}.py
- meshcorral/tests/test_housekeeping.py
- meshcorral/tests/test_housekeeping_ui.py
- scripts/benchmark_housekeeping.py
- docs/REPOSITORY_HOUSEKEEPING.md

Additive integration changes:

- meshcorral/services/search_service.py
- meshcorral/ui/search/async_filter_engine.py
- meshcorral/ui/main_window.py
- meshcorral/ui/asset_inspector.py
- meshcorral/ui/inspector/metadata_panel.py
- meshcorral/ui/inspector/inspector_tabs.py
- meshcorral/tests/test_warm_repository_reopen.py (Phase A harness only)
- docs/WARM_REPOSITORY_REOPEN.md and docs/CHANGELOG.md

Warm repository production architecture, scanner traversal, metadata enrichment, thumbnail rendering/geometry/cache/routing, Blender backend, Gallery/Table and Inspector ownership, user Tags/Favorites/Collections stores, search parser, layouts, dialogs, transfers, shutdown architecture and rebrand behavior are preserved. APP_VERSION remains 0.1.0-rc1, thumbnail style remains v4, package remains meshcorral and log filename remains roundup.log. Earlier uncommitted heavy-mesh/warm changes were retained.
