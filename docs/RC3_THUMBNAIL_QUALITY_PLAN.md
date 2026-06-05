# MeshStager RC3 — Thumbnail Quality + Preview Policy

**Milestone:** RC3 Thumbnail Quality + Preview Policy  
**Status:** Planning only — **does not block RC2** (RC2 remains Beta / Release Candidate)  
**Render pipeline flow:** Unchanged until RC3 implementation passes land explicitly.

RC2 proved the system works: CPU-native proxy thumbnails, cache hits on repeat, correct bottleneck identification (`load_import`), and tester-safe defaults. RC3 is the **next polish target**: better preview visuals and clearer quality tiers in the UI — without sacrificing fast browse.

---

## Relationship to RC2

| RC2 (shipped / handoff) | RC3 (next) |
|-------------------------|------------|
| Performance diagnostics | Visual quality + preview policy UX |
| Proxy-by-default for large files | **Better-looking** proxy (less speckle) |
| Single PNG cache keyed by `render_mode` | **Separate** proxy vs HQ cache entries |
| Regenerate thumbnail (Blender-oriented copy) | Explicit **“Generate HQ Preview”** for selection |
| ThumbHealth: ready / pending / missing / failed | Add **Cached / Proxy / HQ / Deferred** badges |
| ~20–27 s first uncached large STL | Same import cost; faster *perceived* quality via cache + proxy polish |

**Final call:** Screenshots and logs showing speckled but completing thumbnails do **not** regress to alpha. They confirm RC2 behavior and define RC3 scope.

---

## Current RC2 behavior (baseline)

Documented so RC3 changes are measurable and RC2 stays stable.

### CPU-native proxy render

- Backend: `cpu_native` via `NativeThumbnailBackend` → `MeshRenderPipeline`
- Raster: vertex **point splat** with Lambert shading (`meshcorral/services/render/mesh_rasterizer.py`)
- Logs: `thumbnail_backend=cpu_native`, `render_mode=proxy` for large files
- Proxy limits: `MESHSTAGER_PROXY_MAX_PX` (default 192), `MESHSTAGER_PROXY_MAX_POINTS` (default 18000)

### Visual character today

- **Usable** for browse and identification
- **Speckled / noisy** — sparse points, small splat radius, transparent gaps between samples
- **Not final-quality** — intentional stability-first design (no GPU, no Blender required)

### Cached repeat behavior

