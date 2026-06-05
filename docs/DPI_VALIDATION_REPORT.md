# Prime v1.0 RC — DPI Validation Report

**Product:** MeshStager (formerly Roundup / Mesh Corral)  
**Pass:** A5.5 / RC freeze gate — DPI matrix  
**Date:** 2026-05-27  
**Scales validated:** 100%, 125%, 150% (via `QT_SCALE_FACTOR` 1.0 / 1.25 / 1.5)

---

## Executive summary

| Scale | Programmatic probe | Layout unit tests | Overall |
|-------|-------------------|-------------------|---------|
| **100%** | **9/9 PASS** | **5/5 PASS** | **PASS** (1 manual follow-up) |
| **125%** | **9/9 PASS** | (shared constants) | **PASS** (1 manual follow-up) |
| **150%** | **9/9 PASS** | (shared constants) | **PASS** (1 manual follow-up) |

**Freeze recommendation:** **PASS for DPI gate** (manual matrix signed off 2026-05-27).

**DPI-W01 (Settings min height vs content):** Reclassified as **low-priority enhancement** — Save/Cancel, Environment, Blender, and Thumbnail Generation sections all visible at 100%/125%/150% in operator validation. Not a freeze blocker. Tier 2 backlog: optional `QScrollArea` or slightly higher `SETTINGS_DIALOG_MIN_HEIGHT`.

**Tooling:** `scripts/dpi_validation_probe.py` (automated) · `meshcorral/tests/test_dpi_layout_constants.py` (constants)

---

## Validation method

| Layer | What ran |
|-------|----------|
| **Automated probe** | Instantiates Settings, Large-folder warning, Inspector tabs, Diagnostics, and status-bar labels at each scale; checks min sizes, button fit, tab overflow, word wrap, footer width budget |
| **Unit tests** | Right-panel width, inspector tab math, dialog minimums, control height |
| **Code audit** | `layout_constants.py`, `inspector_tabs.py` (`setUsesScrollButtons(True)`), theme `min-width: 56px` on tabs, footer permanent widgets |
| **Manual GUI** | **PASS** — operator verified 100% / 125% / 150% (buttons, footer, table headers, inspector, transfer spacing, layout menu, sidebar) |

```powershell
cd "o:\Mesh package\Mesh_corral"
$env:QT_SCALE_FACTOR = "1.25"   # or 1.0, 1.5
.\.venv\Scripts\python.exe scripts\dpi_validation_probe.py
```

---

## Surface-by-surface results

### Main window

| Check | 100% | 125% | 150% | Notes |
|-------|------|------|------|-------|
| Right panel min width (320px baseline) | PASS | PASS | PASS | `MIN_RIGHT_PANEL_WIDTH`; Qt scales with DPI |
| Control height (32px baseline) | PASS | PASS | PASS | Toolbar/gallery controls use `CONTROL_HEIGHT` |
| Layout header menu | PASS | PASS | PASS | `QMenu` / `QToolButton` — OS-themed; no fixed pixel clipping in code |
| Clipped text / overlapping controls | — | — | — | **Manual:** narrow window + 150% OS scale |

**Findings:** No code-level blockers. Splitter and `#Panel` margins use shared spacing constants.

---

### Settings dialog

| Check | 100% | 125% | 150% | Notes |
|-------|------|------|------|-------|
| Minimum size ≥ 520×440 | PASS | PASS | PASS | `SETTINGS_DIALOG_MIN_*` |
| Vertically resizable | PASS | PASS | PASS | `sizeHint` height ~1291 > min 440; user can resize |
| Internal scroll area | **WARNING** | **WARNING** | **WARNING** | No `QScrollArea`; at **min height** lower sections require resize |
| Wrapped help labels (DCC / Bridge) | PASS | PASS | PASS | `setWordWrap(True)` on help blocks |
| Browse buttons in form rows | PASS | PASS | PASS | `QHBoxLayout` stretch on line edits |

**Before/after behavior:** N/A (validation only).

**Recommended polish (non-blocking):** Optional future `QScrollArea` wrapper if operators report clipping at min size on 150% displays.

---

### Inspector tabs

| Check | 100% | 125% | 150% | Notes |
|-------|------|------|------|-------|
| Tab bar min height | PASS | PASS | PASS | 28px baseline |
| Tab overflow at 320px panel | PASS | PASS | PASS | Total tab width ~317px @ 100%; `usesScrollButtons=True` |
| Tab elide mode | PASS | PASS | PASS | `ElideNone` + scroll buttons avoids overlap |
| Per-tab vertical scroll | PASS | PASS | PASS | `InspectorTabScroll` `ScrollBarAsNeeded` |

