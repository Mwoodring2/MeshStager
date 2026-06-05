## Prime v1.0 — Release gate (remote / VPN)

| Gate | Role |
|------|------|
| **Local stability** | **Primary** — pass on `C:\MeshStager_Test_Data`, `E:\MeshStager_Test`, or local SSD/NVMe copies |
| **Holocron / server** | **Secondary** — stress test when network is good; not the release blocker from home |

No new features, server tuning, thumbnail rewrites, or move/copy/export changes during this pass.

---

## Prime v1.0 — Local Stability Sign-off

**Roadmap:**

```text
Local Stability Sign-off  →  Freeze Prime v1.0 Core  →  Tier 2 Workflow Systems
```

Holocron/VPN is **secondary stress only** — not the release gate from home.

### What “pass” means

Not only automated tests. The app should **feel**:

- **Lighter** — no Blender subprocess flood on STL/OBJ browse
- **Quieter** — bounded queues, rate-limited diagnostics
- **Predictable** — same folder behaves the same way twice
- **Fast on repeat scans** — READY cache, metadata cache, LRU reuse
- **Stable on close** — exit code **0**, `MeshStager shutdown complete`

### Sign-off folders (local only)

Run all four on `C:\MeshStager_Test_Data`, `E:\MeshStager_Test`, or local SSD/NVMe (not Holocron):

| # | Profile | Asset mode |
|---|---------|------------|
| 1 | **Local STL folder** | 3D |
| 2 | **Local image folder** | Images |
| 3 | **Local ZIP-heavy folder** | 3D (archives in tree) |
| 4 | **Local mixed 1,000+ folder** | 3D |

Optional env overrides: `ROUNDUP_LOCAL_*` (see table below). Automated seed: `scripts/validate_prime_v10_local_stability_signoff.py`.

### Signals to watch (especially STL + mixed 1k+)

Console/log: `Prime thumb paint:` (~every 5s) and scan line `Prime v0.8 cache diagnostics:`.

| Signal | Pass expectation |
|--------|------------------|
| `native_jobs_enqueued` | **Rising** on STL/OBJ browse |
| `bridge_jobs_pending` | **Low** on STL-only trees |
| `blender_jobs_skipped_native_supported` | **Rising** (native owns STL/OBJ auto path) |
| `cache_hits` | **Rising** while scrolling back over decoded rows |
| Metadata `scan_hits` / hit rate | **Improves on second scan** of same folder |
| Exit code | **0** on normal close |

**Settings for real sign-off:** Thumbnail generation = **Auto recommended**; **Auto-generate thumbnails after scan** = on.

**Purpose:** Validate Tier 1 workflow (browse → search → inspect → workspace → metadata) before Tier 2.

**Automated pre-check (repo root, builds temp trees on local disk):**

```text
.venv\Scripts\python.exe scripts\validate_prime_v10_local_stability_signoff.py
```

The script disables **auto-thumbnail-after-scan** for speed; run thumbnail steps in the manual checklist below.

**Optional real folders** (set all five to skip auto-seed):

| Variable | Profile |
|----------|---------|
| `ROUNDUP_LOCAL_SMALL` | 50–200 mixed files |
| `ROUNDUP_LOCAL_MEDIUM` | 1,000+ mixed files |
| `ROUNDUP_LOCAL_MESH` | STL / OBJ / FBX |
| `ROUNDUP_LOCAL_IMAGES` | JPG / PNG / PSD / TIF |
| `ROUNDUP_LOCAL_ARCHIVES` | ZIP-heavy sample |

Example paths: `E:\MeshStager_Test\small_mixed`, `C:\MeshStager_Test_Data\project_copy`, or any local test tree you create.

### Manual checklist

#### Launch & browse

- [ ] Launch cleanly (source or EXE); footer counts sane.
- [ ] **Browse Source** → pick a local folder (`C:\MeshStager_Test_Data` or `E:\MeshStager_Test`).
- [ ] **Scan Source** completes; rows appear quickly; UI stays interactive.

