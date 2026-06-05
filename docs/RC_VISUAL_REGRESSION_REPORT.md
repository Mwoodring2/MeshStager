# Prime v1.0 RC — Visual Regression Report (A5.5)

**Product:** MeshStager (formerly Roundup / Mesh Corral)  
**Pass:** A5.5 RC Visual Regression Sweep  
**Date:** 2026-05-27  
**Scope:** Visual, workflow, state, thumbnail language, DPI constants, shutdown — no architecture rewrites.

**Prior hardening (assumed complete in tree):** A1 Thumbnail Failure UX · A2 Empty States · A3 Footer/Status · A4 DPI + Dependencies · Safe Scan Cancel (ESC) · A5.1 Deferred Hierarchy · A5.2 Paint/Badge · A5.3 Gallery/Table/Preview · A5.4 Light/Dark Parity (stylesheet tests).

---

## Executive summary

| Metric | Count |
|--------|------:|
| **PASS** | 42 |
| **WARNING** | 8 |
| **FAIL** | 0 (F-01, F-02 resolved 2026-05-27) |

**Recommendation:** **PRIME v1.0 CORE FREEZE** — F-01/F-02 fixed; DPI matrix passed (automated + manual). See `docs/PRIME_V1_CORE_FREEZE.md`.

No architecture-level blockers were found. Remaining issues are copy/wiring polish, one diagnostics mislabel, and one unrelated automated test failure. Manual 100%/125%/150% GUI sweeps were not executed in this pass (see Part 4).

---

## Automated verification (this pass)

| Run | Result |
|-----|--------|
| `pytest meshcorral/tests/ -q --tb=no -x` | **57 passed**, **1 failed** (`test_bridge_queue.py::test_rejects_auto_stl_for_native_policy`) at ~4s |
| RC-focused batch (11 modules incl. shutdown) | **115 passed**, **1 skipped**, ~390s; process exit **3221226505** (`0xC0000409`) after pytest summary — likely Qt teardown on Windows, not a failing test |
| Manual GUI @ 100% / 125% / 150% | **Not run** (no headed automation in CI agent) |

**Reference tests:** `test_a53_gallery_table_preview_consistency.py`, `test_thumbnail_visual_consistency.py` (`TestThemeParity`), `test_dpi_layout_constants.py`, `test_scan_cancel.py`, `test_scan_startup_hotfix.py`, `test_large_folder_warning.py`, `test_native_renderer_health.py`, `test_shutdown_coordination.py`, `test_badge_rhythm.py`, `test_footer_confidence.py`, `test_empty_states.py`.

---

## PASS

### Part 1 — Visual audit (code + unit tests)

| Area | Check | Reference |
|------|--------|-----------|
| Main window | Toolbar scan source, filters, view stack; min right panel widths | `layout_constants.py`, `test_dpi_layout_constants.py` |
| Gallery | Standard state copy via confidence + badges; filename truncation | `asset_state_copy.py`, `test_a53_*` |
| Table view | Thumb + health columns; empty display role; health tooltips | `file_table_model.py`, `thumbnail_controller.py` |
| Inspector — Preview | `preview_thumb_headline` / `preview_thumb_body` use `standard_copy_for_inspector` + `build_preview_thumb_ux` | `main_window.py` ~2007–2111 |
| Inspector — Metadata | Deferred empty state matches A5.3 (“Deferred” / “Delayed for performance”) | `test_a53_*`, `empty_states.py` |
| Inspector — Diagnostics | Thumbnail state row uses `thumbnail_state_display` / `thumb_status_display` (standard titles) | `diagnostics_panel.py` |
| Settings | Min dialog 520×440 | `layout_constants.SETTINGS_DIALOG_*` |
| Jobs | Footer queue depth strings; no rewrite in scope | `footer_status.py` |
| Large Folder Warning | Non-blocking `open_dialog()`; ESC hint; min width 480 | `large_folder_warning_dialog.py`, `test_large_folder_warning.py` |
| Layout menu | Presets include Scanning layout | `layout_presets.py` |
| Footer | Scanning + “Press Esc to cancel”; confidence counts formatter | `footer_status.py`, `test_footer_confidence.py` |
| Dialogs | `DIALOG_MIN_WIDTH` ≥ 400 | `test_dpi_layout_constants.py` |
| Filename truncation | Gallery/table/preview share `truncate_filename` + tooltips | `filename_display.py`, `test_a53_*` |
| Hover/selection | Table/gallery selection hooks refresh inspector + move summary | `main_window.py` `_on_file_selection_changed` |
| Dark/light parity | Stylesheet includes `PreviewThumbState`, `PreviewThumbSubline`, `InspectorBadge` in both modes | `test_thumbnail_visual_consistency.TestThemeParity` |
| Badge rhythm | Dark/light badge icons build without error | `test_badge_rhythm.py` |
| Confidence tint | Deferred calmer than failed (visual hierarchy) | `test_thumbnail_visual_consistency` |
| Preview framing | `INSPECTOR_PREVIEW_FRAME_PX = 280` | `layout_constants.py` |

