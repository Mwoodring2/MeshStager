# MeshStager UX Audit Checklist

Use before shipping any UI/QoL change. Check **Pass / Fail / N/A** and note fixes in the PR.

**Guide:** [MESHSTAGER_UI_UX_GUIDE.md](MESHSTAGER_UI_UX_GUIDE.md)

**Quick tests:**

```bat
.\.venv\Scripts\python.exe -m unittest meshcorral.tests.test_gallery_scroll_perf
.\.venv\Scripts\python.exe -m unittest meshcorral.tests.test_dialog_placement
.\.venv\Scripts\python.exe scripts\comprehensive_stress_test.py --quick --cleanup
```

**Manual (RC3+):** Large folder → Gallery → wait for thumbnails → mouse-wheel scroll 10–20 s.

---

## 1. System status visibility (Nielsen: visibility of system status)

| # | Check | Pass |
|---|--------|------|
| 1.1 | Footer/status shows **Ready** when idle | ☐ |
| 1.2 | Scan shows **Scanning folder…** (or equivalent) with file count | ☐ |
| 1.3 | Thumbnail work shows **Loading thumbnails…** or thumbnail line activity | ☐ |
| 1.4 | Cache hit shows **Using cached previews** (not scary wording) | ☐ |
| 1.5 | User can tell if app is busy vs safe to scroll | ☐ |
| 1.6 | Long scan shows cancel hint (Esc) where supported | ☐ |

---

## 2. Real-world language

| # | Check | Pass |
|---|--------|------|
| 2.1 | Preview labels use locked terms (Cached / Proxy / HQ / Deferred / Unsupported / Thumbnail Ready) | ☐ |
| 2.2 | No mixed *deferred* / *pending* / *queued* in inspector **headlines** | ☐ |
| 2.3 | No internal module names in user-visible strings | ☐ |
| 2.4 | Large-file behavior sounds intentional, not broken | ☐ |

---

## 3. User control and freedom

| # | Check | Pass |
|---|--------|------|
| 3.1 | Move/copy still offer dry-run preview first | ☐ |
| 3.2 | Migration remains confirmation / dry-run first | ☐ |
| 3.3 | HQ preview remains manual / opt-in (no new auto-HQ path) | ☐ |
| 3.4 | Scan cancel still works where already implemented | ☐ |
| 3.5 | No new irreversible action without confirm | ☐ |

---

## 4. Consistency

| # | Check | Pass |
|---|--------|------|
| 4.1 | Strings match `meshcorral/ui/preview_state_copy.py` | ☐ |
| 4.2 | Button labels match guide (Browse…, Scan Source, etc.) | ☐ |
| 4.3 | Docs updated if user-visible copy changed | ☐ |
| 4.4 | RC2 vs RC3 handoff labels not conflated | ☐ |

---

## 5. Error prevention

| # | Check | Pass |
|---|--------|------|
| 5.1 | Proxy default for large/network paths unchanged | ☐ |
| 5.2 | Cache-first preview behavior unchanged | ☐ |
| 5.3 | No auto-HQ for huge folders | ☐ |
| 5.4 | Transfer blocked without destination / selection where expected | ☐ |

---

## 6. Recognition over recall

| # | Check | Pass |
|---|--------|------|
| 6.1 | Primary actions visible without digging into menus | ☐ |
| 6.2 | Tooltips are one sentence and accurate | ☐ |
| 6.3 | Source path and visible count readable in header/footer | ☐ |

---

## 7. Efficiency

| # | Check | Pass |
|---|--------|------|
| 7.1 | Gallery does **not** full-rebuild on scroll | ☐ |
| 7.2 | Scaled pixmap cache still used in gallery paint path | ☐ |
| 7.3 | Selection inspector debounce still active (default 75 ms) | ☐ |
| 7.4 | Viewport prefetch cap still active (default 100) | ☐ |
| 7.5 | `render/*` pipeline not modified for UI tickets | ☐ |

---

## 8. Minimalist design

