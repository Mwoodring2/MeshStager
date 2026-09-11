# Yard Responsive Dialog Standard

**Status:** Permanent UI standard · **Applies to:** All Yard desktop apps (MeshStager, future tools)

MeshStager is the **reference implementation**. New modals and dialog fixes in any Yard app must follow this standard.

---

## Responsive Dialog Rule

All popup/modal windows must be **usable on laptop screens** (including **1366×768**).

### Required

| # | Requirement |
|---|-------------|
| 1 | Dialogs are **resizable** (`setSizeGripEnabled`; no fixed height that traps actions). |
| 2 | Long dialog content lives inside a **`QScrollArea`** (vertical scrollbar only when needed). |
| 3 | **Save**, **Cancel**, **Close**, **Apply**, or other **primary action buttons stay pinned outside** the scroll area. |
| 4 | The user must **never need to resize, move, or maximize** a dialog just to save or cancel. |
| 5 | Dialogs must **center over the parent window** and **clamp to the current screen** work area. |
| 6 | The clamp target is the **`QScreen.availableGeometry()` of the parent/dialog**, and it must account for the **window frame** (title bar + borders). |

### Do not

- Put action buttons inside scrolling content.
- Ship fixed-height modals that push primary actions off-screen.
- Skip screen clamp on content-heavy dialogs.
- Require window manager tricks (move/maximize) to reach Save/Cancel.

---

## Multi-monitor and window frames

Two details are easy to get wrong and both produce a dialog that hangs off the screen:

**Pick the right screen.** A dialog has no native window handle until it is mapped, so
`QWidget.screen()` reports the **primary** screen. Sizing against the primary work area
while the dialog is about to appear over a parent on a second monitor produces a dialog
that overhangs that monitor. Resolve the **parent window's** screen first
(`screen_for_dialog()` in `dialog_placement.py`), then fall back to the dialog's own
screen, the screen under the dialog, and finally the primary screen. Secondary monitors
also use offset and **negative** coordinates — never clamp against `(0, 0)`.

**Account for the frame.** `resize()` and `setMaximumSize()` act on the *client* area,
while the work area has to contain the *frame*. Deduct the title bar and borders
(`dialog_frame_extra()`, which prefers `QWindow.frameMargins()` because `frameGeometry()`
only picks up the title bar after mapping) before clamping.

---

## Reference code (MeshStager)

| Piece | Location |
|-------|----------|
| Base class | `meshcorral/ui/responsive_dialog.py` → `ResponsiveModalDialog` |
| Scroll body | `create_content_scroll_area()` |
| Pinned actions | `create_pinned_button_row()` |
| Screen clamp + center | `finalize_responsive_dialog_show()` · `center_dialog_over_parent()` in `dialog_placement.py` |
| Example (full pattern) | `SettingsDialog` |
| Example (scroll + pinned Continue) | `LargeFolderWarningDialog` |
| Example (table + pinned actions) | `MovePreviewDialog` |

When starting a new Yard app, copy or extract `responsive_dialog.py` and `dialog_placement.py` (or equivalent) into that app's UI layer.

---

## New dialog checklist

Before merging any modal/popup work:

1. Subclass `ResponsiveModalDialog` (or call equivalent helpers).
2. Put long copy/controls in `QScrollArea`; keep primary buttons outside.
3. On `showEvent`, clamp to the **parent/dialog screen's** `availableGeometry()` (frame included) and center over parent.
4. Manual spot-check at **1366×768** (100% scale): Save/Cancel/primary action visible without resizing.
5. Manual spot-check with the parent window on a **secondary monitor** and pushed against each screen edge.
6. Run `python -m unittest meshcorral.tests.test_dialog_placement` (or app-equivalent tests).

---

## App-specific docs

| App | Guide |
|-----|--------|
| MeshStager | [MESHSTAGER_UI_UX_GUIDE.md](MESHSTAGER_UI_UX_GUIDE.md) · [MESHSTAGER_UX_AUDIT_CHECKLIST.md](MESHSTAGER_UX_AUDIT_CHECKLIST.md) §15 |

When adding this standard to another Yard repo, link back to this file and note where that app's reference dialog lives.
