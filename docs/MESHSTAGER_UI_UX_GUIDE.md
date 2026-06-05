# MeshStager UI/UX Guide

Internal design reference for MeshStager. Use this guide before any UI copy, layout, or QoL change so the product stays consistent across sessions and releases.

**Code source of truth for strings:** `meshcorral/ui/preview_state_copy.py` and `meshcorral/ui/footer_status.py`.

**Related:** [MESHSTAGER_UX_AUDIT_CHECKLIST.md](MESHSTAGER_UX_AUDIT_CHECKLIST.md) · RC3 tester docs in `handoff/templates/`

---

## Product UX goal

MeshStager is a **production desktop tool** for browsing large, messy 3D and image archives on disk.

Users need:

- **Speed first** when opening huge folders (visible-first work, deferred depth).
- **Confidence** the app is not stuck (plain status, cancellable long operations).
- **Quality second** (HQ preview and full metadata on demand, not by default).

Assume: files are huge, folders are messy, network paths are slow, and thumbnails take time.

**Preview quality rule:** Preview quality must support asset identification. Speed improvements are only valid if the preview remains useful for confirming the correct asset.

---

## Preview quality (asset identification)

Thumbnails exist so users can **confirm the correct mesh** — especially vendor and outside assets. Visual polish is secondary to identification.

| Tier | Path / size | Default mode | Purpose |
|------|-------------|--------------|---------|
| **Small local** | &lt; 8 MB | Balanced Preview (professional shaded) | Full silhouette, readable contrast |
| **Medium local** | 8–48 MB | Balanced Preview (reduced face budget) | Solid shaded surface |
| **Large** | ≥ 48 MB | Fast Proxy first | Speed-safe first pass; HQ on demand only |
| **Network / server** | Staged safely | Balanced for small/medium; proxy only when large | Do not permanently downgrade all network thumbs |
| **Huge / prime browse** | Deferred first pass | Placeholder → load when visible | Proxy/defer acceptable only as initial state |
| **Manual HQ** | User regenerate | HQ Preview | Opt-in only — never auto for large/server files |

**Visual reference:** `Screenshot 2026-05-08 000006` — clean shaded mesh, good silhouette, strong contrast. No speckled point-cloud look unless fallback is truly required. No giant “Unsupported” cards when a better preview can be generated.

**Internal modes:** Fast Proxy · Balanced Preview · HQ Preview. Normal local assets default to **Balanced Preview**, not Fast Proxy. Cache keys include `render_mode` + `thumbnail_style_v2` so poor legacy proxy entries are not reused for balanced previews.

---

## Visual style

| Principle | Direction |
|-----------|-----------|
| **Theme** | Dark technical desktop app (light theme supported but secondary) |
| **Density** | Information-rich but not cramped; prefer one clear action per row |
| **Clutter** | Low — no new panels or controls without product approval |
| **Hierarchy** | Primary actions visually stronger than secondary (see below) |
| **Color** | Tokens in `meshcorral/ui/theme.py` (`APP_COLORS`); do not invent one-off hex values in widgets |

**Primary actions (visual weight):** Scan Source, Copy Selected To…, Move Selected…, Generate Missing 3D Thumbnails.

**Secondary / quiet:** Settings, layout presets, filter combos, inspector regenerate, export.

**Right panel:** Supports the selected asset; must not compete with the gallery grid for attention.

---

## Tone and wording

| Do | Don't |
|----|--------|
| Calm, production-tool language | Alarmist or “error” tone for normal behavior |
| Short sentences | Jargon, stack traces, internal enum names |
| Explain *what is happening* | Blame the user or the file |
| **Deferred Preview** for intentional delay | “Failed”, “Broken”, “Stuck” for large-folder deferral |

**Branding:** User-facing name is **MeshStager**. Python package remains `meshcorral` (do not rename in UI strings).

---

## Preview state language (locked)

Use **exact** Title Case labels in inspector headlines, docs, and user-visible status. Do not mix *deferred*, *delayed*, *pending*, and *queued* in primary inspector titles.

