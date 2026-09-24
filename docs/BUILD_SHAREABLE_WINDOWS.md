# MeshStager — Build a Shareable Windows ZIP (Portable)

**Status:** RC3 Beta — Windows-first packaging guide

RC3 ships two artifacts from the **same** verified PyInstaller build:

| Artifact | For | Tester does |
|----------|-----|-------------|
| **Portable ZIP** | Technical testers, throwaway checks | Unzip, run the EXE, delete the folder |
| **Installer** | Non-technical artists | Double-click Setup, install, launch |

The portable build comes first either way: it is what verifies the bundle's dependencies, and the
installer only wraps `dist/MeshStager/` — it never builds the app.

---

## Simple release flow

```powershell
# 1. build the portable distribution (also produces dist\MeshStager, the installer payload)
.\.venv\Scripts\python.exe scripts\build_shareable_windows.py --version v0.1.0-rc3

# 2. verify the portable build — the script aborts on a bundle missing numpy/PIL/trimesh/scipy,
#    and writes VERSION.txt with the commit, dirty state, and "Bundled deps verified" line
Get-Content release\MeshStager_v0.1.0-rc3_Windows_Portable\VERSION.txt

# 3. run the disposable AppData smoke test (see "Manual smoke test" below)
.\scripts\smoke_test_portable.ps1 "release\MeshStager_v0.1.0-rc3_Windows_Portable\MeshStager\MeshStager.exe"

# 4. build the installer
.\scripts\build_installer_windows.ps1
```

5. **Install into a clean/test location** — run `release\MeshStager_v0.1.0-rc3_Setup.exe`. It
   installs per-user into `%LOCALAPPDATA%\Programs\MeshStager` with no admin prompt. To keep a real
   tester's machine shape, do not redirect the install directory; the dir page is hidden anyway.
6. **Launch installed MeshStager** from the Start Menu shortcut and confirm
   **Settings → Native renderer: Ready**, Settings opens normally, and Sort by Type works.
