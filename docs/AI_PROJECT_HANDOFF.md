# MeshStager — AI Project Handoff

**Purpose of this document:** let a new AI assistant (or a new human) continue MeshStager work
without any prior chat history. Everything needed to resume is below or linked from here.

**Read [`FORGE_RULES.md`](../FORGE_RULES.md) at the repo root first** — it defines the working style
(patch size, behavior preservation, no asserts, Windows/PySide6-first). This document covers project
state; that one covers how to work.

**Last updated:** 2026-09-16

**Handoff state:** RC3 code complete; the SciPy packaging blocker is **fixed and verified in a
rebuilt portable ZIP**; GitHub Release **not yet published** (needs commit, tag move, and upload).

---

## 1. Project identity

| Field | Value |
|-------|-------|
| Product name | **MeshStager** (part of **The Yard** internal tool suite) |
| Python package / import path | `meshcorral` |
| Former product name | **Roundup** (pre-rebrand; still appears in older docs, log lines, and `ROUNDUP_*` env aliases) |
| GitHub repo | https://github.com/Mwoodring2/MeshStager |
| Git remote | `origin` → `https://github.com/Mwoodring2/MeshStager.git`, branch `main` |
| Local Windows path (release/dev machine) | `C:\Users\punke\Documents\Mesh package\MeshStager` |
| Local Windows path (this checkout) | `O:\Mesh package\MeshStager` |
| Release tag in flight | `v0.1.0-rc3` |
| `APP_VERSION` in code | `0.1.0-rc1` (`meshcorral/app/config.py`) |
| License | MIT (`LICENSE`) |
| Primary OS target | Windows 10/11 (Windows-first; Linux/macOS are not supported targets) |
| Python | 3.10+ supported, 3.13 used in the repo `.venv` |

> **Path note:** commands in section 6 use the release machine path. If you are working in a
> different checkout (for example `O:\Mesh package\MeshStager`), substitute your own repo root.
> Everything else in this document is checkout-independent.

> **Version note:** the `v0.1.0-rc3` *tag* and the `APP_VERSION = "0.1.0-rc1"` *constant*
> intentionally differ. Recent changelog entries state explicitly that `APP_VERSION` was left
> unchanged. Do not "fix" this as a drive-by edit; treat any bump as a deliberate release task
> that also touches `docs/CHANGELOG.md` and `docs/MESHSTAGER_RELEASE_CHECKLIST.md`.

### Current purpose

MeshStager is a Windows-first desktop app for **browsing, filtering, and organizing large 3D and
image archives that already live on disk**. It is a local-first asset browser, not a DAM and not a
cloud service. Core capabilities:

- **Scan** local folders (optionally recursive) for 3D/DCC and image formats
- **Filter** by name, extension, category, folder, favorites, tags, collections, thumbnail health
- **Browse** the same filtered list in **Table** or **Gallery** view
- **Sort** by name, date, size, or file type
- **Preview** thumbnails via a native CPU renderer, with an optional Blender Bridge fallback
- **Inspect** metadata, tags, and per-asset diagnostics
- **Move / copy** with overwrite-safe planning; **export** the current view to CSV
- **Housekeeping** — duplicate/naming analysis over the indexed catalog (read-only on assets)

