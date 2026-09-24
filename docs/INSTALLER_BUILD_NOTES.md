# MeshStager installer build notes (Inno Setup)

> Previously **Roundup**. Legacy scripts: `installer/Roundup.iss`, `dist/Roundup/`.

For the full release sequence (portable build → verify → smoke test → installer → install → launch →
uninstall), see **`docs/BUILD_SHAREABLE_WINDOWS.md`**. This file covers installer specifics only.

## Overview

The Windows installer packages the existing **PyInstaller onedir** output under `dist/MeshStager/`
without changing application behavior. It does **not** build the app; the portable build
(`scripts/build_shareable_windows.py`) does that and verifies the bundle's dependencies.

- **Install location**: `{autopf}\MeshStager`. Since RC3 the installer is **per-user**
  (`PrivilegesRequired=lowest`), so `{autopf}` resolves to `{localappdata}\Programs` — that is
  **`%LOCALAPPDATA%\Programs\MeshStager`** — and Windows shows **no UAC prompt**. Artists can
  install without administrator rights or IT involvement.
- **User data**: **Not** stored with the program. Settings and logs use **`%LOCALAPPDATA%\MeshStager\`**
  via Qt `QSettings`. Legacy **`%LOCALAPPDATA%\Roundup\`** data is migrated on first launch.
- **Uninstall**: Removes installed program files under `{app}`. It deliberately does **not** delete
  per-user `%LOCALAPPDATA%` data — same as most desktop apps, and it keeps settings, caches,
  thumbnails, and the legacy-Roundup migration intact across a reinstall.

### RC1 → RC3 install-scope change

RC1 installed per-machine into `C:\Program Files\MeshStager` and required elevation. The `AppId` GUID
is shared across both, which is correct for release continuity but means a per-user install **cannot
upgrade a per-machine one in place**. Anyone still running the RC1 installer's output should
uninstall it before installing RC3.

## Prerequisites

1. The frozen bundle at `dist/MeshStager/` — build it with
   `.venv\Scripts\python.exe scripts\build_shareable_windows.py --version v0.1.0-rc3`.
2. **[Inno Setup 6.3+](https://jrsoftware.org/isdl.php)** installed (provides **ISCC.exe**).
   - Its own installer offers a **non-administrator** install into
     `%LOCALAPPDATA%\Programs\Inno Setup 6`.
   - `scripts/build_installer_windows.ps1` finds `ISCC.exe` on `PATH`, via the Inno Setup uninstall
     registry key (HKCU or HKLM), or in the default directories including the per-user one. Pass
     `-IsccPath` to override.

## Payload

Everything under **`dist/MeshStager/`** is recursively installed:

```
MeshStager.exe
_internal\
```

`_internal\` is the required PyInstaller runtime, not something testers interact with; no shortcut
points into it. Nothing else is staged into the payload — earlier versions of the build script copied
repo markdown (`README_FIRST.txt`, `QUICK_QA_CHECKLIST.md`, `TESTER_HANDOFF_RC1.md`) beside the EXE,
which exposed internal build/QA instructions to testers. That no longer happens.

## Build

From the repo root:

```powershell
.\scripts\build_installer_windows.ps1
```

`scripts\build_installer.bat` is a thin wrapper around the same script (kept for muscle memory) so
the two paths cannot drift.

Output:

- **`release/MeshStager_v0.1.0-rc3_Setup.exe`**
- **`release/MeshStager_v0.1.0-rc3_Setup.exe.sha256.txt`**

The filename tracks `#define MyAppVersion` in `installer/MeshStager.iss`; the wrapper reads that
define rather than hardcoding a version, and fails if the compiled artifact does not appear.

To cut a new release, edit `#define MyAppVersion` and `VersionInfoVersion` in
**`installer/MeshStager.iss`**. Leave **`AppId`** alone (see below). The app's own `APP_VERSION` is
separate and is not changed by the installer build.

## Source control

`installer/MeshStager.iss` is **build source and must stay tracked**. `.gitignore` previously ignored
all of `installer/`, which is how the original `.iss` disappeared from the repo (it survived only in
`_archive_cleanup_2026-06-05_github_ready/prior_archive_2026-06-03/installer/`). The directory is no
longer ignored; compiled installers land in `release/`, and `*.exe` is ignored globally, so a stray
Setup.exe cannot be committed by accident.

## Signing

The installer is **unsigned**, so Windows SmartScreen shows *Windows protected your PC* with an
unknown publisher; testers must click **More info → Run anyway**. Removing that warning requires an
Authenticode (ideally EV) code-signing certificate applied to both `MeshStager.exe` and the
Setup.exe. Untracked for RC3.

## Acceptance / QA checklist

After building:

1. **Install** — no UAC prompt; app lands in `%LOCALAPPDATA%\Programs\MeshStager`.
2. **Start Menu** — shortcut launches **`MeshStager.exe`**.
3. **Desktop** — optional task “Create a desktop shortcut” creates one when checked.
4. **Icon** — window, taskbar, and shortcut show the MeshStager icon.
5. **Launch** — app starts; **Settings → Native renderer: Ready**.
6. **Workflow smoke** — Settings dialog, Sort by Type, and scanning behave like the portable build;
   **`%LOCALAPPDATA%\MeshStager\`** holds persisted settings.
7. **Uninstall** — Add/Remove Programs entry reads **MeshStager v0.1.0-rc3** and removes
   `%LOCALAPPDATA%\Programs\MeshStager`; confirm user data **remains** under
   **`%LOCALAPPDATA%\MeshStager\`** (expected).

## `AppId` (GUID)

`installer/MeshStager.iss` uses a fixed Inno-style **`AppId`** (inherited from Roundup lineage for
upgrade continuity):

```text
AppId={{B5CF77B4-9884-4964-A6BC-50E6A5327817}
```

Do **not** rotate this casually: Windows uses it to correlate installs/uninstalls. Generate a **new**
GUID only for a genuinely separate product installer.
