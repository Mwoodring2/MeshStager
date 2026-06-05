# RC4 Thumbnail Backend Evaluation

**Status:** Research note only — no code changes, no new dependencies  
**Date:** 2026-06-04  
**Scope:** Evaluate optional external render backends without replacing or blocking the active RC3 thumbnail pipeline.

**Related:** [RC3_THUMBNAIL_QUALITY_REGRESSION.md](RC3_THUMBNAIL_QUALITY_REGRESSION.md) · [MESHSTAGER_UI_UX_GUIDE.md](MESHSTAGER_UI_UX_GUIDE.md) · [RENDER_SPEED_QUALITY_STRATEGY.md](RENDER_SPEED_QUALITY_STRATEGY.md)

---

## 1. Core product rule

Preview quality must support **asset identification**.

Speed improvements are only valid if users can still **confirm the correct mesh** — especially for vendor, archive, and outside assets where filenames and metadata are unreliable. A fast thumbnail that looks like noise or a point cloud is not an improvement.

This rule applies to any future backend evaluation. Visual polish is secondary to identification.

---

## 2. Current RC3 pipeline (do not replace)

RC3 ships a **stability-first, CPU-native** thumbnail stack with tiered quality modes and RC3 gallery performance safeguards. This pipeline remains the default and the release path.

| Component | Role |
|-----------|------|
| **Native CPU renderer** | Primary fallback for STL, OBJ, PLY, GLB, GLTF via `MeshRenderPipeline` / `NativeThumbnailBackend` |
| **Balanced Preview** | Default for small/medium local files and small/medium network files — shaded surface raster (`thumbnail_style_v2`) |
| **Proxy Preview** | First-pass fast render for large files (≥ 48 MB), including large network paths; improved splat, not the visual target |
| **HQ Preview** | Manual regenerate only — never auto for large or server files |
| **Blender Bridge** | Preferred for `.blend` and `.fbx` when Blender is configured; native remains fallback |
| **Disk cache** | Fingerprint: `path \| size \| mtime \| max_px \| render_mode \| thumbnail_style_v2` — modes do not share keys |
| **Deferred / prime browse** | Placeholder first pass for huge folders; non-blocking workers; gallery scroll optimizations preserved |

**Visual reference:** `Screenshot 2026-05-08 000006` — clean shaded mesh, readable silhouette, strong contrast.

**RC3 constraints that any future backend must respect:**

- Do not block scanning or gallery scrolling
- Do not auto-HQ very large files
- Cache by quality mode and style version
- Handle failures gracefully (compact placeholders, not giant “Unsupported” cards when a render is possible)

---

## 3. External tools to evaluate

Research-only candidates. None are integrated today. No new dependencies in RC3.

### F3D

| Aspect | Notes |
|--------|-------|
| **Role** | Likely **best candidate** for an optional future backend |
| **Strengths** | VTK-based; strong format coverage; headless CLI; widely used for fast 3D preview; good shaded output potential |
| **Risks** | Windows packaging and redistribution (VTK runtime); CLI flag stability across versions; vendor-file crash handling must be tested |
| **RC4 intent** | Spike as **optional** backend behind existing router — not a default swap |

### stl-thumb

| Aspect | Notes |
|--------|-------|
| **Role** | Good **reference** for fast STL / OBJ / 3MF thumbnails |
| **Strengths** | Focused scope; simple CLI mental model; useful benchmark for “how fast can mesh thumbs be” on common formats |
| **Risks** | Narrow format set vs MeshStager’s full 3D inventory; may not cover GLB/PLY/vendor edge cases |
| **RC4 intent** | Compare speed/quality against native balanced path; borrow ideas, not necessarily ship as dependency |

### minirender

| Aspect | Notes |
|--------|-------|
| **Role** | Useful **server/cloud reference** — not the first Windows desktop target |
| **Strengths** | Designed for headless thumbnail generation in pipeline/server contexts |
| **Risks** | Deployment model may assume Linux/container infra; Windows desktop packaging unclear |
| **RC4 intent** | Inform staging/cache patterns for network assets; defer desktop integration |

---

## 4. Evaluation criteria

Use the same matrix for every candidate. Score each pass/fail or note blockers.

| Criterion | Question |
|-----------|----------|
| **Visual quality / silhouette readability** | Can a user identify the asset from the thumb alone (vendor meshes, thin parts, holes)? |
| **Speed — small files** | &lt; 8 MB local/network; must not regress browse responsiveness |
| **Speed — medium files** | 8–48 MB; acceptable queue latency under auto-thumbnail caps |
| **Speed — large files** | ≥ 48 MB; proxy-tier or faster without blocking UI |
| **Windows packaging difficulty** | Single-folder or installer-friendly? DLL/runtime footprint? Code signing impact? |
| **CLI stability** | Deterministic flags, exit codes, stderr on failure; safe to wrap from Python subprocess |
| **Supported formats** | Overlap with MeshStager 3D set (STL, OBJ, PLY, GLB, GLTF, FBX, BLEND, 3MF, etc.) |
| **Headless operation** | No GUI, no user interaction — suitable for background workers |
| **Deterministic PNG output** | Same input + settings → same pixels (or documented acceptable variance) for cache fingerprints |
| **License and redistribution** | Compatible with MeshStager distribution; attribution; commercial use |
| **Bad / vendor file handling** | Corrupt, huge, non-manifold, or exotic exports fail cleanly without hanging the worker |

**Pass bar for any optional backend:** Meets or beats RC3 **Balanced Preview** identification quality on small/medium files, without violating RC3 performance safeguards on large archives.

---

## 5. Recommendation

| Decision | Rationale |
|----------|-----------|
| **Keep `thumbnail_style_v2` and the RC3 native pipeline** | Shipped, tested, cache-versioned, aligned with asset-identification policy |
| **Do not block RC3 on new renderer research** | RC3 release criteria stand on current backends + gallery perf tests |
| **Test F3D in RC4 as optional backend only** | Highest upside for quality/speed balance; integrate behind `ThumbnailRouter` only after spike passes criteria |
| **Use stl-thumb as a benchmark reference** | Inform native raster tuning; not required for RC4 ship |
| **Defer minirender for desktop** | Revisit if server-side staging or cloud preview becomes a product requirement |

### RC4 spike outline (documentation only)

1. Manual F3D install on Windows dev machine — no repo dependency yet  
2. Render sample set: small/medium/large STL/OBJ/GLB + 2–3 ugly vendor files  
3. Compare output to `Screenshot 2026-05-08 000006` and RC3 Balanced/Proxy/HQ modes  
4. Record timing, exit codes, and packaging notes in a follow-up spike log  
5. If spike passes, design an **opt-in** settings flag and separate cache fingerprint suffix — still no RC3 default change without explicit approval  

---

## Out of scope for this note

- Replacing `MeshRenderPipeline` or removing native balanced/proxy tiers  
- Adding pip/npm/Cargo dependencies to the MeshStager application  
- Auto-HQ for large or network files  
- Changing gallery virtualization, scan heartbeat, or deferred-first browse behavior  

---

## Verification (unchanged RC3 bar)

Any RC4 backend experiment must not regress:

```bat
.\.venv\Scripts\python.exe -m unittest meshcorral.tests.test_gallery_scroll_perf
.\.venv\Scripts\python.exe -m unittest meshcorral.tests.test_thumbnail_quality_regression
.\.venv\Scripts\python.exe scripts\comprehensive_stress_test.py --quick --cleanup
```
