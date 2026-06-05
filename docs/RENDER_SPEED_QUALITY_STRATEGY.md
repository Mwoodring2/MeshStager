# MeshStager — Speed + Quality Render Strategy

**Status:** Staged plan (RC2 handoff) — documentation and policy alignment only.  
**Render pipeline flow is unchanged** until future implementation passes explicitly adopt this document.

---

## Executive summary

RC2 benchmarks showed:

| Finding | Implication |
|---------|-------------|
| **Main bottleneck:** `load_import` (mesh read + parse + trimesh build) | Optimize import, cache, and proxy — not only final PNG raster |
| **Cache works:** repeat runs ~instant when fingerprint matches | Aggressive PNG output cache is mandatory |
| **Proxy policy works** for large archive assets (397–566 MB OBJ/STL are normal) | Large files are not “errors”; they use **proxy-by-default** |
| **HQ not auto-triggered** on large/network paths | Quality is **on demand** |
| **CPU path today** | Stable default; GPU is a future optional layer |

**Design principle:** Fast by default. High quality on demand. Cache everything safe. Never block the UI. CPU remains reliable. GPU added later as an upgrade.

---

## Performance modes

MeshStager should choose behavior from **user intent**, **file size**, **local vs server path**, and **cache state** — not a single render path for every file.

### 1. Fast Browse Mode (default)

**When:** Folder scan, gallery/table browse, server/archive trees, first-time indexing, auto-thumbnail after scan.

| Rule | Behavior |
|------|----------|
| Cache first | Use `render_cache/` PNG if path + size + mtime + mode match |
| No auto-HQ | Never queue full-quality render for whole folders |
| Large / network | **Proxy** preview only (`>= 48 MB` or network-like path) |
| Huge files | Proxy or metadata-only; defer full mesh work (see thresholds) |
| UI | Background workers only; footer status updates |

**Goal:** The app feels fast while browsing thousands of assets.

**Maps to RC2 today:** `for_auto_enqueue=True`, `high_quality=False`, output cache + proxy policy in `render_pipeline_policy.py`.

---

### 2. Balanced Preview Mode

**When:** User selects a row, inspector preview, single-file focus after browse.

| Rule | Behavior |
|------|----------|
| Geometry | Enough for dimensions/metadata + clean preview |
| Size tiers | Direct CPU below 48 MB; proxy at/above 48 MB unless HQ requested |
| Output | “Nice” thumbnail, not studio render |
| Cache | Write PNG to `render_cache/` after successful render |

**Goal:** Normal working mode — informative preview without studio cost.

**Maps to RC2 today:** Native CPU raster + geometry metadata stage; `standard` or `proxy` mode from `resolve_render_mode()`.

---

### 3. High Quality Manual Mode

**When:** User explicitly requests quality (regenerate, “HQ preview”, manual Blender path where configured).

| Rule | Behavior |
|------|----------|
| Trigger | **User action only** — not auto-scan, not auto-enqueue |
| Scope | Selected file(s), not entire folder |
| Cost | Higher resolution, more points, optional Blender bridge |
| Storage | Separate cache fingerprint / job output (bridge `result.json` + PNG) |
| Huge files | Warn or confirm above **250 MB**; queue job above **750 MB** (planned UX) |

**Goal:** Beauty when asked; speed when not.

**Maps to RC2 today:** `ThumbnailManualOverride.NATIVE` / `BLENDER`, `high_quality=True` in `MeshRenderPipeline.render_png_bytes()`.

---

### 4. Diagnostic Benchmark Mode

**When:** Developers/testers run `scripts/benchmark_render_pipeline.py`.

| Rule | Behavior |
|------|----------|
| Warm-up | **Internal mini STL only** (`%LOCALAPPDATA%\MeshStager\benchmark\internal_warmup.stl`) |
| Timing | JSONL to `logs/render_timing.log` per stage |
| Repeat | `--repeat 2` proves cache; `--clear-*-cache` for controlled runs |
| Recommendation | One-line bottleneck from uncached stage totals |

**Goal:** Answer “network vs import vs render vs cache write” with evidence.

**Maps to RC2 today:** Fully implemented; see `PERFORMANCE_DIAGNOSTICS.md`.

---

## Size and path thresholds