#### Asset mode

- [ ] Switch **Asset Mode** (3D ↔ Images); working set clears.
- [ ] Rescan the **same** source in the new mode; extensions match mode.

#### Search (local medium folder, 1k+)

- [ ] `ext:stl` — count narrows; status **Searching…** then **N matches**.
- [ ] `size>100mb` — only large files (if any in folder). Automated seed uses `size>10mb` on a ~12 MB local stub.
- [ ] `faces>10000` — meaningful **after** inspecting a few meshes (metadata loads in background).

#### Inspector & metadata

- [ ] Select one STL/OBJ → **Metadata** and **Diagnostics** tabs populate.
- [ ] Geometry fields fill in background (faces/dims/watertight) without freezing.
- [ ] Multi-select shows multi summary.

#### Thumbnails (3D mode, Blender optional)

- [ ] **Settings → Thumbnail generation:** **Auto recommended** (default after native pivot).
- [ ] **Auto-generate thumbnails after scan** on for real STL sign-off (automated script turns this off).
- [ ] **Local STL folder** — watch console/log for `Prime thumb paint:` (every ~5s with Prime perf active):

| Counter | Expect on local STL |
|---------|---------------------|
| `native_jobs_enqueued` | Rises as thumbs generate |
| `bridge_jobs_pending` | Stays **low** (cap 32 local; often 0–2 for STL-only) |
| `bridge_jobs_skipped_native_supported` | Rises (Blender not used for STL/OBJ auto path) |
| `bridge_idle_enqueues` | Low or zero for pure STL trees (idle fill skips native-owned formats) |

- [ ] **PASS (STL):** thumbs appear progressively; scroll stays smooth; **no Blender flood**; rescan reuses READY/LRU cache (faster second pass).
- [ ] **Regenerate** on selected mesh (graceful if Blender missing).
- [ ] **Generate visible / current view** thumbnails — queue bounded; no UI freeze.
- [ ] Fast scroll: placeholders stable; no **Not Responding**.

Optional: `set ROUNDUP_TIMING=1` before launch for extra timing lines.

#### Export & layout

- [ ] **Export Current View** → CSV has **15 columns** (first 7 unchanged).
- [ ] **Layout** → preset (e.g. Review) + **Save layout as…** / load.
- [ ] Quit → relaunch → splitter, view mode, filters restore sensibly.

#### Shutdown

- [ ] Close while **idle** → clean exit, code 0.
- [ ] Close while thumbnails **active** (scan or bridge queue) → no hang; `MeshStager shutdown complete` in log.

### Pass condition

All four folder profiles above: workflow checks pass; signals match expectations; subjective gate met (**lighter, quieter, predictable**). No **Not Responding** during scan, search, scroll, or inspector.

### After local pass — Freeze Prime v1.0 Core

From sign-off forward until Tier 2 ships:

| Allowed | Not allowed |
|---------|-------------|
| Bugfixes | Pipeline rewrites |
| Polish / UX tweaks | Thumbnail architecture changes |
| Targeted perf fixes | Scan architecture changes |
| Tier 2 **new** systems on top | Move/copy/export contract changes |

Then begin **Tier 2 — Workflow Systems** on a stable platform.

### Should NOT see (local)

- Long freeze after scan before rows show.
- Search leaving stale full list (status stuck on old **Filtered.** while query is active).
- Inspector empty for a selected STL after several seconds (check trimesh / file size defer).
- Splitter or session layout lost after relaunch.
- Forced quit or exit code non-zero on normal close.

### Unit tests (Tier 1, no scan)

```text
.venv\Scripts\python.exe -m pytest meshcorral/tests/test_search_polish.py meshcorral/tests/test_layout_persistence.py meshcorral/tests/test_metadata_richness.py -q
.venv\Scripts\python.exe scripts/validate_prime_v10_tier1_regression.py
```