- Output cache: `%LOCALAPPDATA%\MeshStager\render_cache\`
- Fingerprint: path + size + mtime + max_px + **`render_mode`** (`proxy` | `standard` | `high`)
- Repeat view: **near-instant** when unchanged (`used_cached_output=true` in `render_timing.log`)
- Benchmark: run 2 often **100% cache hits** on same folder

### Proxy mode for large files

- **≥ 48 MB** → `proxy` unless HQ requested (`render_pipeline_policy.py`)
- Network-like paths + auto-enqueue → `proxy`
- Large archive STL/OBJ (397–566 MB) treated as **normal assets**, not errors
- First uncached render: dominated by **mesh import** (~15–27 s observed), not PNG encode

### HQ only on demand

- `high_quality=True` or manual override only
- No auto-HQ on huge folders or network scans
- Blender bridge remains optional path for some formats (`.fbx`, etc.)

### UI status (RC2)

Footer / pipeline messages include:

- Copying from server  
- Loading mesh  
- Rendering preview  
- Using cached preview  

---

## RC3 goals

Improve thumbnail **appearance** and **clarity of quality tier** while preserving:

1. Fast browse (proxy + cache first)  
2. Non-blocking UI (background workers)  
3. CPU fallback always available  
4. RC2 timing/logging intact  

---

## Improved proxy visual style (proposed)

**Problem:** Point-cloud raster reads as **speckled** — gaps, uneven density, weak silhouette.

**Direction:** Keep CPU-only proxy path; improve **how** points/faces are drawn — do not require GPU for browse.

| Technique | Purpose |
|-----------|---------|
| **Solid shaded surface** | Where faces exist, rasterize filled triangles (or denser splats) instead of isolated points |
| **Smoother normals** | Recompute or smooth vertex normals before lighting |
| **Better lighting contrast** | Key + fill light or ambient term; avoid flat gray mush |
| **Cleaner silhouette** | Depth sort + optional **edge outline** (1 px) for readability at small thumb size |
| **Less speckle** | Increase effective coverage: larger splat kernel, optional **density-aware** subsampling (not uniform stride) |
| **Anti-aliased edges** | Supersample thumb then downscale (optional, bounded cost) |

**Implementation note (future):** Prototype in `mesh_rasterizer.py` behind env flag e.g. `MESHSTAGER_PROXY_STYLE=v2` so RC2 point-cloud remains fallback.

**Explicit non-goals for proxy pass:**

- Studio lighting / materials  
- Full-resolution mesh render  
- Auto-HQ on large files  

---

## Separate proxy vs HQ caches (proposed)

RC2 uses one cache directory; fingerprint already includes `render_mode`. RC3 should make tiers **visible and intentional**:

| Tier | Cache key includes | Typical path |
|------|-------------------|--------------|
| **Proxy** | `render_mode=proxy` (+ max_px proxy) | Fast browse, auto-queue |
| **HQ** | `render_mode=high` (+ higher max_px) | Manual action only |
| **Standard** | `render_mode=standard` | Medium local files |

**UX rule:**

- Showing proxy thumb does **not** block HQ generation — HQ writes a **different** cache entry  
- Inspector can prefer HQ PNG when present, else proxy, else placeholder  
- Log/cache meta: `preview_tier: proxy | hq | standard | cached`

**Bridge thumbs:** Keep existing `bridge/outputs` index; RC3 maps bridge complete jobs to **HQ** tier where applicable.

---

## “Generate HQ Preview” — selected-file action (proposed)

**Today:** Regenerate thumbnail (Blender-centric tooltip in inspector).

**RC3:**

| Element | Behavior |
|---------|----------|
| **Menu / button** | “Generate HQ Preview” — enabled for selected row only |
| **Scope** | One file (or small multi-select cap, e.g. 5) |
| **Policy** | Calls `high_quality=True`; warns if **≥ 250 MB**; confirm if **≥ 750 MB** (align with `RENDER_SPEED_QUALITY_STRATEGY.md`) |
| **Status** | Footer: “HQ requested” / “Rendering HQ preview” |
| **Never** | Auto-run on folder scan or “generate all” for huge archives |

**Logging:** `render_timing.log` entries with `render_mode=high` and explicit `thumbnail_render_profile` for support.

---

## Preview quality badges (proposed)

Extend beyond `ThumbHealth` (bridge index state) to show **quality tier** when a thumb exists:

| Badge | Meaning |
|-------|---------|
| **Cached** | PNG served from `render_cache/` without re-render this session |
| **Proxy** | Native CPU proxy tier (fast browse) |
| **HQ** | High-quality manual or Blender bridge output |
| **Deferred** | File too large / policy skip — metadata only until user requests |

**Placement:** Table thumb column, gallery overlay, inspector subline (alongside existing thumb status).

**Implementation sketch:**

- New enum or flags on thumb index metadata (not replacing `ThumbHealth`)  
- Resolver: check cache meta + bridge `result.json` `thumbnail_render_profile`  
- Filters (optional): “Proxy only” / “HQ available”  

---

## UX safeguards (RC3 additions)

| Requirement | RC2 | RC3 target |
|-------------|-----|------------|
| Non-blocking UI | Yes | Keep |
| Clear status strings | Partial | Add **Proxy preview**, **HQ requested** |
| Cancel / skip long job | No | Cancel native queue job + bridge job by source path |
| Defer huge file auto work | Proxy only | **Deferred** badge + no queue until user acts |

**Cancel behavior (planned):**

- User selects “Skip preview” or closes inspector during render  
- Worker checks cancellation token; log `error_message=cancelled`  
- UI returns to Deferred or last cached tier  

---

## CPU fallback and GPU (future)

| Layer | RC3 priority |
|-------|----------------|
| **CPU native proxy** | Default for browse — **improve visuals first** |
| **CPU native HQ** | Manual tier — higher px / face raster |
| **Blender bridge HQ** | Existing; document as HQ path for `.fbx` etc. |
| **Blender GPU (Cycles/OptiX)** | **After** CPU/proxy quality stable — HQ only, optional |

GPU does **not** fix RC2’s main bottleneck (OBJ/STL import). RC3 still invests in import/cache policy from RC2 strategy doc.

---

## Future implementation plan (phased)

### Phase RC3a — Visual proxy polish (low risk)

1. Add `MESHSTAGER_PROXY_STYLE` flag and improved raster path  
2. A/B compare on puck/archive samples  
3. Keep old raster as fallback if flag unset  
4. Unit tests: PNG non-empty, bounds, no crash on mini STL  

### Phase RC3b — Cache + badges

1. Document proxy vs HQ in cache sidecar JSON  
2. Inspector/table badge component  
3. Prefer HQ asset in large preview when available  

### Phase RC3c — HQ action + cancel

1. “Generate HQ Preview” on selection  
2. Size warnings (250 / 750 MB)  
3. Job cancellation in native queue  

### Phase RC3d — Blender GPU HQ (optional)

1. Settings: “Use GPU for HQ Blender jobs” when Blender + GPU detected  
2. Benchmark compare CPU vs GPU HQ only  
3. CPU remains fallback  

**RC3 does not start Phase RC3d until RC3a–c are tester-signed.**

---

## Acceptance criteria (RC3)

| Criterion | Pass condition |
|-----------|----------------|
| Proxy browse | Large files still default to proxy; no auto-HQ |
| Proxy look | Subjective: “solid enough” at 192px — less speckle than RC2 baseline (capture before/after screenshots) |
| HQ manual | Single selection → HQ completes or clear failure; badge **HQ** |
| Dual cache | Proxy thumb remains after HQ generated; inspector can show HQ |
| Repeat browse | Cached/Proxy badge; repeat open **&lt; 100 ms** perceived when PNG hit |
| RC2 regression | Smoke 53 OK; benchmark warm-up internal STL; bottleneck still honest |
| RC2 timing | `load_import` still dominant on first uncached huge STL |
| UI | No main-thread block &gt; 100 ms on thumb paint |

---

## Configuration review (no code changes in this doc)

Align with `docs/RENDER_SPEED_QUALITY_STRATEGY.md`:

| Setting | RC2 | RC3 note |
|---------|-----|----------|
| `MESHSTAGER_PROXY_THRESHOLD_MB` | 48 | Unchanged |
| `MESHSTAGER_PROXY_MAX_PX` | 192 | May add `MESHSTAGER_HQ_MAX_PX` later |
| `MESHSTAGER_PROXY_MAX_POINTS` | 18000 | Tune when surface raster added |
| `ROUNDUP_NATIVE_THUMB_SPLAT` | 0–2 | Superseded partly by surface raster |

---

## Logging and diagnostics

RC3 implementation must preserve RC2 logs and extend metadata only:

```json
{
  "render_mode": "proxy",
  "thumbnail_backend": "cpu_native",
  "preview_tier": "proxy",
  "proxy_style": "v2",
  "used_cached_output": false
}
```

Benchmark and `render_timing.log` remain the source of truth for performance regressions.

---

## Related documents

| Document | Role |
|----------|------|
| `RENDER_SPEED_QUALITY_STRATEGY.md` | Speed tiers, size thresholds, server staging |
| `PERFORMANCE_DIAGNOSTICS.md` | Benchmark commands (RC2) |
| `HANDOFF_RC2_STATUS.md` | RC2 handoff validation |
| `mesh_rasterizer.py` | Current point-cloud proxy implementation |
| `render_cache.py` | PNG fingerprint cache |
| `render_pipeline_policy.py` | Proxy vs HQ mode resolution |

---

## Revision history

| Date | Note |
|------|------|
| 2026-06-01 | Initial RC3 plan — planning only; RC2 unchanged |