Large production meshes (397–566 MB OBJ/STL) are **expected archive assets**, not failures. The system treats them **carefully**, not as “unsupported.”

| Tier | Size | Local behavior | Server/network behavior | HQ |
|------|------|----------------|-------------------------|-----|
| **Small** | 0–48 MB | Direct CPU preview (`standard`) | Stage if needed; then same as local | Manual only |
| **Medium** | 48–250 MB | **Proxy by default**; cache PNG | Stage locally first; proxy; aggressive cache | Manual only |
| **Large** | 250–750 MB | Proxy-first; metadata always | Staging + proxy; reuse staged copy | Manual + **warn** (planned) |
| **Huge** | 750 MB+ | Cached/proxy/metadata browse; no auto full import for browse (planned) | Same + staging | Manual + **confirm** + optional background job (planned) |

### RC2 implemented today

| Threshold | Config | Location |
|-----------|--------|----------|
| Proxy at **≥ 48 MB** | `MESHSTAGER_PROXY_THRESHOLD_MB` (default `48`) | `render_pipeline_policy.py` |
| Proxy max pixels | `MESHSTAGER_PROXY_MAX_PX` (default `192`) | `render_pipeline_policy.py` |
| Proxy vertex budget | `MESHSTAGER_PROXY_MAX_POINTS` (default `18000`) | `render_pipeline_policy.py` |
| Network auto path | `is_network_like_path()` → proxy when `for_auto_enqueue` | `path_perf.py` + policy |
| **250 MB / 750 MB** tiers | **Not in code yet** — documented here for next policy pass |

Environment overrides (optional, no code change required):

```text
MESHSTAGER_PROXY_THRESHOLD_MB=48
MESHSTAGER_PROXY_MAX_PX=192
MESHSTAGER_PROXY_MAX_POINTS=18000
ROUNDUP_NATIVE_THUMB_MAX_POINTS=60000
```

---

## Server and network handling

**Order of operations (RC2 pipeline — unchanged):**

```text
1. Check PNG output cache (fingerprint: path, size, mtime, mode)
2. If hit → "Using cached preview" (skip load/render)
3. If miss and network-like → stage to render_staging/ (timed: stage_copy_s)
4. Load/import mesh from local path (staged or original) (timed: load_import_s)
5. Geometry/metadata (timed: geometry_metadata_s)
6. Proxy or HQ raster (timed: preview_proxy_s / render_hq_s)
7. Write PNG to render_cache/ (timed: write_cache_s)
```

**Staging reuse:** Same path + size + mtime → reuse staged file without re-copy.

**Benchmark:** `stage_copy_s` vs `load_import_s` must be reported separately (RC2 profiler does this).

---

## CPU vs GPU plan

### Current (RC2)

| Stage | Engine |
|-------|--------|
| Mesh import | CPU (trimesh) |
| Geometry / metadata | CPU |
| Proxy / standard thumbnail | CPU point-cloud raster |
| Optional beauty | Blender bridge (subprocess; GPU not assumed) |
| Caching | Disk PNG + JSON metadata |

### Future GPU layer (optional, not required)

| Principle | Detail |
|-----------|--------|
| Fallback | CPU path remains when GPU unavailable |
| Scope | **HQ manual** and shaded viewport-style previews |
| Implementation | Blender Cycles/OptiX/CUDA when configured |
| Benchmark | Report `cpu` vs `gpu` in timing logs when added |

**Where GPU helps:** lighting, shaded HQ render, Cycles/Eevee-quality stills.

**Where GPU does not fix RC2 bottleneck:** OBJ/STL parsing, ASCII text parse, server file read, cache lookup, folder scan.

---

## Import optimization plan (future — not RC2 scope)

Long-term speed wins without touching original archive files:

| Initiative | Benefit |
|------------|---------|
| **Cache-first browse** | If PNG exists and unchanged, skip `trimesh.load` entirely |
| **Format awareness** | Prefer binary STL, PLY, glTF/GLB over ASCII STL / heavy OBJ when advising workflows |
| **Lightweight metadata index** | Store bounds, vertex/face counts, thumb fingerprint in SQLite/metadata cache |
| **Generated proxy mesh cache** | Optional simplified mesh on disk for repeat views (separate from PNG) |
| **No full import for table thumb** | When bridge/native thumb already indexed, defer deep import to inspector |