### Secondary (when VPN/server is healthy)

- Holocron search: `scripts/validate_prime_v10_search_holocron.py`
- Holocron Tier 1 stress: `scripts/validate_prime_v10_tier1_signoff.py`

---

## MeshStager v0.1.0-rc1 — Quick Manual QA Checklist

### Setup

- Launch the app (from source or EXE).
- Confirm the window opens and the footer shows counts (Indexed / Visible / Selected / Queue).

### Scan folder

- Click **Scan Source** and choose a folder with mixed files.
- Toggle **Include subfolders** on/off and verify scan results change accordingly.
- Switch **Asset Mode** (3D / DCC Assets ↔ Images / Textures) and confirm it clears results and requires a new scan.

### Search & filters

- Type into **Name contains** and verify results update after a short pause.
- Use **Type**, **Ext**, and **Folder** filters together and verify they combine as expected.
- Use **Reset Filters** and confirm view returns to the full working set.

### Table ↔ Gallery

- Switch **Table** and **Gallery** and confirm selection behavior remains sensible.
- Change **Gallery Size** and confirm the view updates.

### Blender thumbnails (optional bridge)

- If Blender is available:
  - Select an `.stl` or `.obj` and click **Generate thumbnail**.
  - Queue multiple files via multi-select.
  - Confirm **Jobs (n)** updates as the queue changes.
  - Open **Jobs → Pending queue…** and cancel a pending job.
  - Open **Jobs → Job history…** and verify output/log actions work.
- If Blender is not available:
  - Confirm the app stays usable and thumbnail actions fail gracefully.

### Move / Copy / Export

- Set a **Destination** folder.
- Select a small set of files and run **Copy Selected To…**
  - Confirm the preview shows OK/Blocked/Error rows.
  - Confirm copies appear in destination and originals remain.
- Run **Move Selected…**
  - Confirm moved files are removed from the working set.
  - Confirm collisions are blocked (no overwrite).
- Run **Export Current View** and verify the CSV file is created and readable.

### Settings save/load

- Open **Settings**.
- Change theme (dark/light) and confirm it applies after Save.
- If available, set Blender path and click **Test Blender**.
- Close and reopen the app; confirm settings persist.

### Close / reopen

- Close the app normally.
- Relaunch and confirm it opens cleanly.

## Prime Performance v0.4 — Server Folder / Holocron QA (secondary stress)

**Test folder example:** `\\holocron\Sculpt\Sculpt Drop Folder\...`

**Note:** Not the primary release gate while testing remotely over VPN. Pass **Local Stability Sign-off** first.

**Purpose:** Validate that UI responsiveness is decoupled from thumbnail generation speed.

### Setup

- Launch from source or EXE with **auto-thumbnail after scan** enabled (Settings).
- Use **3D Asset Mode** and scan the holocron (or similar) folder with **Include subfolders** as needed.
- Prefer a folder with **200+** mesh assets (`.stl` / `.obj` / `.fbx`) for a meaningful pass.

### Checklist

#### 1. Scan completes

- Rows/gallery appear quickly after scan.
- User can interact within ~1–2 seconds after scan result population.
- App does not wait for all thumbnails before showing the folder.

#### 2. Status hint

- Shows **“Server folder detected: visible thumbnails load first.”** or equivalent large-folder/visible-first hint.

#### 3. Footer progress

- Shows coarse progress like **“Generating thumbnails… (3/25)”**.
- Updates about once per second.
- Does not spam one status message per file.

#### 4. Placeholders

- Non-ready rows show stable format cards/placeholders.
- Rows do not flicker between random states.
- Off-screen rows may remain placeholders by design.

#### 5. Scrolling

- Scrolling through 200+ assets remains responsive.
- No 1–2 second stalls while thumbnails finish in the background.

#### 6. Visible-first thumbnails