**Probe detail @ 100%:** `tab_total_w=317`, `panel=320`, `scroll_btns=True`.

---

### Diagnostics tab

| Check | 100% | 125% | 150% | Notes |
|-------|------|------|------|-------|
| Form labels + value wrap | PASS | PASS | PASS | Value labels `setWordWrap(True)` |
| Long deferred reason | PASS | PASS | PASS | 120+ char reason wraps (`deferred_h>20`) |
| Mesh / geometry row (F-01) | PASS | PASS | PASS | Shows geometry summary, not thumbnail health |

---

### Metadata tab

| Check | 100% | 125% | 150% | Notes |
|-------|------|------|------|-------|
| Value labels word wrap | PASS | PASS | PASS | `_muted_label` uses `setWordWrap(True)` |
| Deferred banner | PASS | PASS | PASS | Empty-state widget; A5.3 copy |
| Metadata block height cap | PASS | PASS | PASS | `_METADATA_MAX_HEIGHT = 120` with scroll in `QPlainTextEdit` |
| Narrow (320px) form | — | — | — | **Manual:** confirm label column at 150% OS scale |

---

### Layout menu

| Check | 100% | 125% | 150% | Notes |
|-------|------|------|------|-------|
| Header `Layout` tool button | PASS | PASS | PASS | Standard `QToolButton` + `QMenu` |
| Preset / load submenu entries | PASS | PASS | PASS | Native menu rendering |

---

### Large-folder warning dialog

| Check | 100% | 125% | 150% | Notes |
|-------|------|------|------|-------|
| Min width ≥ 480 | PASS | PASS | PASS | Default open width 560 |
| Action buttons fit row | PASS | PASS | PASS | Continue / Scan without / Cancel ~376px in 560px dialog |
| Intro + bullets word wrap | PASS | PASS | PASS | 9 wrapped labels detected |
| ESC hint visible | PASS | PASS | PASS | `MutedLabel` below button row |

---

### Footer / status bar

| Check | 100% | 125% | 150% | Notes |
|-------|------|------|------|-------|
| Scan line (125k files + Esc) | PASS | PASS | PASS | hint width ~261 @ 1280 host |
| Counts strip (Prime + failures) | PASS | PASS | PASS | Stretch factor 1 on center label |
| Permanent widgets (thumbs + bridge + version) | PASS | PASS | PASS | Combined hint ~688px @ 1280 host |
| Truncation on narrow window | — | — | — | **Manual:** shrink main window &lt; 1024px at 150% |

**Stress strings used:** `Scanning… 125,000 files found · Press Esc to cancel`, full Prime Server counts strip, long Blender path in bridge line.

---

## Defect register

| ID | Severity | Scale | Surface | Finding | Status |
|----|----------|-------|---------|---------|--------|
| DPI-W01 | **Enhancement** | All | Settings | Content taller than min height; resize works; all sections visible in manual pass | Tier 2 UX backlog (optional scroll area) |
| DPI-W02 | **INFO** | All | Footer | Very narrow windows may compress center strip before permanent widgets | Manual spot-check |
| DPI-W03 | **INFO** | All | Main window | Full-window toolbar wrap not probed headlessly | Manual spot-check |

**FAIL:** None identified in automated pass.

---

## Manual follow-up (~15 min)

On a Windows machine, set **Display → Scale** to 100%, then 125%, then 150%. Launch MeshStager and confirm:

1. **Settings** — Open at default size; scroll/resize if needed; Save/Cancel not cropped.
2. **Inspector** — All four tabs readable at minimum right-panel width.
3. **Large-folder warning** — Trigger a large scan path; three buttons + ESC hint visible.
4. **Footer** — During scan, Esc hint readable; bridge line not clipped on 1920×1080.
5. **Layout menu** — All preset names visible.

If DPI-W01 is acceptable in practice → **Prime v1.0 Core Freeze** for DPI.

---

## Test results (this run)

```
test_dpi_layout_constants     5 passed
dpi_validation_probe @ 1.0    9/9 passed
dpi_validation_probe @ 1.25   9/9 passed
dpi_validation_probe @ 1.5    9/9 passed
```

---

## Sign-off

| Role | Result |
|------|--------|
| Automated DPI probe (100 / 125 / 150) | **PASS** |
| Layout constants unit tests | **PASS** |
| Physical Windows display scaling | **PASS** (operator 2026-05-27) |
| Core freeze (DPI criterion) | **Approved** |

*Prime v1.0 RC — DPI validation. Complements `docs/RC_VISUAL_REGRESSION_REPORT.md`.*
