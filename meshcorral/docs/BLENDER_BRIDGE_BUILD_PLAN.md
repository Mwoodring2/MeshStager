# Blender Bridge Build Plan (Optional Worker)

## Purpose

Roundup (the desktop app) stays the main **production control center**:
- indexing, search, tagging, renaming
- batch queue management and job history
- lightweight previews and exports

Blender is an **optional** background worker used only for heavier DCC operations:
- thumbnail/turntable rendering
- format conversion
- deeper geometry/material analysis
- (later) repair, remesh, decimate, UV checks, baking

This bridge is designed to be:
- **non-destructive** (never overwrites originals)
- **repeatable** (every operation is a job with a saved JSON request)
- **debuggable** (per-job logs + result files)
- **optional** (the app runs normally when Blender is not installed)

## High-level architecture

```
Roundup / Mesh / Texture App
        |
        | writes job request JSON + launches Blender (optional)
        v
Blender Headless Worker
        |
        | runs Python script(s)
        v
Outputs (in a controlled folder):
- rendered thumbnail(s)
- metadata JSON
- CSV report (later)
- logs (per job)
```

## Phase 1: Scaffold the bridge (plumbing only)

We add the folder structure and placeholder modules first, without integrating deeply into the UI.

### Target folder structure

```
meshcorral/
  app/
    bridge/
      blender_locator.py
      blender_bridge.py
      job_models.py
      job_runner.py

blender_worker/
  scripts/
    run_job.py
    thumbnail_render.py

data/
  jobs/
    pending/
    running/
    complete/
    failed/

outputs/
  blender_bridge/
```

### Goal
- **Create the plumbing first** (models, runner, folders, logging conventions).
- No heavy mesh operations yet.

## Phase 2: Detect Blender (optional dependency)

The app needs a reliable way to find Blender, but must remain functional without it.

### Detection methods (in priority order)
- **Manual path** set in app settings (most reliable)
- **Auto-detect** common Windows install locations
- Optional: environment variable override (useful for studios / CI)

### UX requirements
- A **“Test Blender”** action that verifies the path works (runs `blender.exe --version`)
- Clear messaging when Blender is unavailable:
  - bridge features are disabled
  - the rest of the app still works

### Example install paths
- `C:\Program Files\Blender Foundation\Blender 4.4\blender.exe`
- `C:\Program Files\Blender Foundation\Blender 5.0\blender.exe`

### Goal
- Blender Bridge is **strictly optional** and fails gracefully.

## Phase 3: Send jobs using JSON job files

We do not “talk to Blender live” at first. Instead, Roundup writes a job request to disk.
This makes jobs replayable, debuggable, and safe to run on a separate worker later.

### Example job file (concept)

```json
{
  "job_id": "thumb_001",
  "job_type": "thumbnail_render",
  "source_file": "E:/models/creature.stl",
  "output_dir": "outputs/blender_bridge/thumb_001",
  "settings": {
    "resolution": 512,
    "view": "isometric"
  }
}
```

### Safety rules (non-negotiable)
- **Never overwrite the original source file**
- Originals are treated as **read-only inputs**
- All outputs are written under a **per-job output directory**
- Output filenames include a **clear operation suffix** (example: `_thumb.png`)

### Goal
- Each operation is a **job type** with a versionable schema.

## Phase 4: Run Blender headless

Roundup launches Blender in the background, passing the job JSON path to a worker script.

### Command shape

```bash
blender.exe --background --python blender_worker/scripts/run_job.py -- job.json
```

### Worker responsibilities
- Read the job JSON
- Execute exactly one job
- Write outputs + a `result.json`
- Exit with a useful exit code

### Goal
- Use Blender’s power without forcing the user to open Blender manually.

## Phase 5: Proof of concept job — generate a thumbnail

We start with one job only:
- **Generate Blender thumbnail for selected mesh**

### Inputs
- A single mesh file: `.stl`, `.obj`, `.fbx`, `.glb`, etc. (best-effort import)

### Outputs (per job)
- `thumbnail.png`
- `result.json` (status + paths + any error message)
- `job_log.txt` (captured Blender stdout/stderr)

### Constraints
- No mesh repair yet
- No baking yet
- No deep geometry ops yet

### Goal
- Prove the end-to-end bridge works: **settings → job JSON → headless Blender → output files**.

## Phase 6: Return logs + status to the app

Roundup should surface job execution results in a user-friendly way.

### Status model (minimum)
- Queued
- Running
- Complete
- Failed

### Per-job details in UI
- status + timestamps
- output folder path (open button)
- log file path (view button)
- error message if failed

### Goal
- No silent failures; every job is inspectable.

## Phase 7: Expand job types (incrementally, one safe tool at a time)

After the thumbnail POC is stable, we add heavier tools one-by-one:
- format conversion
- mesh diagnostics / deeper analysis
- decimation
- mesh repair
- UV inspection
- texture baking / reprojection
- turntable render export

### Principle
Each new tool is:
- its own **job type**
- has a clear **input/output contract**
- remains **non-destructive**
- adds tests + documented expectations

## Implementation notes (beginner-friendly guidance)

- Keep the bridge code isolated under `app/bridge/` so the core app stays simple.
- Prefer “files on disk” contracts (job + result JSON) before adding any networking.
- Treat Blender as unreliable/optional:
  - Blender missing, wrong version, or broken install should be handled cleanly.
- Always write to controlled output directories; never write next to the original mesh.