- Thumbnails load for visible rows first.
- Scrolling down queues nearby visible rows.
- App does not auto-queue the entire tree at once.

#### 7. Interaction during generation

- User can select rows.
- User can filter.
- User can open **Jobs**.
- User can export current view.
- User can use inspector without the window becoming **Not Responding**.

#### 8. Should NOT see

- Long pause after scan before rows appear.
- Freeze every time a thumbnail job completes.
- Gallery/table full rebuilds or flashing.
- Hundreds of per-file footer messages.
- Window marked **Not Responding** during thumbnail generation.

### Pass condition

Browsing a large `\\holocron\...` folder should feel like a production asset browser: **fast catalog first**, **lazy thumbnails second**, **background generation third**.

### Known acceptable limits

- Thumbnail generation may still take minutes.
- Blender queue may still run one job at a time.
- Rows never scrolled to may remain placeholders.
- Inspector large preview may be slower than gallery paint.

## Prime Performance v0.9 — Scroll / Holocron QA

**Test folder example:** `\\holocron\Sculpt\Sculpt Drop Folder\...` (or a subfolder with **500–1,000+** assets)

**Purpose:** Validate scroll-aware perceived responsiveness on large local/server folders.

### Setup

- Prime stack v0.5–v0.9 enabled (large or network scan).
- **3D Asset Mode**, **Include subfolders** as needed.
- Optional automated probe:  
  `.venv\Scripts\python scripts\validate_prime_v09_holocron.py "\\holocron\...\YourSubfolder"`

### Checklist

#### 1. Fast scroll (500–1,000+ rows)

- Scroll quickly through a long list for **5–10 seconds**.
- UI stays responsive; no **Not Responding**.
- Placeholders stay stable (no full-gallery flashing).

#### 2. Thumbnails pause while moving

- New thumbnails do not race the scrollbar during fast motion.
- Status may show **“Scrolling… thumbnails paused”** (at most ~1 update/sec).

#### 3. Thumbnails resume after settle

- Stop scrolling; within **~300 ms** on server paths (**~160 ms** local), visible rows begin loading again.
- Status may show **“Loading visible thumbnails…”** once, not spammed.

#### 4. Scroll-back reuse

- Scroll back over rows that already decoded; thumbnails reappear from cache without a long stall.

#### 5. Diagnostics (optional: `ROUNDUP_TIMING=1` or debug logs)

- `fast_scroll_suppression_count` increases during rapid scroll.
- `stale_epoch_drops` increases when epoch advances during in-flight decode.
- `cache_hits` rises when scrolling back over decoded rows.

### Pass condition

Fast scrolling feels **smoother** than pre-v0.9: work pauses while moving, resumes after settling, footer does not spam, no window freeze or gallery flash.

### Should NOT see

- Thumbnail decode/queue storms during fast wheel/drag scroll.
- Footer/status changing every few hundred milliseconds.
- Placeholders flickering between unrelated states.
- **Not Responding** while only scrolling (not during a multi-minute Blender backlog).

## Prime Performance v0.10 — Bridge Backpressure QA

**Purpose:** Blender thumbnail jobs must not flood the queue during large scans or scroll.

**Automated pre-check (repo root):**

```text
.venv\Scripts\python.exe scripts\validate_prime_v10_bridge_pass.py
```

### Setup

- Prime stack active (200+ files, network path, or slow scan).
- Blender configured; **auto-thumbnail after scan** on.
- Large 3D folder (holocron or similar).

### Watch (log every ~5s: `Prime thumb paint:`)

| Counter | Expect |
|--------|--------|
| `bridge_jobs_pending` | Stays ≤ **32** (local) or **12** (remote) |
| `bridge_jobs_running` | **0** or **1** only |
| `bridge_jobs_suppressed` | Increases when cap is hit during scroll/scan |
| `bridge_duplicate_skips` | Increases on repeated viewport passes over same files |
| `bridge_idle_enqueues` | Non-zero only after scroll settle + decode quiet + UI idle ≥ 2s |