| Label | Meaning |
|-------|---------|
| **Cached Preview** | PNG already rendered and reused from disk cache |
| **Balanced Preview** | Default shaded surface render for small/medium local and network assets |
| **Proxy Preview** | Fast lightweight first pass (large files; upgrade via regenerate / HQ) |
| **HQ Preview** | High-quality render — **manual / on demand only** (no new HQ workflow without approval) |
| **Deferred Preview** | Intentionally delayed so browsing stays responsive |
| **Unsupported Preview** | Format not supported for automatic preview yet |
| **Thumbnail Ready** | Preview available for the asset |

**Card face (short):** `Defer` / badge `DEFER` — not the inspector headline.

**In-flight (operational):** Generating, Queued, Loading preview — OK for queue/decode states; not interchangeable with Deferred Preview.

---

## Status / footer language (locked)

Footer and left status label must answer: *What is happening? Is it safe to scroll or click?*

| Status | When |
|--------|------|
| **Ready** | Idle / scan complete |
| **Scanning folder…** | Folder walk in progress (Esc cancels) |
| **Loading thumbnails…** | Visible thumbnail load pass |
| **Using cached previews** | Reused render cache (footer maps pipeline message) |
| **Proxy preview ready** | Proxy render finished (footer maps pipeline save step) |
| **Preview queue complete** | Thumbnail queue drained (when surfaced) |
| **Large files deferred for fast browsing** | Prime perf deferral toast / calm hint |

Other calm lines: *Scrolling — previews paused briefly*, *Canceling scan…*, *Filtered*, *Searching…*.

**Render pipeline:** Do not change `meshcorral/services/render/*` for copy. Map display strings in `friendly_render_pipeline_status()` only.

---

## Gallery behavior rules

| Rule | Detail |
|------|--------|
| **Virtualized list** | `QListView` + `QAbstractListModel` — not QWidget-per-thumbnail |
| **No scroll rebuild** | `set_records` / full model reset only on filter, scan, mode change — **never** on wheel |
| **Scaled pixmap cache** | Fingerprint: path + size/mtime + gallery pixel size |
| **Inspector debounce** | Default `MESHSTAGER_GALLERY_SCROLL_DEBOUNCE_MS` = **75** |
| **Viewport cap** | Default `MESHSTAGER_GALLERY_MAX_VISIBLE_BUILD` = **100** |
| **Scroll timing log** | Off by default; `MESHSTAGER_UI_SCROLL_TIMING=1` to enable |

**Large folders:** Table view + filters are valid fallbacks; document in tester guides, do not hide Gallery.

---

## Safety rules

| Area | Rule |
|------|------|
| **Move / copy** | Dry-run preview before destructive transfer |
| **Migration** | Confirmation + dry-run first; never silent bulk migration |
| **HQ preview** | Opt-in / manual; no auto-HQ on huge files or whole folders |
| **Proxy / cache** | Cache-first and proxy-default for large/network paths (render policy unchanged) |
| **Scan** | Cooperative cancel (Esc) where already implemented |
| **Destructive actions** | Confirm dialogs remain; do not remove guardrails for “speed” |

---

## Modal / popup dialogs — Yard Responsive Dialog Standard (locked)

> **Suite standard:** [YARD_RESPONSIVE_DIALOG_STANDARD.md](YARD_RESPONSIVE_DIALOG_STANDARD.md)  
> Permanent rule for **MeshStager and all Yard desktop apps**. MeshStager is the reference implementation.

All MeshStager **popup/modal windows must be usable on laptop screens** (including **1366×768**).

**Required:**

- Dialogs are **resizable** (`setSizeGripEnabled`; no fixed height trapping actions).
- Long dialog content lives inside a **`QScrollArea`** (scrollbar only when needed).
- **Save**, **Cancel**, **Close**, **Apply**, or other **primary action buttons stay pinned outside** the scroll area.
- The user must **never need to resize, move, or maximize** a dialog just to save or cancel.
- Dialogs must **center over the parent window** and **clamp to the current screen** work area.