**OBJ note:** Often slow (text, materials, large vertex buffers). Treat as normal but proxy-first.

**ASCII STL note:** Much slower than binary STL — same extension, different cost; future detection optional.

---

## UX safeguards

| Requirement | RC2 status | Target |
|-------------|------------|--------|
| Never block UI | Native queue + bridge queue on workers | Keep |
| Status: “Copying from server” | `RenderStatusNotifier` | Keep |
| Status: “Loading mesh” | Yes | Keep |
| Status: “Rendering preview” / proxy | Yes | Keep |
| Status: “Using cached preview” | Yes | Keep |
| Status: “HQ requested” | Partial (manual path); label explicitly in next UX pass | Add |
| Cancel / skip long render | Planned — not RC2 | Add job cancellation |
| Warn before HQ on huge file | Planned (250 MB+) | Settings + dialog |

---

## Planned policy / settings layer (next implementation pass)

Do **not** rewrite the pipeline in one step. Add a thin policy config consumed by existing `resolve_render_mode()`:

```text
Fast Browse:
  cache_first: true
  proxy_over_mb: 48
  hq_auto: false

Balanced:
  proxy_over_mb: 48
  direct_below_mb: 48

HQ Manual:
  user_trigger_only: true
  warn_over_mb: 250
  confirm_over_mb: 750

Server:
  stage_locally: true
  cache_aggressive: true
```

Future Settings UI (conceptual):

```text
Preview Quality:  [ Fast ]  [ Balanced ]  [ High Quality — manual only ]
```

---

## Benchmark acceptance criteria (RC2)

Use these to sign off performance diagnostics without destabilizing the handoff:

| Criterion | Pass condition |
|-----------|----------------|
| **Repeat cache** | `--repeat 2` → cache hit rate rises sharply (ideally 100% on unchanged files for run 2) |
| **No auto-HQ on huge** | No `render_mode=high` without `--high-quality` or manual override |
| **Network staging separated** | `stage_copy_s` visible in log for UNC paths; not folded into `load_import` |
| **Warm-up** | Internal mini STL only; cold start not inflated by 500 MB user mesh |
| **Bottleneck honesty** | Recommendation matches slowest uncached stage (RC2: often `load_import`) |
| **Proxy on large archive** | 397–566 MB files use `proxy` in run 1, not HQ |
| **Smoke tests** | `comprehensive_stress_test.py --quick --cleanup` → 53 OK |
| **Profiler tests** | `test_render_timing_profiler` + `test_benchmark_render_pipeline` → pass |

Example commands (handoff root):

```bat
.venv\Scripts\python.exe scripts\benchmark_render_pipeline.py "E:\archive" --clear-render-cache
.venv\Scripts\python.exe scripts\benchmark_render_pipeline.py "E:\archive" --repeat 2
.venv\Scripts\python.exe scripts\benchmark_render_pipeline.py "\\server\share\archive" --clear-staging-cache
```

---

## Target user experience

| Moment | Expected feel |
|--------|----------------|
| Open folder | Fast scan; rows appear |
| Browse | Thumbnails/proxies fill in; UI responsive |
| Click file | Good preview; metadata visible |
| Large archive mesh | Proxy quickly; not “broken” |
| Same file again | Instant cached preview |
| Need beauty | User triggers HQ; app warns if huge |
| Need proof | Benchmark shows bottleneck line |
| Server asset | Staged once; cached; repeat is cheap |
| GPU later | Optional HQ boost; CPU still works |

---

## Related documentation

| Document | Purpose |
|----------|---------|
| `RC3_THUMBNAIL_QUALITY_PLAN.md` | **Next milestone** — proxy visual polish, HQ action, badges (planning only) |
| `PERFORMANCE_DIAGNOSTICS.md` | Tester benchmark commands and log interpretation |
| `HANDOFF_RC2_STATUS.md` | RC2 package validation summary |
| `render_pipeline_policy.py` | Implemented thresholds (48 MB proxy, network proxy) |
| `mesh_render_pipeline.py` | Stage order (cache → stage → load → geometry → render → write) |

---

## Revision history

| Date | Note |
|------|------|
| 2026-06-01 | Initial strategy doc — post RC2 puck benchmark; flow unchanged |