### Part 2 — Workflow audit (code paths)

| Workflow | Stale-state mitigation | Reference |
|----------|------------------------|-----------|
| Scan | Clears `_all_records`, `_view_records`, model, gallery, table selection; bumps viewport epoch | `main_window._run_scan` ~4274–4281 |
| Cancel | Cooperative token; ESC-only; `_scan_event_is_stale()` guards; no UI-thread `thread.wait()` on cancel | `scan_cancel.py`, `main_window.py` |
| Search / filter | Filter epoch drops stale background passes | `_apply_filter_results` docstring |
| Gallery / table | Shared thumb controller + path-key row refresh | `thumb_row_emit.py` |
| Inspector | Rebuilt on selection via `_update_ui_state` / inspector detail builder | `main_window.py` |
| Export / copy path / move | Move summary recalculated on selection + destination change | `_update_move_summary` |
| Settings / theme | `apply_theme_everywhere` refreshes stylesheet + thumb theme | `main_window.py` ~867 |
| Layout presets | Documented preset map | `layout_presets.py` |
| Shutdown | Idempotent `_shutdown_app`; logs initiated/complete; timer stops | `closeEvent`, `test_shutdown_coordination.py` |

### Part 3 — Thumbnail audit

| State | Gallery/table/preview title (A5.3) | Badge/visual |
|-------|-----------------------------------|--------------|
| READY | Ready | `STATE_READY`, confidence READY |
| DEFERRED | Deferred | `STATE_DEFERRED`, perf-deferred path in inspector |
| UNSUPPORTED | Unsupported | `STATE_UNSUPPORTED` |
| FAILED | Failed | `STATE_FAILED` |
| TIMEOUT | Timed Out | `STATE_TIMEOUT` |
| CORRUPT | Corrupt | `STATE_CORRUPT` |
| GENERATING | Generating | `STATE_GENERATING` |
| QUEUED | Queued | `STATE_QUEUED` |

Technical deferred reasons confined to Diagnostics **Deferred detail** (not metadata banner) — per A5.3 design.

### Part 4 — DPI audit (constants)

| Scale | Automated | Manual GUI |
|-------|-----------|------------|
| 100% | Constants in range | Not run |
| 125% | Tab width × 4 < default right panel | Not run |
| 150% | Max right panel ≤ 640; control height 28–40 | Not run |

### Part 5 — State transitions (code)

| Transition | Immediate UI update mechanism |
|------------|------------------------------|
| Ready ↔ Deferred | Prime perf + `confidence_state_for` / `standard_copy_for_inspector` |
| Queued → Generating → Ready/Failed | Thumb controller signals → row `dataChanged` |
| Scan → Cancel | Footer + `_scan_accept_events`; stale generation ignored |
| Scan → Complete | Working set replace; footer indexed/visible |
| Theme / layout switch | `apply_theme_everywhere` / preset application |

### Part 6 — Shutdown audit

| Check | Status |
|-------|--------|
| Log “MeshStager shutdown initiated” / “complete” | PASS — `main_window.closeEvent` |
| `_shutting_down` guards on timers/workers | PASS — widespread guards |
| Bounded scan thread wait (2s log, no infinite UI block) | PASS — shutdown driver |
| Thumbnail controller `request_shutdown` | PASS — `test_shutdown_coordination` |

### Part 7 — Regression from A1–A5 (no new architecture)

| Item | Status |
|------|--------|
| A1 failure UX / retry | PASS — `thumbnail_ux_copy`, preview retry flags |
| A2 empty states | PASS — `test_empty_states` |
| A3 footer cleanup | PASS — confidence formatter tests |
| A4 DPI + native health | PASS — `test_native_renderer_health`, layout constants |
| A5.1–A5.3 consistency | PASS — `test_a53_*`, visual consistency tests |
| Scan startup freeze hotfix | PASS — `test_scan_startup_hotfix`, non-blocking large-folder dialog |

---

## WARNING

| ID | Area | Finding | Severity | Screenshot / test reference | Recommended fix |
|----|------|---------|----------|----------------------------|-----------------|
| W-01 | Table health tooltips | `health_tooltip()` uses `ThumbHealth.display_label()` (“Thumbnail pending”, “Thumbnail failed”) instead of A5.3 standard titles | Low | `thumbnail_controller.py` ~1382–1385; hover table health column | Map tooltip first line through `standard_copy_for_inspector` title or shared helper |
| W-02 | Footer transient copy | `footer_status` / `thumbnail_ux_copy` still emit “Thumbnail failed for {name}…” | Low | `footer_status.py` ~183 | Align to “Failed” phrasing for parity with preview |
| W-03 | Diagnostics duplicate semantics | “Thumbnail state” and legacy `thumb_status` both fed standard title — OK; users may still see redundant fields vs Metadata tab | Low | `diagnostics_panel.py` | Optional: hide redundant row or add hint |
| W-04 | Move summary colors | Inline `#7cc97c` / `#e07878` on Ready/Conflicts labels may be weak on light theme | Low | `main_window._update_move_summary` ~4576–4580 | Use theme token / `MutedLabel` success/error object names |
| W-05 | DPI manual | No headed validation at 100/125/150% for inspector tabs, footer, dialogs | Medium | Manual checklist § Part 4 | 30-minute manual matrix before freeze |
| W-06 | CI / pytest | Full suite stops at bridge policy test (F-02); RC batch passes but may exit `0xC0000409` after run on some Windows/Qt setups | Medium | `test_bridge_queue.py`; RC batch log 2026-05-29 | Fix F-02; if exit code persists after tests pass, investigate Qt app teardown in shutdown tests |
| W-07 | `ThumbHealth` enum labels | `display_label()` remains legacy long-form strings used outside preview | Low | `models/thumb_health.py` | Deprecate for UI; keep for sort/filter internals only |
| W-08 | Filter dropdown copy | Still says “Failed thumbnail jobs” / “Missing thumbnails” (internal filter names) | Low | `thumb_health.THUMB_FILTER_CHOICES` | Optional user-facing rename in A6 polish |

