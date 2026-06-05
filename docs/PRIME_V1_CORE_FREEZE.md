# Prime v1.0 — Core Freeze

**Status:** **CORE FROZEN** (2026-05-27)  
**Git tag:** `v1.0.0-core-freeze`  
**Changelog:** `docs/CHANGELOG.md`

MeshStager has completed Prime v1.0 RC hardening (A1–A5), freeze-gate fixes (F-01, F-02), and DPI validation (automated + manual 100% / 125% / 150%).

### Freeze note

Core systems are locked for feature work. **Tier 2** features (tags, favorites, collections, saved searches, batch actions) are implemented **beside** the frozen core, not inside scan/routing/metadata/gallery/inspector/footer/shutdown code paths.

**Shipped on top of freeze:** Tier 2.1 **Tags MVP** — see [`TIER2_TAGS.md`](TIER2_TAGS.md) (user guide) and [`TIER2_TAGS_MVP.md`](TIER2_TAGS_MVP.md) (technical).

Supporting reports:

- `docs/RC_VISUAL_REGRESSION_REPORT.md` — A5.5 audit
- `docs/DPI_VALIDATION_REPORT.md` — DPI matrix

---

## Freeze gate (all passed)

| Gate | Status |
|------|--------|
| A1 Thumbnail UX | ✅ |
| A2 Empty States | ✅ |
| A3 Footer / Status | ✅ |
| A4 DPI + Dependency Reliability | ✅ |
| A5 Visual Consistency | ✅ |
| F-01 Diagnostics geometry row | ✅ |
| F-02 Native routing test alignment | ✅ |
| DPI matrix (100% / 125% / 150%) | ✅ |
| ESC scan cancel | ✅ |
| Large-folder warning responsiveness | ✅ |

**DPI-W01 (Settings scroll):** Low-priority enhancement only — not a freeze blocker.

---

## Frozen areas

Do **not** modify unless fixing a confirmed bug (no feature work, no refactors):

| Area | Scope |
|------|--------|
| Scan pipeline | Discovery, cancel token, large-folder preflight, working-set replace |
| Thumbnail routing | Native vs Blender policy, `route_thumbnail`, queue guard |
| Native renderer routing | Health probe, degradation footer |
| Metadata cache | Registry, geometry worker contract |
| Gallery architecture | Model, selection, thumb refresh |
| Inspector architecture | Tab shell, panel ownership, preview framing |
| Footer framework | Counts strip, scan/bridge/thumbnail lines |
| ESC cancel framework | Cooperative scan cancel, non-blocking warning dialog |
| Shutdown behavior | `_shutdown_app`, bounded thread waits, logging |

Polish that stays allowed: copy fixes, DPI spacing within existing layout constants, test alignment — **small diffs only**.

---

## Tier 2 development track

Build **on top of** the frozen core, in this order:

1. **Tags** ✅ (Tier 2.1)
2. **Favorites** ✅ (Tier 2.2)
3. **Collections**
4. **Saved searches**
5. **Batch actions**

Tier 2 UX backlog (non-blocking):

- Settings dialog: optional `QScrollArea` or slightly higher minimum height (DPI-W01)

---

## Release tagging

When ready in git:

```bash
git tag -a v1.0.0-core-freeze -m "Prime v1.0 core freeze: RC hardening A1-A5, F-01/F-02, DPI validated"
```

Use `v1.0.0-rc2` instead if that matches your release train.

---

## Product state

MeshStager is in **product state**, not prototype: consistent visual language, stable deferred thumbnail states, correct diagnostics geometry row, responsive scanning, graceful dependency degradation, and validated DPI behavior at 100–150% scaling.
