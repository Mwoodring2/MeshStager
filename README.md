# MeshStager

**RC3 Beta — Gallery Performance**

MeshStager is a **Windows-first** desktop app for browsing, filtering, and organizing large 3D and image archives on disk. It is part of **The Yard** internal tool suite (Python package: `meshcorral`; formerly **Roundup**).

This repository contains **source, docs, tests, scripts, and branding only**. It does not include user caches, handoff zips, build outputs, or private production meshes.

---

## What it does

- **Scan** local folders (optional subfolders) for supported 3D/DCC and image formats
- **Filter** by name, extension, category, folder, favorites, tags, and thumbnail health
- **Browse** the same filtered list in **Table** or **Gallery** view
- **Sort** by name, date, size, or file type (extension)
- **Preview** thumbnails via native CPU renderer and optional Blender Bridge
- **Inspect** metadata, tags, and diagnostics per asset
- **Move / copy** with overwrite-safe planning
- **Export** the current view to CSV

---

## Current status (RC3)

| Area | Status |
|------|--------|
| Gallery virtualization & scroll perf | Shipped |
| Thumbnail quality (`thumbnail_style_v2`) | Balanced default for small/medium; proxy for large |
| Responsive dialogs | Yard suite standard |
| Browse sort by type | Shipped |
| RC4 external renderer research | Docs only — see `docs/RC4_THUMBNAIL_BACKEND_EVALUATION.md` |

---

## Requirements

- **Windows 10/11** (primary target)
- **Python 3.10+** (3.13 tested)
- Optional: **Blender** for `.blend` / `.fbx` thumbnails and bridge jobs

---

## Install and run from source

From the repository root:

```bat
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python -m meshcorral.app
```

Or:

```bat
scripts\run_meshstager.bat
```

Headless / no-console launch:

```bat
.venv\Scripts\pythonw.exe -m meshcorral.app
```

User data (settings, caches, bridge outputs) is stored under `%LOCALAPPDATA%\MeshStager\` — not in this repo.

---

## Tests

Quick smoke (recommended before handoff):

```bat
.venv\Scripts\python.exe scripts\comprehensive_stress_test.py --quick --cleanup
```

Full unit discovery:

```bat
.venv\Scripts\python.exe -m unittest discover -s meshcorral/tests -p "test_*.py"
```

Gallery scroll regression:

```bat
.venv\Scripts\python.exe -m unittest meshcorral.tests.test_gallery_scroll_perf
```

---

## Build Windows EXE (optional)

```bat
pip install -r requirements-dev.txt
scripts\build_exe.bat
```

Output: `dist\MeshStager\MeshStager.exe` (gitignored — build locally).

Icon: `assets/icons/MeshStager_icon.ico` via `MeshStager.spec`.

---

## Documentation map

| Doc | Purpose |
|-----|---------|
| [docs/GITHUB_QUICK_START.md](docs/GITHUB_QUICK_START.md) | Tester / contributor quick start |
| [docs/SAMPLE_DATA_POLICY.md](docs/SAMPLE_DATA_POLICY.md) | What not to commit |
| [docs/MESHSTAGER_UI_UX_GUIDE.md](docs/MESHSTAGER_UI_UX_GUIDE.md) | UI copy, preview quality, sort behavior |
| [docs/RC3_THUMBNAIL_QUALITY_REGRESSION.md](docs/RC3_THUMBNAIL_QUALITY_REGRESSION.md) | Thumbnail quality policy |
| [docs/RC4_THUMBNAIL_BACKEND_EVALUATION.md](docs/RC4_THUMBNAIL_BACKEND_EVALUATION.md) | Optional future backends (F3D, etc.) |
| [docs/YARD_RESPONSIVE_DIALOG_STANDARD.md](docs/YARD_RESPONSIVE_DIALOG_STANDARD.md) | Modal / dialog UX rule |
| [docs/RENDER_SPEED_QUALITY_STRATEGY.md](docs/RENDER_SPEED_QUALITY_STRATEGY.md) | Performance diagnostics note |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Release history |
| [meshcorral/README.md](meshcorral/README.md) | Package-level technical README |

---

## Known limitations

- **Windows-first** — Linux/macOS are not supported targets today
- **Large folders** — prime browse defers some thumbnail work for responsiveness
- **Network paths** — slower; staging cache helps but is not a full DAM
- **Blender** — optional; native CPU path covers common mesh formats
- **No cloud sync** — local disk and `%LOCALAPPDATA%` only
- **Sample meshes** — not bundled; use your own test folders (see sample data policy)

---

## Branding assets (tracked)

- `assets/icons/MeshStager_icon.png`
- `assets/icons/MeshStager_icon.ico`
- `assets/icons/MeshStager_icon_toolbar.png`
- `assets/branding/MeshStager_icon_pro.jpg` (marketing / README artwork)

---

## License

Released under the [MIT License](LICENSE).
