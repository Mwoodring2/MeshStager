# MeshStager — Build a Shareable Windows ZIP (Portable)

**Status:** RC3 Beta — Windows-first packaging guide

For RC3, use a **portable ZIP** first — not an installer. Testers can unzip, run the EXE, and delete the folder when done.

---

## Prerequisites

1. Repo `.venv` with app dependencies installed (`pip install -r requirements.txt`).
2. **PyInstaller** installed **in that same venv** (`pip install -r requirements-dev.txt`).
   PyInstaller can only freeze what the interpreter running it can import, so the build must run in
   the environment that has PySide6, numpy, Pillow, trimesh, and SciPy. The script tries the repo
   venv first and aborts if no available interpreter has the full set — a `python` on PATH with
   PyInstaller but no SciPy is what shipped the RC3 bundle whose native renderer was unavailable.
3. Git optional — commit hash is recorded in `VERSION.txt` when available.

---

## Build command

From the repo root:

```bat
.\.venv\Scripts\python.exe scripts\build_shareable_windows.py --version v0.1.0-rc3
```

Or:

```bat
scripts\build_shareable_windows.bat
```

The script runs quick unit validation, then builds from **`MeshStager.spec`** (onedir →
`dist/MeshStager/`). The spec is the single source of truth for the entry point (`run_frozen.py`),
icon, windowed mode, and the SciPy hidden imports the native renderer needs; `scripts/build_exe.bat`
builds from the same spec.

Before packaging, the script verifies that `dist/MeshStager/_internal/` actually contains `numpy`,
`PIL`, `trimesh`, and `scipy` (plus `scipy/sparse` and `scipy/spatial`) and aborts if any are
missing, so an incomplete bundle cannot become a release ZIP. `meshcorral/tests/test_release_packaging.py`
guards the same rules without running PyInstaller.

---

## Expected output

| Artifact | Path |
|----------|------|
| Staging folder | `release/MeshStager_v0.1.0-rc3_Windows_Portable/` |
| ZIP | `release/MeshStager_v0.1.0-rc3_Windows_Portable.zip` |
| SHA256 | `release/MeshStager_v0.1.0-rc3_Windows_Portable.sha256.txt` |

The `release/` folder is gitignored — build outputs are never committed.

---

## ZIP layout (inside the archive)

```
MeshStager_v0.1.0-rc3_Windows_Portable/
  MeshStager/
    MeshStager.exe
    _internal/
    … (PyInstaller runtime files)
  README.md
  LICENSE
  START_HERE.txt
  VERSION.txt
  docs/
    GITHUB_QUICK_START.md
    SAMPLE_DATA_POLICY.md
    QUICK_QA_CHECKLIST.md
```

---

## Manual smoke test (before uploading)

Extract the ZIP **outside the repo**, for example:

```
C:\MeshStager_Test
```

Then run `MeshStager\MeshStager.exe` and confirm:

1. MeshStager.exe launches.
2. Header/title/taskbar icon appears.
3. Settings opens centered, resizable, Save/Cancel visible.
4. Scan a small local STL/OBJ folder.
5. Balanced thumbnails are readable.
6. Sort by Type works.
7. Large/network behavior does not lock up.

---

## What not to include

Do **not** bundle:

- `.venv/`, `build/`, `dist/` (except what the script copies into the portable folder)
- `handoff/`, `_archive_cleanup_*/`, old zips
- User caches (`render_cache/`, `thumbnail_cache/`, `.db` / `.sqlite`)
- Private meshes or production assets

---

## GitHub Release upload

1. Open: https://github.com/Mwoodring2/MeshStager/releases/tag/v0.1.0-rc3
2. Attach:
   - `release/MeshStager_v0.1.0-rc3_Windows_Portable.zip`
   - `release/MeshStager_v0.1.0-rc3_Windows_Portable.sha256.txt`
3. Release title suggestion: **MeshStager v0.1.0-rc3 Beta**
4. Note RC3 status, portable ZIP, and test status from `VERSION.txt`.
