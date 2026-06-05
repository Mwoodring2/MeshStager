# MeshStager

MeshStager is a Windows-first desktop app for **scan-first file organization**:
- scan a folder or drive for supported files
- narrow results with fast in-memory filters
- switch between **Table** and **Gallery** views
- preview a **safe move/copy plan** (no silent overwrites)
- export the current view to CSV

MeshStager is part of **The Yard** internal tool suite. (Previously released as **Roundup**.)

## Supported file types

MeshStager supports two scan modes (choose in the UI):

- **3D Assets mode**: scans common 3D/asset formats like `.stl`, `.obj`, `.fbx`, `.blend`, `.glb`, `.gltf`, `.ply`, `.3mf`, `.dae`, `.abc`
- **Images / Textures mode**: scans raster image formats like `.png`, `.jpg`, `.jpeg`, `.tif`, `.tiff`, `.tga`, `.bmp`, `.webp`, `.psd`

The authoritative lists live in `meshcorral/app/config.py`.

## Blender Bridge (optional)

Blender is **not required** to use MeshStager.

When Blender is installed (or a `blender.exe` path is set in Settings), MeshStager can queue **headless thumbnail jobs** for `.stl` / `.obj`:
- jobs run one at a time in the background
- each job writes an `output_dir` containing `thumbnail.png`, `result.json`, and `log.txt`
- failures keep logs and outputs available for debugging (one-click open from the UI)

## How thumbnails work

MeshStager does **not** modify original mesh files.

- thumbnail jobs write per-job outputs under the user data directory:
  - `%LOCALAPPDATA%\MeshStager\bridge\outputs\blender_bridge\<job_id>\`
- the app indexes `result.json` files on disk and maps **source file path → thumbnail.png**
- Table and Gallery render thumbnails from that index; missing/failed thumbs show a status badge

## Upgrading from Roundup

On first launch, MeshStager automatically migrates data from `%LOCALAPPDATA%\Roundup\` and QSettings scope `WoodringTools/Roundup`. Legacy data is preserved. See `docs/MESHSTAGER_DATA_MIGRATION.md`.

## Run from source (Windows)

From the repository root (`Mesh_corral/`):

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m meshcorral.app
```

Or use `scripts\run_meshstager.bat`.

If you run from inside the inner `meshcorral/` folder, set `PYTHONPATH` to the parent so the package resolves:

```powershell
$env:PYTHONPATH = (Resolve-Path ..).Path
python -m meshcorral.app
```

## Tests

From the repository root (`Mesh_corral/`):

```bash
python -m unittest discover -s meshcorral/tests -p test_*.py
```

## Build Windows EXE (PyInstaller)

Install dev deps, then run the build script from the repository root:

```bat
pip install -r requirements-dev.txt
scripts\build_exe.bat
```

Notes:
- Entry point: `run_frozen.py` (equivalent to `python -m meshcorral.app`)
- Output: `dist\MeshStager\MeshStager.exe` (and `README_FIRST.txt` is copied beside it)
- App icon (window/taskbar/EXE): `assets/icons/MeshStager_icon.png` and `.ico`
- Marketing artwork (README/handoff): `assets/branding/MeshStager_icon_pro.jpg` (optional)
- Windows taskbar grouping: `set_windows_app_user_model_id()` → `MeshStager.MeshStager.RC3`

If `dist\` becomes unexpectedly large, remove `build\` and `dist\` before rebuilding.
