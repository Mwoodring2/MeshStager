# MeshStager Branding Status — Icons & Assets

**Audit date:** 2026-05-30

## Logo / icon inventory

| Asset | Path | Roundup-branded? | Status |
|-------|------|------------------|--------|
| Windows app icon | `assets/icons/MeshStager_icon.ico` | Official MeshStager artwork | **READY** |
| PNG logo | `assets/icons/MeshStager_icon.png` | Official MeshStager artwork | **READY** |
| PNG icon source | `Mesh_corral_icon.png` | No | **READY** |
| PyInstaller `--icon` | `assets/icons/MeshStager_icon.ico` | Wired in `MeshStager.spec` / `build_exe.bat` | **READY** |
| Qt window/taskbar icon | `assets/icons/MeshStager_icon.ico` via `application_icon()` | Main window + dialogs | **READY** |
| Windows AppUserModelID | `MeshStager.MeshStager.RC3` | `set_windows_app_user_model_id()` before `QApplication` | **READY** |
| Marketing / README artwork | `assets/branding/MeshStager_icon_pro.jpg` | Docs/handoff only (not taskbar) | **READY** |
| Inno Setup uninstall icon | `{app}\MeshStager.exe` embedded icon | From PyInstaller bundle | **READY** |
| Dedicated `MeshStager.ico` | — | Not present | **NEEDS ART** (optional — current Mesh Corral icon used) |
| Splash screen asset | — | None in codebase | **PLACEHOLDER** (no splash implemented) |
| Marketing lockup "MeshStager" wordmark | — | Not in repo | **NEEDS ART** |

## References cleaned

| Reference | Before | After |
|-----------|--------|-------|
| Executable name | `Roundup.exe` | `MeshStager.exe` |
| Build output folder | `dist/Roundup/` | `dist/MeshStager/` |
| Installer product name | Roundup | MeshStager |
| Window / About title | Roundup | MeshStager |

## No new artwork created

Per rebrand instructions: existing Mesh Corral icons are wired cleanly. A future **MeshStager**-specific wordmark/icon can replace `meshcorral.ico` without code changes (same filename or update spec paths).

## Asset folders

| Role | Path |
|------|------|
| App / taskbar / EXE | `assets/icons/MeshStager_icon.png`, `.ico` |
| Marketing / tester docs | `assets/branding/MeshStager_icon_pro.jpg` (optional) |
| Legacy | `meshcorral.ico` at repo root |