| # | Check | Pass |
|---|--------|------|
| 8.1 | No new panels or workflow buttons added | ☐ |
| 8.2 | Settings/right panel text still concise | ☐ |
| 8.3 | No duplicate status messages (footer vs toast) | ☐ |

---

## 9. Error recovery

| # | Check | Pass |
|---|--------|------|
| 9.1 | Setup errors plain English with next step | ☐ |
| 9.2 | User dialogs avoid raw stack traces in main body | ☐ |
| 9.3 | Thumbnail failures point to Jobs / details, not panic copy | ☐ |

---

## 10. Help / docs

| # | Check | Pass |
|---|--------|------|
| 10.1 | `TESTER_QUICK_START.md` lists unzip + fresh venv + direct python path | ☐ |
| 10.2 | Common mistakes: no run-from-ZIP, Activate.ps1 workaround | ☐ |
| 10.3 | `MESHSTAGER_UI_UX_GUIDE.md` linked from RC3 handoff status | ☐ |
| 10.4 | Log paths documented (`%LOCALAPPDATA%\MeshStager\logs\`) | ☐ |

---

## 11. Visual hierarchy

| # | Check | Pass |
|---|--------|------|
| 11.1 | Scan Source reads as primary action | ☐ |
| 11.2 | Transfer buttons clear but not louder than scan | ☐ |
| 11.3 | Inspector supports selection without overpowering grid | ☐ |
| 11.4 | Asset/preview state visible on card or inspector | ☐ |

---

## 12. Spacing

| # | Check | Pass |
|---|--------|------|
| 12.1 | Gallery cell text not cramped under thumbnail | ☐ |
| 12.2 | Settings dialog usable at 100% scale without awkward clip | ☐ |
| 12.3 | Panel gaps consistent (`layout_constants` / theme) | ☐ |

---

## 13. Contrast

| # | Check | Pass |
|---|--------|------|
| 13.1 | Selected gallery tile obvious (border + fill) | ☐ |
| 13.2 | Disabled buttons readable on dark theme | ☐ |
| 13.3 | Muted labels not gray-on-gray | ☐ |
| 13.4 | Status strip readable at glance | ☐ |

---

## 14. Selected item visibility

| # | Check | Pass |
|---|--------|------|
| 14.1 | Gallery selection visible while scrolling | ☐ |
| 14.2 | Table selection still visible (if touched) | ☐ |
| 14.3 | Filename readable on selected tile | ☐ |

---

## 15. Yard Responsive Dialog Standard

**Suite standard:** [YARD_RESPONSIVE_DIALOG_STANDARD.md](YARD_RESPONSIVE_DIALOG_STANDARD.md) (permanent · all Yard apps)

Guide: [MESHSTAGER_UI_UX_GUIDE.md](MESHSTAGER_UI_UX_GUIDE.md) — MeshStager application

Helpers: `ResponsiveModalDialog` · `create_content_scroll_area()` · `create_pinned_button_row()` · `finalize_responsive_dialog_show()` · `center_dialog_over_parent()`

| # | Check | Pass |
|---|--------|------|
| 15.1 | Dialog is **resizable** (no fixed height trapping actions) | ☐ |
| 15.2 | Long body content in `QScrollArea`; scrollbar only when needed | ☐ |
| 15.3 | Save / Cancel / Close / Apply / primary actions **outside** scroll, pinned at bottom | ☐ |
| 15.4 | User never needs resize/move/maximize just to save or cancel | ☐ |
| 15.5 | Dialog clamped to screen `availableGeometry()` (laptop / 1366×768) | ☐ |
| 15.6 | Dialog centered over parent and fully on-screen after clamp | ☐ |
| 15.7 | Settings, large-folder warning, move preview follow rule (if touched) | ☐ |

**Automated:** `python -m unittest meshcorral.tests.test_dialog_placement`

---

## Sign-off

| Field | Value |
|-------|--------|
| **Auditor** | |
| **Date** | |
| **Branch / RC** | |
| **Gallery scroll manual test** | Pass / Fail / N/A |
| **Automated tests** | Pass / Fail |
| **Notes** | |