### Checklist

1. Scan completes; UI stays interactive.
2. Fast scroll: no rapid wall of `Enqueued Blender Bridge job` lines (no 100+ burst in one second).
3. Visible / near-visible meshes still queue thumbnails (selected → visible → preload order).
4. After sitting idle, additional jobs may trickle in (`bridge_idle_enqueues`); pending still capped.
5. Close app → `MeshStager shutdown complete`, exit code **0**.

### Pass condition

Blender jobs no longer flood. Visible/near-visible thumbnails still generate. Idle fill only when UI is quiet. Close exits cleanly.

### Should NOT see

- 100+ bridge enqueue log lines in a few seconds after one scan/scroll.
- `bridge_jobs_pending` stuck far above cap.
- Idle-tier jobs while actively scrolling or decoding.

## Prime v1.0 Sprint C — Search polish (Holocron — secondary)

**Default automated folder:** `\\holocron\Sculpt\Sculpt Drop Folder\STL DROP\Movie` (~1,000+ indexed rows)

Prefer local 1k+ folder for release sign-off; see **Local Stability Sign-off** above.

```text
.venv\Scripts\python.exe scripts\validate_prime_v10_search_holocron.py
```

Override: `ROUNDUP_VALIDATE_FOLDER` or pass a subfolder with 1,000+ assets.

### Manual UI checklist

1. Scan a 1,000+ file holocron folder (3D Asset Mode, subfolders as needed).
2. Search: `ext:stl` → count drops; status **Searching…** then **N matches**; UI stays interactive.
3. Search: `folder:starwars` (or a folder name that exists in your tree).
4. Search: `size>100mb` (requires enriched sizes).
5. Search: `vader helmet` (plain text).
6. Clear search → full filtered view returns.

### Pass condition

- No **Not Responding** while typing or after debounce (~400 ms).
- Match counts look correct; selection restores by path when the row is still visible.
- Thumbnails do not fully reset/flicker (cache hits should not drop to zero on search alone).

### Defer

- Table/gallery **highlight** styling until search UX feels confusing without it.

## Prime v1.0 Sprint D — Persistent layouts

### Auto-restore

- Close MeshStager after changing panel widths (drag splitter), view mode, thumb size, filters, inspector tab.
- Relaunch → layout should match (session stored in QSettings).

### Layout menu (header **Layout**)

- **Save layout as…** — name a custom workspace.
- **Load layout** — built-ins + saved names.
- **Reset layout to defaults**.
- **Preset:** Scanning, Review, Texture Audit, Export Prep, Sculpt Review.

### Quick checks

1. Drag main splitter → quit → reopen → splitter sizes restored.
2. Gallery + 160px thumbs → save as “My Review” → reset → load “My Review”.
3. Preset **Texture Audit** → Images mode + gallery (does not auto-rescan).

## Prime v1.0 Tier 1 — Regression (before Sprint E)

```text
.venv\Scripts\python.exe scripts/validate_prime_v10_tier1_regression.py
```

Covers: session/named/preset layout, search after preset, inspector tab, source path preserved, layouts package does not touch scan/thumb code.

Optional holocron search: `scripts/validate_prime_v10_search_holocron.py`

## Prime v1.0 Sprint E — Metadata richness

### Inspector (STL/OBJ)

- Select a mesh → Metadata tab shows dimensions (mm), faces, vertices, watertight, density when trimesh can parse.
- Large files (>100 MB default) show **deferred** status without freezing (set `ROUNDUP_METADATA_ALLOW_LARGE_INSPECTOR=1` to force).

### Search tokens (when metadata loaded)

- `faces>100000`, `watertight:true`, `archive_members>0`

### Export

- CSV appends rich metadata columns after the original seven table columns.

```text
python -m pytest meshcorral/tests/test_metadata_richness.py -q
```

