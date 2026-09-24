# MeshStager changelog

> Historical entries may reference **Roundup** (pre-rebrand product name).

## Per-user Windows installer for RC3 (2026-09-16)

- `installer/MeshStager.iss` restored and switched to a **per-user** install: no administrator
  rights and no UAC prompt, landing in `%LOCALAPPDATA%\Programs\MeshStager` instead of
  `Program Files`. The RC1 `AppId` GUID is retained so Windows still correlates upgrades.
- Start Menu shortcut plus an optional Desktop shortcut; MeshStager and the RC3 version appear in
  the wizard, Add/Remove Programs, and the uninstaller; "Launch MeshStager" offered on finish.
- `scripts/build_installer_windows.ps1` compiles the installer from the already-verified
  `dist/MeshStager` payload, refuses a bundle missing numpy/PIL/trimesh/scipy, locates `ISCC.exe`,
  and writes `release/MeshStager_v0.1.0-rc3_Setup.exe` with a SHA256 sidecar. It never rebuilds the
  app. `scripts/build_installer.bat` now delegates to it so the two cannot drift.
- Uninstall removes program files only; `%LOCALAPPDATA%\MeshStager` settings, caches, thumbnails,
  and the legacy Roundup migration source are preserved.
- Fixed `.gitignore` ignoring all of `installer/`, which had silently dropped the `.iss` build
  source from the repository.
- Packaging only: no application or runtime code changed, and APP_VERSION is untouched.

## Repository Housekeeping (2026-09-12)

- Explicit, cancellable analysis over the indexed catalog with atomic completed findings.
- Same-size SHA-256 duplicate candidates, conservative review flags, cached ZIP evidence,
  and bounded OBJ/MTL companion checks; assets remain read-only.
- Existing-browser Housekeeping filters and duplicate-group views, with Ignore/Restore
  in the existing Metadata Inspector; user Tags and Collections remain separate.
- Synthetic 10k/50k/100k benchmarks and focused safety/lifecycle coverage.
- Warm-reopen test settings/startup isolation corrected without production redesign.
- Documentation: `docs/REPOSITORY_HOUSEKEEPING.md`. APP_VERSION and thumbnail style unchanged.

## Binary STL thumbnail consistency correction (2026-09-11)

- Removed the 8 MiB compact-renderer eligibility gate: valid binary STL now uses
  the same solid preview path across file sizes, with safe legacy fallback.
- Bumped PNG style v3 to v4 once; preview geometry remains reusable and caches
  are not deleted. Quality tier policy and non-STL renderers are unchanged.
- Added size-range, fallback, determinism, and cache-invalidation coverage.

## Heavy-mesh thumbnail hardening (2026-09-11)

- Bounded binary-STL preprocessing and a persistent compact preview-geometry cache.
- Solid, antialiased heavy-mesh previews reuse the existing native thumbnail pipeline.
- Size/style regeneration reuses geometry; existing PNG hits avoid geometry entirely.
- Atomic, corruption-checked cache publication and safe permission-failure recovery.
- Repeatable benchmark, focused regression coverage, and measurements in
  `docs/THUMBNAIL_HEAVY_MESH_HARDENING.md`. APP_VERSION remains `0.1.0-rc1`.

## Tier 2.3 — Collections (2026-09-11)

- Persistent, manually curated collections in a separate `asset_collections.sqlite` store.
- Create, rename, and confirm deletion; assets remain untouched on disk.
- Sidebar filtering over loaded assets, counts, Metadata membership controls, and bulk
  add/remove through the shared gallery/table context menu.
- Exact case-insensitive `collection:"Name"` search composes with Tags, Favorites, and
  existing filters without rescanning or changing the source or asset mode.
- Missing paths retain membership; responsive dialogs and existing lifecycle wiring.
- Documentation: `docs/TIER2_COLLECTIONS.md`. Displayed version remains `0.1.0-rc1`.

## v1.0.0 — Prime core freeze + Tags MVP (2026-05-27)

### Prime v1.0 core freeze — completed

RC hardening (A1–A5), freeze-gate fixes (F-01/F-02), and DPI validation (100% / 125% / 150%) are complete. The following areas are **frozen** (bugfix-only unless explicitly approved):

| Frozen area | Notes |
|-------------|--------|
| Scan pipeline | Discovery, cooperative cancel, large-folder preflight |
| Thumbnail routing | Native vs Blender policy, queue guards |
| Metadata cache | SQLite metadata cache, geometry worker contract |
| Gallery / inspector architecture | Tab shell, preview framing, panel ownership |
| Footer framework | Status strip, scan/bridge/thumbnail lines |
| ESC cancel | Cooperative scan cancel, non-blocking warning dialog |
| Shutdown behavior | Idempotent teardown, bounded thread waits |

Reports: `docs/RC_VISUAL_REGRESSION_REPORT.md`, `docs/DPI_VALIDATION_REPORT.md`, `docs/PRIME_V1_CORE_FREEZE.md`.

Git tag: `v1.0.0-core-freeze`

---

### Tier 2.1 — Tags MVP

- User-defined tags per asset path (SQLite: `asset_tags.sqlite`)
- Metadata tab: **Tags** block, **+ Add Tag** dialog, chips
- Multi-select: **+ Add Tag to N Assets**
- Search: `tag:name` (e.g. `tag:print-ready`, `tag:armor`)
- Docs: `docs/TIER2_TAGS.md`, `docs/TIER2_TAGS_MVP.md`

Tags do not rename, move, or modify source files.

---

### Tier 2.2 — Favorites

- ☆ / ★ toggle on Metadata tab (single selection)
- **Favorites** filter: All / Favorites Only
- SQLite: `asset_favorites.sqlite`
- Docs: `docs/TIER2_FAVORITES.md`

---

## v0.1.0-rc1 and earlier

See [`RELEASE_NOTES_v0.1.md`](../RELEASE_NOTES_v0.1.md) at the repository root.