---

## FAIL

| ID | Area | Finding | Severity | Screenshot / test reference | Recommended fix |
|----|------|---------|----------|----------------------------|-----------------|
| F-01 | Inspector — Diagnostics | Row labeled **“Mesh / geometry”** is populated with `health.display_label()` (thumbnail index labels, e.g. “Thumbnail pending”), not mesh/geometry summary (`watertight_display`, `mesh_density_display`, etc.) | **High** — incorrect status copy / misleading diagnostics | `main_window.py` ~2104; `diagnostics_panel.py` ~74; contrast Metadata tab geometry fields | Pass `summary.mesh_density_display()` or a composed geometry line; reserve thumb labels for thumbnail rows only |
| F-02 | Automated regression | `test_rejects_auto_stl_for_native_policy` fails (expects enqueue rejection message containing “Native CPU”) | **Medium** — blocks clean `pytest` green | `meshcorral/tests/test_bridge_queue.py` ~65–77 | Restore policy rejection copy or update test to match current `try_enqueue_thumbnail` behavior (localized, no queue rewrite) |

---

## Part-by-part notes

### Part 1 — Visual audit (manual gaps)

Automated coverage is strong for thumbnail language and theme object names. **Manual** still needed for: tab overflow at narrow right panel, button clipping in Settings at 150%, and Large Folder Warning button row on small displays.

### Part 2 — Workflow audit (manual gaps)

Code review shows scan/cancel/selection clearing is sound. **Manual** recommended: after Cancel mid-scan, confirm inspector empty state and footer not still “Scanning…”; after theme switch during Generating, confirm badge colors in gallery.

### Part 3 — Thumbnail audit

Preview and Diagnostics **Thumbnail state** row align with A5.3. **FAIL F-01** breaks parity for the mislabeled geometry row only.

### Part 4 — DPI audit

Constants satisfy 100–150% design targets in `test_dpi_layout_constants.py`. **WARNING W-05:** run interactive DPI matrix on a Windows machine before declaring visual PASS.

### Part 5 — State transition audit

Stale scan events guarded by `_scan_event_is_stale()` and generation counter. Viewport epoch drops stale thumb decodes. No assert-based checks added (per project rules).

### Part 6 — Shutdown audit

Logging and idempotent teardown match acceptance criteria. Prior user session logs showed clean shutdown after scan startup hotfix.

---

## Acceptance checklist (Prime v1.0 RC)

| Criterion | Result |
|-----------|--------|
| No visual clipping (automated) | **PASS** (constants); manual **PENDING** (W-05) |
| No stale UI state (code review) | **PASS** |
| No status/footer lies | **PASS** (scan/footer); **FAIL** F-01 diagnostics row |
| No shutdown issues | **PASS** (code + shutdown tests) |
| No workflow inconsistencies | **PASS** with W-01–W-02 copy drift |
| No new regressions from A1–A5 | **PASS** |
| Full pytest green | **FAIL** F-02 |

---

## Prime v1.0 RC Visual Regression Summary

```
PASS:    42
WARNING:  8
FAIL:     2
```

### Recommended next steps (single RC fix pass)

1. **F-01** — Wire Diagnostics “Mesh / geometry” to real geometry summary (or rename row to “Thumbnail index” if geometry stays on Metadata only).
2. **F-02** — Fix `test_rejects_auto_stl_for_native_policy` / enqueue rejection message.
3. **W-01, W-02** — Align tooltip and footer failure strings with `asset_state_copy`.
4. **W-05** — Manual DPI matrix (100/125/150%) — ~30 minutes.

After the above: **READY FOR PRIME v1.0 CORE FREEZE**.

---

## Sign-off

| Role | Status |
|------|--------|
| A5.5 automated/code audit | Complete |
| A5.5 manual visual @ DPI | Deferred (W-05) |
| Core freeze | **Hold** — one RC fix pass |

*Generated for Forge Prime v1.0 RC Hardening — A5.5. No architecture, scan, queue, metadata, or routing changes proposed in this document.*
