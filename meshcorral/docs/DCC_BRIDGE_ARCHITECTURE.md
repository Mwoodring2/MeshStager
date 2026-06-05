# Roundup — DCC Bridge architecture (compatibility plan)

**Status:** Planning document only. **No code renames or new DCC integrations in this phase.**

This document prepares Roundup to grow from a **single provider (Blender)** to a **multi-provider “DCC Bridge”**—one shared job pipeline with pluggable **provider adapters** (Blender today; Maya, Houdini, Cinema 4D later).

---

## Naming: “Blender Bridge” → “DCC Bridge”

| Term (target) | Meaning |
|---------------|---------|
| **DCC Bridge** | The universal subsystem: enqueue jobs, run worker processes, persist `result.json` / `log.txt`, refresh history, thumbnails, cleanup/retention. |
| **DCC provider** | A concrete Digital Content Creation tool (Blender, Maya, …). |
| **Provider adapter** | Code that translates universal job requests into provider-specific CLIs, scripts, and filesystem layout. |

**v0.1 / current code** still uses historical names (`blender_bridge`, `BlenderBridge`, “Blender Bridge” in UI copy). A **rename pass** is deferred until a deliberate milestone; this doc describes the **target** structure without changing shipped behavior.

---

## Design: `DccAdapter` + provider implementations

### Base interface: `DccAdapter` (conceptual)

Every provider implements the same logical contract so the core app never forks on “which DCC” beyond the adapter.

**Responsibilities:**

| Area | Adapter answers |
|------|-----------------|
| **Identity** | Provider id (`blender`, `maya`, …), display name |
| **Executable discovery** | Where to look (settings, PATH, standard install roots on Windows/macOS/Linux) |
| **Version check** | Cheap “is this binary usable?” probe (no heavy scene work) |
| **Headless invocation** | argv for background/batch (e.g. Blender `--background`, Maya batch) |
| **Worker payload** | Which script/module runs and how args/env are passed |
| **Capabilities** | Supported `job_type` values and per-type parameters |
| **Validation** | Refuse jobs the provider cannot satisfy before queueing I/O |

The **core** calls only `DccAdapter` (or a small **registry** that picks an adapter by provider id). It does **not** embed Blender- or Maya-specific strings except through the active adapter.

### First implementation: **Blender adapter**

**`BlenderAdapter`** maps universal operations to today’s proof path:

- Executable: `blender.exe` / `blender` (see `SettingsService` + locator)
- Invocation: `blender … --background --python run_job.py …` (actual flags live in runner code today)
- Worker: `blender_worker/scripts/run_job.py`
- Output contract: per-job folder under `outputs/.../<job_id>/` with `result.json` + `log.txt`

Nothing in this plan requires changing that yet; it **documents** the seam.

### Future adapters (not implemented now)

| Provider | Typical headless entry | Notes |
|----------|------------------------|--------|
| **Maya** | `mayapy` / `maya -batch` | `-command` / `-script` patterns; license & env |
| **Houdini** | `hython`, `hbatch` | often session script or `.hip`-less hython one-offs |
| **Cinema 4D** | `Commandline`, `c4dpy` | highly versioned install layout on Windows |

These are **placeholders** for API design; no new dependencies or subprocesses are added in the planning phase.

---

## What stays universal (thin, stable core)

These parts should remain **provider-agnostic** so UI, disk layout, and QA stay predictable.

| Layer | Examples in current codebase |
|-------|-------------------------------|
| **Job queue** | In-memory + on-disk pending/running/complete/failed/cancelled queues under the bridge root |
| **Job models** | `BridgeJobRequest`, `BridgeJobResult`, `BridgeJobStatus`, job type enum |
| **Artifacts** | `result.json` schema (same fields, provider fills values) |
| **Logs** | `log.txt` next to `result.json` |
| **Filesystem layout** | `<bridge_root>/outputs/.../<job_id>/` (today `outputs/blender_bridge/<job_id>/`—rename is a separate migration) |
| **History** | Scan `result.json` files for the job history dialog |
| **Thumbnail index** | Index paths from completed jobs (Blender-generated PNG today; other providers could emit previews the same way) |
| **Retention / cleanup** | Delete only under bridge root; age/mode policies |
| **Status UI** | Status bar, job menus, non-blocking error UX |
| **Error UX** | Standard dialogs, copy path, reveal folder—unchanged by provider |

