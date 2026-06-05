# RC3 Thumbnail Quality Regression Fix

**Status:** Active quality policy · **Date:** 2026-06-04

## Problem

RC3 gallery performance work shipped **fast proxy thumbnails** that are **not the final visual target**. Compared to the reference screenshot **Screenshot 2026-05-08 000006**, current defaults look:

- Speckled / point-cloud (not solid shaded)
- Flat contrast
- Noisy silhouettes
- Unprofessional in an asset-browser context

This document tracks the **balanced default quality** fix while **preserving RC3 speed safeguards**.

## Visual reference

**Target style:** `Screenshot 2026-05-08 000006` — professional shaded thumbnails with clean silhouettes, readable contrast, and asset-browser presentation.

**Not the target:** Sparse vertex splats on large transparent backgrounds.

## Quality policy (default)

| Tier | File size / path | Render mode | Visual | Auto-HQ? |
|------|------------------|-------------|--------|----------|
| **Small** | Local, &lt; 8 MB | `balanced` | Solid shaded surface raster | No |
| **Medium** | Local, 8–48 MB | `balanced` (reduced face budget) | Solid shaded surface raster | No |
| **Large** | ≥ 48 MB | `proxy` | Fast improved splat | No |
| **Server/network** | Small/medium on network path | `balanced` | Staged + shaded surface (not permanently proxy) | No |
| **Server/network** | Large on network path | `proxy` | Fast splat first pass + staging cache | No |
| **Manual HQ** | User regenerate | `high` | Full surface raster budget | Yes (opt-in only) |
| **Deferred** | Prime large-folder browse | Placeholder card | No render until visible | N/A |

**HQ / manual render** remains available for selected files. **Large and server files do not auto-HQ.**

## Render paths

| Path | Role |
|------|------|
| Native CPU `MeshRenderPipeline` | STL/OBJ/PLY/GLB — balanced surface default for small/medium |
| Blender Bridge | `.blend`, `.fbx` — professional result when Blender configured |
| Disk `render_cache` | Separate keys per `render_mode` + `thumbnail_style_v2` |
| Bridge job index | Blender/native job `thumbnail.png` |
| Placeholder cards | Deferred / unsupported / failed — compact professional copy |

## Cache separation

Fingerprint includes:

```
path | size | mtime | max_px | render_mode | thumbnail_style_v2
```

Old speckled proxy entries are **not reused** after the style version bump.

## UI labels (RC3 copy)

| Mode | Label |
|------|--------|
| Fast large-file path | **Proxy Preview** |
| Small/medium default | **Balanced Preview** |
| Manual regenerate | **HQ Preview** |
| Prime deferral | **Deferred Preview** (not broken) |

## Preserved RC3 behavior

- Gallery virtualized list + scroll perf tests
- Scan heartbeat / cooperative cancel
- Metadata clarity
- Responsive dialog fixes
- Branding
- Proxy/deferred safeguards for huge files
- Non-blocking thumbnail generation

## Verification

```bat
.\.venv\Scripts\python.exe -m unittest meshcorral.tests.test_gallery_scroll_perf
.\.venv\Scripts\python.exe -m unittest meshcorral.tests.test_thumbnail_quality_regression
.\.venv\Scripts\python.exe scripts\comprehensive_stress_test.py --quick --cleanup
```

Manual: compare small STL/OBJ thumbs against Screenshot 2026-05-08 000006; confirm large folder still defers and does not auto-HQ.
