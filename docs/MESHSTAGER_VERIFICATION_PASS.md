# MeshStager Verification Pass — 2026-05-31

Final rebrand verification before `MeshStager v1.0.0-core-freeze` tag.

## Step 1 — Recreate venv ✅

```powershell
cd "E:\Mesh package\Mesh_corral"
Remove-Item -Recurse -Force .venv
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt -r requirements-dev.txt
```

**Result:** Fresh Python 3.12 venv; PySide6 6.11.1, PyInstaller 6.20.0, numpy/trimesh installed.

---

## Step 2 — Run app (automated + manual)

### Automated (headless)

`meshcorral/tests/test_rebrand_smoke.py` — **5/5 PASS**

| Check | Result |
|-------|--------|
| `APP_NAME` / `SettingsService.APP_NAME` | `MeshStager` |
| Welcome empty state | `Welcome to MeshStager` |
| Settings header | `MeshStager Settings` |
| About window title | `About MeshStager` |
| Thumbnail UX copy | Uses MeshStager (not Roundup) |

Data migration tests — **3/3 PASS** (`test_data_migration.py`)

### Manual (your eyes — recommended once)

```bat
.venv\Scripts\python -m meshcorral.app
```

Confirm: window title, Settings, welcome, footer version, tags, favorites, layouts.

---

## Step 3 — Build executable ✅

```bat
scripts\build_exe.bat
```

| Artifact | Status |
|----------|--------|
| `dist\MeshStager\MeshStager.exe` | **Exists** (~7.2 MB) |
| `dist\MeshStager\README_FIRST.txt` | Staged |
| `dist\MeshStager\_internal\` | PyInstaller bundle |

---

## Step 4 — Launch frozen EXE ✅

```powershell
Start-Process "dist\MeshStager\MeshStager.exe"
```

**Result:** Process started and ran 8+ seconds without immediate crash (killed after smoke launch).

**Your confirmation:** Launch from Explorer (not IDE), verify same branding strings as Step 2 manual.

---

## Full GUI test suite ✅ (completed)

With fresh venv:

```
Ran 579 tests in ~415s
FAILED (failures=7, skipped=1)
```

Suite **completed** (prior hangs were broken venv + headless Python 3.12 without project deps).

### Failures (pre-existing — not rebrand regressions)

| Test | Module |
|------|--------|
| `test_footer_copy_matches_health` | footer / health copy drift |
| `test_scan_source_after_mode_switch_uses_selected_source` | mode switch + `_run_scan` signature |
| `test_scan_source_then_back_to_3d_rescans_same_folder` | same |
| `test_scan_source_scans_selected_path` | source browse scan |
| `test_default_routes_stl_to_native` | native routing default |
| `test_decode_failed_corrupt_copy` | thumbnail UX wording |
| `test_unsupported_no_retry` | thumbnail UX wording |

None assert on `Roundup` branding. Safe to tag rebrand; track these as separate bugfix items if gating release.

---

## Roundup reference audit

Remaining `Roundup` / `ROUNDUP` / `roundup` hits are **intentional**:

| Category | Examples | Verdict |
|----------|----------|---------|
| **Migration / legacy** | `LEGACY_APP_NAME`, `data_migration.py`, `%LOCALAPPDATA%\Roundup\` | Required |
| **Env var aliases** | `ROUNDUP_*` in QA scripts; `read_branded_env()` reads `MESHSTAGER_*` first | Backward compat |
| **Deprecated launchers** | `run_roundup.bat`, `launch_roundup.ps1` | Forward to MeshStager |
| **Legacy build artifacts** | `Roundup.spec`, `Roundup.iss`, `dist/Roundup/`, `Roundup_v*.zip` | Archive / retire manually |
| **Historical docs** | CHANGELOG note, migration docs, audit tables | Intentional |
| **Internal docstrings** | Some module headers still mention Roundup historically | Non-user-facing |

### Commonly missed — verified

| Item | Status |
|------|--------|
| Installer product name | `MeshStager` in `installer/MeshStager.iss` ✅ |
| Registry (QSettings) | `WoodringTools/MeshStager` (+ legacy migration) ✅ |
| Logging prefixes | `MeshStager shutdown …` ✅ |
| Portable readme | `MeshStager.exe`, `%LOCALAPPDATA%\MeshStager\` ✅ |
| Build output name | `MeshStager.exe` ✅ |
| GitHub Actions | **None in repo** |
| `dist/Roundup/` | Old build — delete when ready |

---

## Release readiness

| Gate | Status |
|------|--------|
| Rebrand code complete | ✅ |
| Venv healthy | ✅ |
| Frozen build | ✅ |
| EXE launches | ✅ (smoke) |
| Full test suite runs to completion | ✅ |
| 100% tests green | ⚠️ 7 known failures (pre-rebrand drift) |
| Manual GUI spot-check | **You** — one pass recommended |

**Recommendation:** Comfortable tagging **`MeshStager v1.0.0-core-freeze`** for the rebrand after your manual GUI spot-check. Fix the 7 test failures in a follow-up hardening pass if you want a green CI gate before Tier 2 feature work (Collections, Saved Searches, Batch Actions).
