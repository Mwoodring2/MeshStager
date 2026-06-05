# MeshStager installer build notes (Inno Setup)

> Previously **Roundup**. Legacy scripts: `installer/Roundup.iss`, `dist/Roundup/`.

## Overview

The Windows installer packages the existing **PyInstaller onedir** output under `dist/MeshStager/` without changing application behavior.

- **Install location**: `{autopf}\MeshStager` (typically `C:\Program Files\MeshStager` on 64-bit Windows).
- **User data**: **Not** stored under Program Files. Settings and logs use **`%LOCALAPPDATA%\MeshStager\`** via Qt `QSettings`. Legacy **`%LOCALAPPDATA%\Roundup\`** data is migrated on first launch.
- **Uninstall**: Removes installed program files under `{app}`; it does **not** need to (and typically should not) delete per-user `%LOCALAPPDATA%` profile data — same as most desktop apps.

## Prerequisites

1. Python + project venv (for the frozen EXE): see `scripts/build_exe.bat`.
2. **[Inno Setup 6](https://jrsoftware.org/isdl.php)** installed (includes **ISCC.exe** Compiler).
   - `scripts/build_installer.bat` looks for `ISCC.exe` in standard install paths under `Program Files` / `Program Files (x86)`.

## Recommended layout before compiling

Everything under **`dist/MeshStager/`** is recursively installed:

```
MeshStager.exe
_internal\
README_FIRST.txt
RELEASE_NOTES_v0.1.md
QUICK_QA_CHECKLIST.md
TESTER_HANDOFF_RC1.md
```

Optional markdown files are **copied into `dist/MeshStager`** by `scripts/build_installer.bat` when they exist in the repo root. `build_exe.bat` only refreshes **`README_FIRST.txt`**; run the installer script after staging docs as needed.

## Build

From the **`Mesh_corral/`** repo root:

```bat
scripts\build_exe.bat
scripts\build_installer.bat
```

Output:

- **`dist_installer/MeshStager_Setup_v0.1.0-rc1.exe`** (suffix tracks `installer/MeshStager.iss` `#define MyAppVersion`).

To change branding or version for a new release:

- Edit `#define MyAppVersion`, **`AppId`** only if splitting a truly different product lineage (normally keep **one stable `AppId`** per product so upgrades unregister correctly), and `OutputBaseFilename` pattern in **`installer/MeshStager.iss`**.

## Acceptance / QA checklist

After building:

1. **Install** — confirm default folder `Program Files\MeshStager`.
2. **Start Menu** — shortcut launches **`MeshStager.exe`**.
3. **Desktop** — optional task “Create a desktop shortcut” creates one when checked.
4. **Launch** — app starts; **`%LOCALAPPDATA%\MeshStager\`** used for persisted settings (theme, paths, etc.).
5. **Workflow smoke** — **Scan Source**, **Move/Copy**, **Asset Mode**, **Gallery Size** behave like the portable build.
6. **Uninstall** — Add/Remove Programs removes **`Program Files\MeshStager`**; confirm user data may remain under **`%LOCALAPPDATA%\MeshStager\`** (expected).

## `AppId` (GUID)

`installer/MeshStager.iss` uses a fixed Inno-style **`AppId`** (inherited from Roundup lineage for upgrade continuity):

```text
AppId={{B5CF77B4-9884-4964-A6BC-50E6A5327817}
```

Do **not** rotate this casually: Windows uses it to correlate installs/uninstalls. Generate a **new** GUID only for a genuinely separate product installer.