The **universal rule:** the app reasons about **jobs** and **artifacts**, not about “Blender” unless the active adapter is Blender.

---

## What is provider-specific (swappable per adapter)

| Concern | Blender (today) | Other DCC (later) |
|---------|-----------------|---------------------|
| **Executable resolution** | blender.exe discovery | mayapy, hython, Commandline, … |
| **Version / smoke test** | optional `--version`/light probe | provider-specific |
| **CLI for headless work** | `--background --python …` | `-batch`, `-c`, `hython` script, … |
| **Worker implementation** | Python inside Blender’s runtime | MEL/Python/HS/COFFEE or batch scene graph |
| **Supported job types** | e.g. `generate_thumbnail` for meshes | extend with provider capabilities |
| **Output media** | PNG thumbnail, optional metadata JSON | could add EXR/USD previews—still behind same `result.json` contract |

Providers may also differ in **timeouts**, **retry policy**, and **sandboxing**; those policies can live in the adapter or a shared “execution policy” fed by settings.

---

## Recommended future folder layout

Target layout (after a future refactor; **not applied in v0.1**):

```
meshcorral/app/bridge/
├── core/                    # queue, models, paths, retention (universal)
├── providers/
│   ├── base.py              # DccAdapter ABC / protocol
│   ├── blender/
│   │   ├── adapter.py       # BlenderAdapter
│   │   └── scripts/         # or reuse ../blender_worker at repo root
│   ├── maya/
│   │   └── adapter.py       # future
│   ├── houdini/
│   │   └── adapter.py       # future
│   └── cinema4d/
│       └── adapter.py       # future
```

**Note:** Today’s `meshcorral/app/bridge/` modules and top-level `blender_worker/` remain the **source of truth** until a migration PR explicitly moves them.

---

## Migration plan: “Blender Bridge” → “DCC Bridge”

**Phase A — Documentation & terminology (this document)**  
- Agree on naming, adapter interface, and universal vs provider concerns.  
- **No code changes.**

**Phase B — Introduce adapter seam (Blender only)**  
- Add `DccAdapter` (or `Protocol`) + `BlenderAdapter` that wraps existing `job_runner`/`queue_manager` logic.  
- Route all enqueues and subprocess spawns through `BlenderAdapter`.  
- Behavior and on-disk paths **unchanged** for users.

**Phase C — Naming & paths (optional, breaking-change window)**  
- Rename user-facing strings: “Blender Bridge” → “DCC Bridge”; menu labels may say “DCC jobs (Blender)”.  
- Consider folder rename `outputs/blender_bridge` → `outputs/dcc_jobs` with a one-time migration or symlink for old paths.  
- Update PyInstaller datas, docs, and tests.

**Phase D — Additional providers**  
- Add `MayaAdapter`, etc., each with isolated worker assets and tests behind feature flags or settings.  
- Extend `job_type` and UI only when a provider is selected.

**Rollback strategy:** keep Phase B behind a single factory (`get_active_adapter()`) so Blender remains default and tests can pin to one provider.

---

## Success criteria (for a future implementation PR)

- Core app depends on **`DccAdapter`**, not Blender symbols, outside the Blender package.  
- **One** provider (Blender) passes all existing tests unchanged.  
- `result.json` + `log.txt` contracts remain stable unless versioned.  
- No user workflow regression (scan, filter, move/copy, thumbnails, jobs).

---

## Out of scope (explicit)

- Implementing Maya / Houdini / Cinema 4D workers.  
- Renaming existing Python modules, UI strings, or disk folders **in this planning step**.  
- Database or schema changes.  
- Changing Blender thumbnail behavior for v0.1 users.

---

*Last updated: planning-only document for Roundup compatibility with future DCC providers.*
