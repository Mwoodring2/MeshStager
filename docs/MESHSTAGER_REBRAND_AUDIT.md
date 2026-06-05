# MeshStager Rebrand Audit

**Generated:** 2026-05-30  
**Scope:** Roundup → MeshStager official product rename (branding only)

| Category | File | Current Value | Recommended Change |
|----------|------|---------------|-------------------|
| **APP_NAME** | `meshcorral/app/config.py` | `Roundup` | `MeshStager` ✅ |
| **Settings APP_NAME** | `meshcorral/services/settings_service.py` | `Roundup` | Import from config → `MeshStager` ✅ |
| **Window title** | `meshcorral/ui/main_window.py` | `APP_NAME` (`Roundup`) | `MeshStager` via config ✅ |
| **Status bar version** | `meshcorral/ui/main_window.py` | `{APP_NAME} v{APP_VERSION}` | `MeshStager v0.1.0-rc1` ✅ |
| **Welcome screen** | `meshcorral/ui/main_window.py`, `empty_states.py` | `Welcome to Roundup` | `Welcome to MeshStager` ✅ |
| **Settings dialog title** | `meshcorral/ui/settings_dialog.py` | `Roundup Settings` | `MeshStager Settings` ✅ |
| **Settings copy** | `meshcorral/ui/settings_dialog.py` | Roundup in DCC/Blender help | MeshStager ✅ |
| **About dialog** | `meshcorral/ui/dialogs.py` | `About {APP_NAME}` | Uses `MeshStager` via config ✅ |
| **Shutdown logs** | `meshcorral/ui/main_window.py` | `Roundup shutdown initiated/complete` | `MeshStager shutdown …` ✅ |
| **Thumbnail UX copy** | `thumbnail_ux_copy.py` | Roundup delayed/failed messages | MeshStager ✅ |
| **Large folder dialog** | `large_folder_warning_dialog.py` | Roundup can browse… | MeshStager ✅ |
| **Metadata clipboard** | `thumb_index.py` | `Roundup — asset metadata` | `MeshStager — asset metadata` ✅ |
| **Export default name** | `main_window.py` | `roundup_export.csv` | `meshstager_export.csv` ✅ |
| **Transfer report** | `main_window.py` | `Roundup transfer report` | `MeshStager transfer report` ✅ |
| **User data dir** | `config.py` | `%LOCALAPPDATA%\Roundup` | `%LOCALAPPDATA%\MeshStager` + legacy migration ✅ |
| **QSettings scope** | `settings_service.py` | `WoodringTools/Roundup` | `WoodringTools/MeshStager` + migration ✅ |
| **README** | `meshcorral/README.md` | Roundup | MeshStager ✅ |
| **Portable readme** | `README_FIRST.txt` | Roundup.exe, Roundup folder | MeshStager ✅ |
| **CHANGELOG** | `docs/CHANGELOG.md` | `# Roundup changelog` | MeshStager + historical note ✅ |
| **project.json** | `project.json` | Roundup display/build paths | MeshStager ✅ |
| **PyInstaller spec** | `Roundup.spec` | `name='Roundup'` | New `MeshStager.spec` ✅ |
| **Build script** | `scripts/build_exe.bat` | `dist\Roundup\Roundup.exe` | `dist\MeshStager\MeshStager.exe` ✅ |
| **Installer** | `installer/Roundup.iss` | Roundup Setup | New `installer/MeshStager.iss` ✅ |
| **Launch scripts** | `run_roundup.bat`, `launch_roundup.ps1` | Roundup | New `run_meshstager.bat`, `launch_meshstager.ps1` ✅ |
| **DPI probe** | `scripts/dpi_validation_probe.py` | `Roundup v1.0.0-rc` | `MeshStager v1.0.0-rc` ✅ |
| **QA checklist** | `QUICK_QA_CHECKLIST.md` | Roundup throughout | Update user-facing refs (partial — see manual tasks) |
| **Tier 2 docs** | `TIER2_TAGS*.md`, `TIER2_FAVORITES.md` | `%LOCALAPPDATA%\Roundup` | `%LOCALAPPDATA%\MeshStager` + migration note |
| **Core freeze** | `PRIME_V1_CORE_FREEZE.md` | Roundup product state | MeshStager current; Roundup historical |
| **DPI / RC reports** | `DPI_VALIDATION_REPORT.md`, `RC_VISUAL_REGRESSION_REPORT.md` | Roundup (Mesh Corral) | MeshStager primary name |
| **Internal docstrings** | `meshcorral/**/__init__.py`, services | Roundup in module docs | MeshStager (non-breaking) |
| **Env vars (dev/QA)** | Multiple modules | `ROUNDUP_*` | Keep `ROUNDUP_*`; add `MESHSTAGER_*` alias via `read_branded_env()` ✅ |
| **Env vars (unchanged logic)** | `thumbnail_routing_policy.py`, etc. | `ROUNDUP_NATIVE_THUMBS` | No workflow change; dual-prefix read ✅ |
| **Icons** | `meshcorral.ico`, `Mesh_Corral.png` | Mesh Corral artwork | Wire as-is — no Roundup logo files ✅ |
| **dist/** (built artifacts) | `dist/Roundup/` | Old build output | Rebuild → `dist/MeshStager/` (manual) |
| **Test assertions** | `test_shutdown_coordination.py` | Roundup shutdown strings | MeshStager ✅ |
| **Test QSettings doc** | `test_mode_switch_source_preservation.py` | WoodringTools/Roundup | MeshStager ✅ |
| **Blender bridge plan** | `meshcorral/docs/BLENDER_BRIDGE_BUILD_PLAN.md` | Roundup control center | MeshStager (architecture unchanged) |
| **Database schema** | `asset_tags.sqlite`, etc. | Unchanged filenames | **No change** ✅ |
| **Python package name** | `meshcorral` | Unchanged | **No change** ✅ |
| **Class / module names** | Throughout | Unchanged | **No change** ✅ |

## Intentionally unchanged (non-branding)

| Item | Reason |
|------|--------|
| `meshcorral` import path | Breaking change for packaging/tests |
| SQLite schema / table names | User data compatibility |
| Scan, routing, thumbnail, tag, favorites logic | Explicit freeze — branding only |
| `ROUNDUP_*` env vars in QA scripts | Backward compatible; production code reads `MESHSTAGER_*` first |
| Historical release zip names | `Roundup_v0.1.0-rc1_portable.zip` remains archive artifact |
| `Roundup.spec` / `Roundup.iss` | Legacy filenames retained; superseded by MeshStager.* |
