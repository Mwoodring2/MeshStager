# MeshStager Release Checklist (post-rebrand)

Use this checklist for Prime v1.0 MeshStager builds after the Roundup → MeshStager rename.

## Pre-build

- [ ] Version bumped in `meshcorral/app/config.py` (`APP_VERSION`)
- [ ] `project.json` version aligned
- [ ] `installer/MeshStager.iss` `#define MyAppVersion` aligned
- [ ] `README_FIRST.txt` version string updated
- [ ] `docs/CHANGELOG.md` entry added

## Build

```bat
.venv\Scripts\pip install -r requirements-dev.txt
scripts\build_exe.bat
```

Expected output:

- [ ] `dist\MeshStager\MeshStager.exe` exists
- [ ] `dist\MeshStager\README_FIRST.txt` staged
- [ ] Window icon visible on EXE in Explorer

Optional installer:

```bat
scripts\build_installer.bat
```

Expected:

- [ ] `dist_installer\MeshStager_Setup_v*.exe`

## Branding smoke test

- [ ] Window title: **MeshStager**
- [ ] Settings header: **MeshStager Settings**
- [ ] Welcome / empty state: **Welcome to MeshStager**
- [ ] Status bar: **MeshStager v{version}**
- [ ] About dialog: **MeshStager v{version}**
- [ ] Shutdown log: `MeshStager shutdown complete`

## Data migration smoke test (upgrade path)

- [ ] Populate `%LOCALAPPDATA%\Roundup\` (tags, favorites, cache) from prior Roundup build
- [ ] Launch MeshStager — data appears under `%LOCALAPPDATA%\MeshStager\`
- [ ] Tags, favorites, layouts, settings persist
- [ ] Legacy `%LOCALAPPDATA%\Roundup\` still present

## Regression guard (must NOT change)

- [ ] Scan pipeline behavior unchanged
- [ ] Thumbnail routing unchanged (`ROUNDUP_NATIVE_THUMBS` / `MESHSTAGER_NATIVE_THUMBS` aliases)
- [ ] Tag / favorite SQLite schemas unchanged
- [ ] No new workflow steps

## Tests

```bat
.venv\Scripts\python -m unittest discover -s meshcorral/tests -p test_*.py
```

- [ ] All tests pass (including `test_data_migration.py`)

## Post-release manual tasks

- [ ] Retire or archive `dist/Roundup/` old builds
- [ ] Update internal download links to MeshStager artifact names
- [ ] Optional: commission `MeshStager.ico` wordmark (see `MESHSTAGER_BRANDING_STATUS.md`)
