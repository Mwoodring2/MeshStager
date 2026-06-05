# GitHub readiness report

**Date:** 2026-06-05 (final pre-push pass)  
**Action:** Repository prepared for first public GitHub push. **No commit or push performed.**

---

## Summary

| Item | Status |
|------|--------|
| MIT `LICENSE` | Added |
| Root `README.md` | GitHub-facing; links license |
| `.gitignore` | MeshStager caches, builds, archives, secrets |
| Archive cleanup | `_archive_cleanup_2026-06-05_github_ready/` (local, gitignored) |
| `O:\` examples in QA docs | Replaced with `C:\MeshStager_Test_Data` / `E:\MeshStager_Test` |
| `unittest discover` | **668 tests — OK (1 skipped)** |
| Quick stress test | **102/102 OK** |

---

## LICENSE

Added [MIT License](../LICENSE) at repository root. `README.md` links to it.

---

## Path / privacy review

| Pattern | Resolution |
|---------|------------|
| `O:\` in active docs | **Resolved** — `docs/QUICK_QA_CHECKLIST.md` and `scripts/validate_prime_v10_local_stability_signoff.py` use generic test paths |
| `O:\` in archived handoff | Remains in `_archive_cleanup_*` only (gitignored) |
| `C:\Users\punke` | Not in tracked source |
| Secrets / `.env` | None committed; gitignored |

---

## Test fixes (8 failures → green)

Outdated tests aligned with RC3 UX copy and async scan launch — **no render/gallery/sort/dialog behavior changes**.

| Test area | Fix |
|-----------|-----|
| Thumbnail UX copy | Expect **No Preview**, **unreadable**, **deferred** (not legacy *not supported* / *malformed* / *delayed*) |
| Footer native fallback | `footer_status.py` aligned with `native_renderer_health` (*slower fallback path*) |
| Scan Source tests | `scan_test_helpers.py` stubs async large-folder preflight + `QTimer.singleShot` |
| Bridge shutdown test | Use `.fbx` (Blender route) so shutdown rejection is exercised |

---

## Test results (final)

```bat
.\.venv\Scripts\python.exe -m unittest discover -s meshcorral/tests -p "test_*.py"
# Ran 668 tests — OK (skipped=1)

.\.venv\Scripts\python.exe scripts\comprehensive_stress_test.py --quick --cleanup
# 102/102 OK
```

---

## Git dry-run (what would be committed)

After `git init`, `git status --short` shows untracked source tree only (no `.venv/`, no `_archive_cleanup_*/`).

`git add --dry-run .` includes:

- `LICENSE`, `README.md`, `.gitignore`, `MeshStager.spec`, requirements, scripts, `docs/`, `meshcorral/`, `assets/icons/`, `assets/branding/`, `blender_worker/`

Does **not** include: `.venv/`, `build/`, `dist/`, `handoff/`, `_archive_cleanup_*/`, `*.db`, logs, caches.

If `git status` fails with dubious ownership on `E:\Mesh package\MeshStager`:

```bat
git config --global --add safe.directory "E:/Mesh package/MeshStager"
```

---

## Kept at repo root

| Path | Role |
|------|------|
| `meshcorral/` | Application source + tests |
| `scripts/` | Run, build, QA utilities |
| `docs/` | Product, RC3/RC4, UX, GitHub guides |
| `assets/icons/`, `assets/branding/` | Tracked branding |
| `blender_worker/` | Blender bridge worker scripts |
| `LICENSE`, `README.md`, `requirements*.txt` | GitHub essentials |

---

## Archived locally (gitignored)

See `_archive_cleanup_2026-06-05_github_ready/ARCHIVE_MANIFEST.md`:

- `handoff/`, `build/`, `dist/`, prior cleanup archive, `project.json`, duplicate root icons

---

## Remaining known limitations (pre-push)

1. **No git commit yet** — run `git add` + `git commit` when ready
2. **Windows-first** — primary target; not tested as a cross-platform product
3. **Blender optional** — `.blend`/`.fbx` thumbs need Blender when configured
4. **Large folders** — deferred/proxy thumbnails for responsiveness (`thumbnail_style_v2`)
5. **User data external** — `%LOCALAPPDATA%\MeshStager\` never ships in repo
6. **Sample meshes** — not bundled; see [SAMPLE_DATA_POLICY.md](SAMPLE_DATA_POLICY.md)
7. **Internal QA paths** — `docs/DPI_VALIDATION_REPORT.md` still has a legacy lowercase path example (cosmetic; optional redact)

---

## Suggested first push commands

```bat
git add .
git commit -m "Initial MeshStager RC3 Beta open-source snapshot"
git remote add origin <your-repo-url>
git push -u origin main
```

Review `git diff --cached` before committing.