Assets on disk are treated as read-only unless the user explicitly runs a move/copy plan.
All app state (settings, caches, bridge outputs, logs) lives in `%LOCALAPPDATA%\MeshStager\`,
never in the repo.

---

## 2. Current status

| Item | Status |
|------|--------|
| GitHub repo | **Live** and public at https://github.com/Mwoodring2/MeshStager |
| License | **MIT**, committed as `LICENSE` |
| `v0.1.0-rc3` tag | **Exists** |
| Portable ZIP pipeline | **Exists** — `scripts/build_shareable_windows.py` → `release/` (ZIP + SHA256) |
| GitHub Release | **Not published.** Held until the smoke test passes (see section 3) |
| Repo contents | Source, docs, tests, scripts, branding only — no build outputs, caches, or production meshes |

The repository is the source of truth for code and docs. Release artifacts are deliberately
**not** tracked (`release/`, `dist/`, `build/`, `*.zip`, `*.exe` are all gitignored).

Last built portable artifact present locally (`release/`, gitignored):

```
release/MeshStager_v0.1.0-rc3_Windows_Portable/          (staging folder)
release/MeshStager_v0.1.0-rc3_Windows_Portable.zip       (~94 MB)
release/MeshStager_v0.1.0-rc3_Windows_Portable.sha256.txt
```

Its `VERSION.txt` records: `v0.1.0-rc3`, build date `2026-09-16`, `Quick validation: PASS`,
`Bundled deps verified: numpy, PIL, trimesh, scipy`, and the build interpreter path. This build
includes SciPy and reports `Native renderer: Ready`; it replaced the 2026-06-05 build (~70 MB,
commit `71ca6ff`) that exhibited the blocker described below.

`Commit` / `status` read `unknown` in this checkout because git cannot claim the repo here — see
the `safe.directory` note in section 6. Fix that before cutting the artifact you actually upload,
so the ZIP is traceable to a commit.

### Uncommitted work in this checkout

A completed but **uncommitted** feature is present: a persistent negative thumbnail cache that stops
MeshStager from repeatedly sending known non-renderable FBX files to Blender. Check whether it is
still uncommitted before starting new work.

- New policy module: `meshcorral/services/thumbnails/nonrenderable_thumbs.py`
- New tests: `meshcorral/tests/test_nonrenderable_fbx_thumbs.py`
- `meshcorral/services/metadata_cache.py` — `SCHEMA_VERSION` bumped 2 → 3, new
  `thumb_negative_cache` table
- Wiring in `meshcorral/ui/main_window.py` and `meshcorral/ui/thumbnail_controller.py`

Behavior: only high-confidence permanent cases are recorded (zero-mesh FBX imports containing only
armature/camera/light/empty objects, and ASCII FBX the importer cannot read). Transient failures
(crash, timeout, permission/IO, missing output, unknown importer exceptions) stay retryable. Entries
are keyed by path plus size plus mtime, so any file change makes the entry stale, and manual
"Regenerate Thumbnail" always bypasses the cache. Focused tests passed. `APP_VERSION` and the
thumbnail style version were intentionally left unchanged.

---

## 3. SciPy packaging blocker — fixed 2026-09-16

**Original symptom:** the **portable** build showed `Native renderer unavailable: missing SciPy`
in Settings, while running from source worked. A packaging problem, not an app-logic problem.

**Pass condition (unchanged):**

> Portable build → **Settings → Native renderer: Ready**

### Root cause

The release build did not control which interpreter PyInstaller ran in. PyInstaller can only freeze
what the *build interpreter* can import, and `scripts/build_shareable_windows.py` deliberately
switched the build step to `shutil.which("python")`, falling back to it even when it lacked the
project's dependencies. The shipped bundle's `_internal/python314.DLL` proves it was frozen by a
Python 3.14 on `PATH`, not by the repo `.venv` (3.13) where `requirements.txt` — including
`scipy>=1.11` — is installed. That interpreter had PyInstaller but no SciPy, so SciPy could not be
collected.

Two things let it ship silently:

- Nothing *declared* SciPy. The app only reaches it through a guarded function-level
  `import scipy` (`meshcorral/services/render/mesh_render_pipeline.py`) and an
  `importlib.util.find_spec` probe (`native_renderer_health.py`), while trimesh imports it behind
  `try`/`except` wrappers. The build was also spec-less (`--onedir --windowed --name ...`), so
  `MeshStager.spec` and its empty `hiddenimports` were never used.
- Nothing *verified* the finished bundle before zipping it.

### The fix

| Change | File |
|--------|------|
| `HIDDEN_IMPORTS = ['scipy', 'scipy.sparse', 'scipy.sparse.csgraph', 'scipy.spatial']`, wired into `Analysis(hiddenimports=...)` | `MeshStager.spec` |
| Build through the spec (`python -m PyInstaller --noconfirm --clean MeshStager.spec`); spec is now a required input, not an optional one | `scripts/build_shareable_windows.py` |
| Build interpreter must import PyInstaller **and** PySide6, numpy, PIL, trimesh, scipy; the repo `.venv` is tried first and the build aborts if no candidate qualifies | `scripts/build_shareable_windows.py` |
| Post-build gate: abort before packaging if `_internal/` lacks numpy, PIL, trimesh, scipy, or `scipy/sparse` and `scipy/spatial` | `scripts/build_shareable_windows.py` |
| Same spec + venv preference for the dev EXE build, so the two paths cannot drift | `scripts/build_exe.bat` |
| Regression tests for all of the above (no PyInstaller run needed) | `meshcorral/tests/test_release_packaging.py` |

Only the SciPy subpackages the render path needs are named; PyInstaller's bundled `hook-scipy*`
hooks collect the matching extension modules and DLLs. No app, renderer, or health-probe logic
changed, and `APP_VERSION` was not touched.

### Verified evidence (2026-09-16 rebuild)

| Check | Result |
|-------|--------|
| Build interpreter selected | repo `.venv` (Python 3.13.5) |
| `_internal/scipy` + `scipy.libs` in extracted ZIP | **present** (85 `.pyd`, ~66 MB with OpenBLAS) |
| `_internal/{numpy,PIL,trimesh,PySide6}` | present |
| Frozen app startup log | `Startup environment \| Native renderer: Ready \| Blender: Ready` |
| Native STL renders in the frozen app | succeeded, `error_message: null` — proves `import scipy` and `import trimesh` resolve inside `_load_mesh` |
| `unable to use sparse matrix, falling back!` / `Missing dependency` / any `ERROR` | none |
| Launch and graceful shutdown | clean, no missing-DLL or import traceback |
| ZIP size | 67.2 MB → 93.7 MB (SciPy is ~66 MB unpacked; unavoidable, it is a hard runtime requirement) |

The frozen app logs the same readiness lines the Settings → Environment page shows (see
`MainWindow.__init__`), which is how a windowed build is confirmed without clicking through the UI.
The manual Settings check remains in the smoke test below.

---

## 4. Recent completed milestones

Shipped and considered stable — do not redo these:

- **GitHub cleanup** — public repo prepared: source/docs/tests/scripts/branding only, MIT license,
  sample-data policy, gitignore covering caches and build artifacts.
- **Responsive Settings dialog** — Settings is the reference implementation of the Yard responsive
  dialog standard (resizable, scrolled body, pinned actions, centered and screen-clamped).
- **Toolbar / header icon polish** — `assets/icons/MeshStager_icon*.{png,ico}` wired through
  `MeshStager.spec` and the in-app header/taskbar presentation.
- **`thumbnail_style_v2` quality policy** — balanced default for small/medium meshes, proxy path
  for large ones; codified in `docs/RC3_THUMBNAIL_QUALITY_REGRESSION.md` with regression tests.
- **Sort by Type** — extension-based sort alongside name/date/size in both Table and Gallery.
- **Blender worker packaging fix** — `blender_worker/scripts/` (`run_job.py`,
  `thumbnail_render.py`) resolves correctly in frozen builds.

Later work landed on top of RC3 and is reflected in `docs/CHANGELOG.md`: heavy-mesh thumbnail
hardening, binary-STL thumbnail consistency (PNG style v3 → v4), Tier 2 tags/favorites/collections,
warm repository reopen, and repository housekeeping. Read the changelog before assuming what the
current `main` contains.

---

## 5. Core product rules

These are standing constraints, not preferences. Violating one is a regression even if tests pass.

1. **Preview quality must support asset identification.** A thumbnail exists so a user can
   recognize *which* asset this is. An unreadable-but-fast preview has failed.
2. **Speed cannot reduce thumbnail usefulness.** Performance work may defer, tier, cache, or
   proxy — it may not degrade previews below the identification bar.
3. **Dialogs must be responsive with pinned action buttons.** Every modal follows
   `docs/YARD_RESPONSIVE_DIALOG_STANDARD.md`: resizable, long content in a `QScrollArea`, primary
   actions pinned outside the scroll area, centered over parent and clamped to available screen
   geometry. A user must never resize, move, or maximize a dialog just to reach Save or Cancel.
   Subclass `ResponsiveModalDialog` (`meshcorral/ui/responsive_dialog.py`) and extend
   `meshcorral/tests/test_dialog_placement.py` when adding a dialog.
4. **Shareable builds must be reproducible.** The same command on a clean environment produces an
   equivalent portable ZIP. Manual post-build fixups are a bug in the build script.
5. **Release artifacts stay out of git.** No ZIPs, EXEs, installers, `dist/`, `build/`, `release/`,
   caches, databases, or private meshes. See `.gitignore` and `docs/SAMPLE_DATA_POLICY.md`.
6. **No `assert` statements in production code.** Use explicit runtime checks, typed guards, and
   `logging`. Asserts vanish under optimization and are not a safety mechanism.

Additional house style: typing required, ~100-character lines, docstrings on public functions and
classes, tests accompany behavior changes, and changes land as small reviewable increments with the
rationale written down.

---

## 6. Commands

Run from the repo root. Substitute your own repo root if it differs from the release machine.

```bat
cd "C:\Users\punke\Documents\Mesh package\MeshStager"
```

**Full unit test discovery**

```bat
.\.venv\Scripts\python.exe -m unittest discover
```

If bare discovery does not collect the suite in your checkout, use the explicit form documented in
`README.md`:

```bat
.\.venv\Scripts\python.exe -m unittest discover -s meshcorral/tests -p "test_*.py"
```

**Quick stress / smoke test**

```bat
.\.venv\Scripts\python.exe scripts\comprehensive_stress_test.py --quick --cleanup
```

**Build the portable Windows ZIP**

```bat
.\.venv\Scripts\python.exe scripts\build_shareable_windows.py --version v0.1.0-rc3
```

The build script runs a quick validation subset (`test_gallery_scroll_perf`,
`test_thumbnail_quality_regression`, `test_gallery_list_model`) and aborts on failure. Add
`--skip-validate-quick` only when you have already run the tests yourself.

**Run from source (no build)**

```bat
.\.venv\Scripts\python.exe -m meshcorral.app
```

**Useful notes**

- PyInstaller comes from `requirements-dev.txt`, not `requirements.txt`.
- `pytest` is **not** installed in the repo `.venv`; use `unittest`.
- Qt tests create a `QApplication`. Mixing `QCoreApplication` and `QApplication` across modules in
  one process can hard-crash the interpreter at teardown, so new Qt tests should use
  `QApplication.instance() or QApplication([])`.
- If git reports `fatal: detected dubious ownership in repository`, the checkout is owned by a
  different Windows account than the one running the build (common on a shared or moved drive).
  The build still succeeds, but `VERSION.txt` records `Commit: unknown` / `status: unknown`. Clear
  it with `git config --global --add safe.directory '<repo root>'` before cutting a release build,
  so the artifact is traceable to a commit.
- Known pre-existing test failure, unrelated to release readiness:
  `test_warm_repository_reopen.test_success_publishes_and_reconciles_add_change_remove_no_duplicates`
  fails on machines whose `%TEMP%` path has an 8.3 short name, because
  `MetadataCache.complete_source_snapshot` writes `path_key` via `os.path.abspath` while
  `MetadataCache.get` looks up via `Path.resolve()`. The row is present with `file_exists=0` but
  unfindable. Do not "fix" this casually — warm reopen is a protected area.

---

## 7. Release checklist (`v0.1.0-rc3`)

Work top to bottom. Do not reorder items 5 and 6.

- [x] **1. Fix SciPy / native renderer packaging.** Done 2026-09-16 — see section 3. Packaging and
      build-script changes only; **not yet committed**.
- [x] **2. Rebuild the portable ZIP.**
      `.\.venv\Scripts\python.exe scripts\build_shareable_windows.py --version v0.1.0-rc3`
      The build now aborts if SciPy is missing from `_internal/`, so this step cannot silently pass.
- [ ] **3. Smoke test from `C:\MeshStager_Test`.** Extract the ZIP **outside the repo**, run
      `MeshStager\MeshStager.exe`, and confirm:
    - [x] **Settings → Native renderer: Ready** ← release gate (confirmed via the startup log;
          re-confirm visually in Settings during the manual sweep)
    - [x] EXE launches (also scanned a network STL folder and rendered natively with no errors)
    - [ ] header / title / taskbar icon correct
    - [ ] Settings opens centered and resizable with Save/Cancel visible without resizing
    - [ ] Scan a small local STL/OBJ folder
    - [ ] Balanced thumbnails are readable (identification bar)
    - [ ] Sort by Type works
    - [ ] Large / network folders do not lock up the UI
- [ ] **4. Commit the build fix.** Packaging change plus a `docs/CHANGELOG.md` note. Commit only
      source/docs/scripts — never `release/` or `dist/` output.
- [ ] **5. Move the `v0.1.0-rc3` tag** to the commit from step 4. Only do this **before** the
      GitHub Release is published; once a Release is public, the tag is frozen and any further fix
      needs a new tag (`v0.1.0-rc4`).
- [ ] **6. Publish the GitHub Release** and upload both artifacts:
    - `release/MeshStager_v0.1.0-rc3_Windows_Portable.zip`
    - `release/MeshStager_v0.1.0-rc3_Windows_Portable.sha256.txt`
      Release page: https://github.com/Mwoodring2/MeshStager/releases/tag/v0.1.0-rc3
      Suggested title: **MeshStager v0.1.0-rc3 Beta**. In the notes, state RC3 status, portable-ZIP
      form, and the test status recorded in `VERSION.txt`.

---

## Where to look next

| Topic | Document |
|-------|----------|
| Working style / patch conventions | `FORGE_RULES.md` (repo root) |
| Repo overview, install, tests, doc map | `README.md` |
| Package-level technical detail | `meshcorral/README.md` |
| Release history and what recently landed | `docs/CHANGELOG.md` |
| Portable ZIP pipeline and smoke steps | `docs/BUILD_SHAREABLE_WINDOWS.md` |
| Broader release checklist (versioning, branding, migration) | `docs/MESHSTAGER_RELEASE_CHECKLIST.md` |
| Dialog / modal standard | `docs/YARD_RESPONSIVE_DIALOG_STANDARD.md` |
| Thumbnail quality policy | `docs/RC3_THUMBNAIL_QUALITY_REGRESSION.md` |
| Preview speed vs quality strategy | `docs/RENDER_SPEED_QUALITY_STRATEGY.md` |
| Heavy-mesh thumbnail hardening | `docs/THUMBNAIL_HEAVY_MESH_HARDENING.md` |
| UI copy, preview quality, sort behavior | `docs/MESHSTAGER_UI_UX_GUIDE.md` |
| Manual QA sweep | `docs/QUICK_QA_CHECKLIST.md` |
| What must never be committed | `docs/SAMPLE_DATA_POLICY.md` |
| Housekeeping feature design | `docs/REPOSITORY_HOUSEKEEPING.md` |
| Warm reopen design (protected area) | `docs/WARM_REPOSITORY_REOPEN.md` |
| Future renderer backends (research only) | `docs/RC4_THUMBNAIL_BACKEND_EVALUATION.md` |

### Key source landmarks

| Concern | Location |
|---------|----------|
| App entry points | `meshcorral/app/main.py`, `run_frozen.py`, `scripts/run_meshstager.bat` |
| Version and extension/scan sets | `meshcorral/app/config.py` |
| Native renderer health probe (the blocker's source of truth) | `meshcorral/services/environment/native_renderer_health.py` |
| Thumbnail routing (native vs Blender vs none) | `meshcorral/services/thumbnails/thumbnail_router.py`, `thumbnail_routing_policy.py` |
| Native render pipeline | `meshcorral/services/render/` |
| Blender Bridge (queue, jobs, thumb index) | `meshcorral/app/bridge/` |
| Blender headless worker | `blender_worker/scripts/` |
| Persistent caches (SQLite) | `meshcorral/services/metadata_cache.py`, `%LOCALAPPDATA%\MeshStager\cache\` |
| Main window / UI wiring | `meshcorral/ui/main_window.py` |
| Responsive dialog base class | `meshcorral/ui/responsive_dialog.py` |
| Tests | `meshcorral/tests/` |
| Build and packaging | `MeshStager.spec`, `scripts/build_exe.bat`, `scripts/build_shareable_windows.py` |