7. **Uninstall** from Settings → Apps (entry reads *MeshStager v0.1.0-rc3*) and confirm
   `%LOCALAPPDATA%\Programs\MeshStager` is gone while `%LOCALAPPDATA%\MeshStager\` (settings, logs,
   caches, thumbnails) **remains** — user data is intentionally preserved.

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

### Preferred: launch through the disposable AppData sandbox

Use `scripts/smoke_test_portable.ps1` rather than double-clicking the EXE:

```powershell
.\scripts\smoke_test_portable.ps1 "C:\MeshStager_Test\MeshStager_v0.1.0-rc3_Windows_Portable\MeshStager\MeshStager.exe"
```

Add `-Clean` to delete the sandbox when the app exits; by default it is kept so the logs and
caches can be inspected.

The launcher creates `%TEMP%\MeshStager_SmokeTest_<timestamp>\` and overrides `LOCALAPPDATA` and
`APPDATA` **for the launched process only**, so a release check starts from an empty profile. This
matters because launching the EXE directly runs against your real user data: first launch migrates
legacy `%LOCALAPPDATA%\Roundup` data forward, and bridge retention then deletes job bundles older
than 30 days from that copied state. Neither is a bug, but a release verification run should not do
it. The script prints the sandbox path before launch, reports the `Startup environment` line and any
`ERROR` lines from the sandboxed run, and verifies afterwards that your real
`%LOCALAPPDATA%\MeshStager`, `%LOCALAPPDATA%\Roundup`, and `%APPDATA%` were untouched and that the
calling shell's environment was not modified.

Two limits to know:

- **Preferences are not sandboxed.** `SettingsService` uses `QSettings("WoodringTools", "MeshStager")`
  in NativeFormat, which is `HKCU\Software\WoodringTools\MeshStager` in the registry rather than a
  file under AppData, so the last scan folder and view mode still carry over. Use a separate Windows
  profile if you need those isolated too.
- **Blender discovery** scans `LOCALAPPDATA` among its install roots, so a Blender installed there
  will not be found during a sandboxed run. Installs under `ProgramFiles` are unaffected.

`USERPROFILE` is deliberately left alone: `data_migration` only falls back to `Path.home()` when
`LOCALAPPDATA` is unset, which the script always sets.

### Checks to confirm

1. MeshStager.exe launches.
2. Header/title/taskbar icon appears.
3. Settings opens centered, resizable, Save/Cancel visible.
4. **Settings → Native renderer: Ready** — the release gate. The launcher echoes the equivalent
   `Startup environment` log line, but confirm it visually too.
5. Scan a small local STL/OBJ folder.
6. Balanced thumbnails are readable.
7. Sort by Type works.
8. Large/network behavior does not lock up.

---

## Build the installer (for artist testers)

The installer is the artifact to hand to non-technical testers: double-click, install, launch. It
packages the already-verified `dist/MeshStager/` payload — same EXE and `_internal/` runtime as the
portable ZIP.

### Prerequisites

**[Inno Setup 6.3+](https://jrsoftware.org/isdl.php)**, which provides `ISCC.exe`. Its installer
offers a **non-administrator** install into `%LOCALAPPDATA%\Programs\Inno Setup 6`; the build script
finds it there, on `PATH`, via the registry, or under `Program Files`.

### Command

```powershell
.\scripts\build_installer_windows.ps1
```

Pass `-IsccPath "<path to ISCC.exe>"` if Inno Setup lives somewhere unusual, or `-Quiet` to reduce
compiler output.

The script **never rebuilds MeshStager**. It verifies `dist/MeshStager/` has `MeshStager.exe`,
`_internal/`, and the `numpy`, `PIL`, `trimesh`, `scipy` packages — the same requirement the portable
build enforces — then compiles `installer/MeshStager.iss` and reports the artifact with its SHA256.
It exits non-zero with instructions if the payload is incomplete (2), ISCC is missing (3), the
compile fails (4), or the expected Setup.exe was not produced (5).

`scripts\build_installer.bat` is a thin wrapper that calls the same script, so the two cannot drift.

### Expected output

| Artifact | Path |
|----------|------|
| Installer | `release/MeshStager_v0.1.0-rc3_Setup.exe` |
| SHA256 | `release/MeshStager_v0.1.0-rc3_Setup.exe.sha256.txt` |

### What the installer does

- **Per-user, no administrator rights** (`PrivilegesRequired=lowest`), so there is no UAC prompt.
- Installs to **`%LOCALAPPDATA%\Programs\MeshStager`**.
- Creates a **Start Menu** shortcut, plus an **optional Desktop** shortcut (checkbox, on by default).
- Shows **MeshStager v0.1.0-rc3** in the wizard, Add/Remove Programs, and the uninstaller, using the
  app icon from `assets/icons/MeshStager_icon.ico`.
- Offers **Launch MeshStager** on the final page.
- Displays the MIT `LICENSE`; the directory and Start-Menu-group pages are hidden so testers only
  click through Next → Install → Finish.
- **Uninstall removes the program only.** Nothing under `%LOCALAPPDATA%\MeshStager` or the legacy
  `%LOCALAPPDATA%\Roundup` is touched, so settings, caches, thumbnails, and the legacy-data
  migration all survive a reinstall.

`installer/MeshStager.iss` keeps the original `AppId` GUID from the RC1 installer so Windows
correlates upgrades and uninstalls across releases. Do not rotate it.

### Two things to warn testers about

- **SmartScreen / "unknown publisher."** The installer is unsigned, so Windows shows a blue
  *Windows protected your PC* screen. Testers must click **More info → Run anyway**. Fixing this
  properly requires an Authenticode code-signing certificate.
- **An older RC1 install under `Program Files`** was per-machine. Because the `AppId` is shared,
  uninstall that one first; a per-user install cannot upgrade a per-machine one in place.

### Verify the installed build

Same checks as the portable smoke test, against the installed copy:

1. No admin prompt during install.
2. Start Menu shortcut launches the app; Desktop shortcut works if it was selected.
3. Taskbar/window icon is correct.
4. **Settings → Native renderer: Ready**.
5. Settings dialog opens centered and resizable with Save/Cancel visible.
6. Sort by Type works.
7. Uninstall removes `%LOCALAPPDATA%\Programs\MeshStager` and leaves `%LOCALAPPDATA%\MeshStager`.

The disposable-AppData launcher works on the installed EXE too, if you want the app-data isolation
described above while testing the installed copy:

```powershell
.\scripts\smoke_test_portable.ps1 "$env:LOCALAPPDATA\Programs\MeshStager\MeshStager.exe"
```

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
   - `release/MeshStager_v0.1.0-rc3_Setup.exe`
   - `release/MeshStager_v0.1.0-rc3_Setup.exe.sha256.txt`
3. Release title suggestion: **MeshStager v0.1.0-rc3 Beta**
4. Note RC3 status, both artifacts, and test status from `VERSION.txt`. Point non-technical testers
   at the installer and mention the SmartScreen **More info → Run anyway** step.
