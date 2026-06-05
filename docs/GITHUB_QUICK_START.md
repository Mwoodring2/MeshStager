# MeshStager — GitHub / tester quick start

**Build label:** RC3 Beta — Gallery Performance  
**Platform:** Windows-first desktop (Python + PySide6)

---

## 1. Clone and set up

```bat
git clone <your-repo-url> MeshStager
cd MeshStager
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

---

## 2. Launch

```bat
.venv\Scripts\python -m meshcorral.app
```

First run creates `%LOCALAPPDATA%\MeshStager\` for settings and caches. Nothing in that folder is committed to git.

---

## 3. Smoke test

```bat
.venv\Scripts\python.exe scripts\comprehensive_stress_test.py --quick --cleanup
```

Expect **102+** passing tests in quick mode.

---

## 4. Manual pass (5 minutes)

1. **Scan Source** — pick a small local folder with a few `.stl` / `.obj` / images
2. Switch **Table ↔ Gallery** — same row count
3. Change **Sort → Type A–Z** — files group by extension; thumbnails do not regenerate
4. Open **Settings** — Save/Cancel reachable on a laptop-sized window (scroll + pinned buttons)
5. Select one mesh — inspector shows metadata and preview state

---

## 5. RC3 highlights to verify

| Feature | What to check |
|---------|----------------|
| Gallery scroll | Smooth with 500+ visible rows after load |
| Thumbnail quality | Small files: shaded **Balanced Preview** (not speckled proxy) |
| Large files | **Proxy Preview** or deferred card — no auto-HQ |
| Sort by type | Header **Sort** combo — Type A–Z / Z–A |
| Dialogs | Settings, scan warning, move preview — resizable, scrollable body |

---

## 6. Docs for reviewers

- Preview / identification rule: `MESHSTAGER_UI_UX_GUIDE.md`
- Thumbnail tiers: `RC3_THUMBNAIL_QUALITY_REGRESSION.md`
- Dialog standard: `YARD_RESPONSIVE_DIALOG_STANDARD.md`
- Performance strategy: `RENDER_SPEED_QUALITY_STRATEGY.md`
- Future backends (research only): `RC4_THUMBNAIL_BACKEND_EVALUATION.md`
- QA checklist: `QUICK_QA_CHECKLIST.md`

---

## 7. What is not in the repo

- `.venv/`, `build/`, `dist/`, handoff zips
- User caches (`render_cache`, bridge outputs under AppData)
- Private or vendor production meshes
- Old cleanup archives under `_archive_cleanup_*/` (local only; gitignored)