| Implementation | Location |
|----------------|----------|
| Base class | `ResponsiveModalDialog` in `meshcorral/ui/responsive_dialog.py` |
| Scroll body | `create_content_scroll_area()` |
| Pinned actions | `create_pinned_button_row()` |
| Show sizing | `finalize_responsive_dialog_show()` → `center_dialog_over_parent()` |

**Reference implementations:** `SettingsDialog` · `LargeFolderWarningDialog` · `MovePreviewDialog`

**Audit:** [MESHSTAGER_UX_AUDIT_CHECKLIST.md](MESHSTAGER_UX_AUDIT_CHECKLIST.md) §15

**Do not:** Put action buttons inside scrolling content; ship fixed-height modals that push actions off-screen; skip screen clamp on content-heavy dialogs.

---

## Accessibility and contrast

| Check | Expectation |
|-------|-------------|
| **Selected gallery tile** | Visible fill + highlight border — always obvious |
| **Disabled buttons** | Readable gray on dark (`theme.py` disabled tokens) |
| **Muted text** | `PlaceholderText` on **Active** palette, not Disabled |
| **Small filenames** | Elided, not clipped to zero contrast |
| **Status strip** | Readable at 100%–150% Windows scaling |

Re-verify after theme or delegate changes.

---

## Tester documentation rules

Handoff templates (`handoff/templates/`) must stay aligned with this guide:

| Doc | Purpose |
|-----|---------|
| `TESTER_QUICK_START.md` | Five commands first; common mistakes (unzip, fresh venv, direct `python.exe`) |
| `GALLERY_PERFORMANCE.md` | RC3 scroll test + optional `ui_scroll_timing.log` |
| `PERFORMANCE_DIAGNOSTICS.md` | RC2 `render_timing.log` + preview label table |
| `HANDOFF_RC3_STATUS.md` | RC3 scope + links to this guide |

When copy changes in code, update `preview_state_copy.py` **and** these docs in the same PR.

---

## Button labels (locked)

| Control | Label |
|---------|--------|
| Source browse | **Browse…** |
| Scan | **Scan Source** |
| Transfer | **Copy Selected To…** · **Move Selected…** |
| File actions | **Reveal in Explorer** · Copy Selected Path (secondary) |
| Batch thumbs | **Generate Missing 3D Thumbnails** |

Tooltips: **one sentence**, describe what happens on click (include “dry-run first” for move/copy).

---

## Do / Don't examples

### Do

- “Deferred Preview — Large folder — preview loads when you browse.”
- “Using cached previews” in the footer during cache hit.
- “Scanning folder… 12,450 files found · Press Esc to cancel.”
- Primary button on Scan Source; secondary styling on layout/settings.

### Don't

- “ERROR: Thumbnail deferred!!!” for a normal 2 GB folder.
- Rebuild the entire gallery model on every mouse wheel tick.
- Auto-enqueue HQ render for every file in a 10k folder.
- Show raw Python tracebacks in QMessageBox body without a collapsed Details section.
- Introduce new preview words (*pending*, *delayed*, *waiting*) in inspector headlines.

---

## Persistence across sessions (design discipline)

This guide replaces ad-hoc style drift. Before merging UI work:

1. Read this guide and [MESHSTAGER_UX_AUDIT_CHECKLIST.md](MESHSTAGER_UX_AUDIT_CHECKLIST.md).
2. Confirm strings match `preview_state_copy.py` or update both code and docs.
3. Run `test_gallery_scroll_perf` + `comprehensive_stress_test.py --quick --cleanup`.
4. Manual pass: large folder → Gallery scroll after thumbnails loaded.

No external design-system dependency required — consistency is enforced by doc + code constants + checklist.

---

## Release labels (tester-facing)

| Build | Label |
|-------|--------|
| RC2 | **RC2 Beta — Performance Diagnostics** |
| RC3 | **RC3 Beta — Gallery Performance** |

Keep RC2 (render) and RC3 (gallery UI) stories separate in handoff zips and status markdown.
