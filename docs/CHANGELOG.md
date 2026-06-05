# MeshStager changelog

> Historical entries may reference **Roundup** (pre-rebrand product name).

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
