# SPDX-License-Identifier: GPL-2.0-or-later
# flake8: noqa
# isort: skip_file
"""
Blender: render a PNG thumbnail for a mesh (STL or OBJ) without modifying the source file.
"""

from __future__ import annotations

import json
import shutil
import typing
from collections import Counter
from pathlib import Path
from typing import Any, Callable

if typing.TYPE_CHECKING:
    import bpy  # type: ignore[import-not-found]

LogFn = Callable[[Path, str], None]

# Curves/surfaces/metaballs can appear inside complex OBJ hierarchies — convert to evaluated mesh geometry.
_CONVERTIBLE_EMPTY_TYPES = frozenset(
    {"CURVE", "SURFACE", "META"}
)


def _write_result(
    out_dir: Path,
    *,
    job_id: str,
    job_type: str,
    status: str,
    source_file: str,
    output_dir: str,
    thumbnail_path: str | None,
    error_message: str | None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "job_id": job_id,
        "job_type": job_type,
        "status": status,
        "source_file": source_file,
        "output_dir": output_dir,
        "thumbnail_path": thumbnail_path,
        "error_message": error_message,
    }
    (out_dir / "result.json").write_text(
        json.dumps(data, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _append_log(out_dir: Path, line: str, log: LogFn) -> None:
    log(out_dir, line)


def _ensure_addon_enabled(module: str) -> None:
    """
    Best-effort enable for bundled importers (FBX/GLTF, etc).

    In many Blender builds these are enabled by default, but `--factory-startup` can disable them.
    """
    import bpy

    try:
        if getattr(bpy.context, "preferences", None) is None:
            return
        addons = getattr(bpy.context.preferences, "addons", None)
        if addons is not None and module in addons:
            return
        bpy.ops.preferences.addon_enable(module=module)
    except Exception:  # noqa: BLE001
        # If the importer is unavailable, the later import op will surface a clearer error.
        return


def _ensure_addon_disabled(module: str) -> None:
    """Best-effort disable for bundled addons when they break specific importers."""
    import bpy

    try:
        if getattr(bpy.context, "preferences", None) is None:
            return
        addons = getattr(bpy.context.preferences, "addons", None)
        if addons is not None and module not in addons:
            return
        bpy.ops.preferences.addon_disable(module=module)
    except Exception:  # noqa: BLE001
        return

def _scene_object_summary(scene: object) -> tuple[int, str]:
    """Return total object count and a compact breakdown by bpy.types.Object.type."""
    objs = tuple(scene.objects)
    if not objs:
        return (0, "none")
    counts = Counter(o.type for o in objs)
    parts = [f"{k}:{counts[k]}" for k in sorted(counts.keys(), key=lambda t: str(t))]
    return len(objs), ", ".join(parts)


def _list_mesh_objects(scene: object):
    """All mesh datablock objects suitable for framing/render (excluding linked library orphans)."""
    out = []
    for o in scene.objects:
        if o.type != "MESH" or o.data is None:
            continue
        try:
            if getattr(o, "library", None) is not None:
                continue
        except AttributeError:
            pass
        out.append(o)
    return out


def _unhide_for_render(scene: object, objects: object) -> None:
    """Ensure objects participate in depsgraph/bounds calculation (viewport + render visibility)."""
    for o in objects:
        try:
            if getattr(o, "hide_viewport", None) is True:
                o.hide_viewport = False
        except (AttributeError, TypeError):
            pass
        try:
            if getattr(o, "hide_render", None) is True:
                o.hide_render = False
        except (AttributeError, TypeError):
            pass
        try:
            if getattr(o, "hide_get", None) is not None and callable(o.hide_get):  # type: ignore[union-attr]
                try:
                    if o.hide_get():  # type: ignore[attr-defined]
                        if getattr(o, "hide_set", None):
                            o.hide_set(False)  # type: ignore[arg-type]
                except ReferenceError:
                    pass
        except (AttributeError, TypeError):
            pass


def _convert_convertible_geometry_to_mesh(
    *,
    scene: object,
    log: LogFn,
    out_dir: Path,
) -> int:
    """
    Convert standalone curve/surface/meta objects to meshes in-place.

    Returns how many conversions were attempted (best-effort; failures logged only).
    """
    import bpy

    vl = bpy.context.view_layer
    attempted = 0
    objs = list(scene.objects)
    for ob in objs:
        if getattr(ob, "type", "") not in _CONVERTIBLE_EMPTY_TYPES:
            continue
        if getattr(ob, "library", None) is not None:
            continue
        try:
            bpy.ops.object.select_all(action="DESELECT")
            ob.select_set(True)
            vl.objects.active = ob
            _unhide_for_render(scene, [ob])
            attempted += 1
            bpy.ops.object.convert(target="MESH")
        except Exception as exc:  # noqa: BLE001
            _append_log(
                out_dir,
                f"Convert attempt skipped for '{getattr(ob, 'name', '?')}': {exc}",
                log,
            )
        finally:
            try:
                ob.select_set(False)
            except (ReferenceError, RuntimeError):
                pass
    return attempted


def _resolve_mesh_objects_for_thumbnail(
    *,
    scene: object,
    ext: str,
    out_dir: Path,
    log: LogFn,
):
    """
    Populate mesh_objects for STL/OBJ paths.

    STL is expected to emit meshes directly; OBJ may include curves/meta only —
    optionally convert geometry to meshes when **ext == .obj**.
    Returns (mesh_objects:list|None, error_message|None).
    """
    mesh_objects = _list_mesh_objects(scene)
    _unhide_for_render(scene, mesh_objects)

    if mesh_objects:
        return mesh_objects, None

    # OBJ-specific recovery: Blender may import some assets as curves/surfaces/metaballs.
    if ext == ".obj":
        n_conv = _convert_convertible_geometry_to_mesh(
            scene=scene,
            log=log,
            out_dir=out_dir,
        )
        if n_conv:
            _append_log(out_dir, f"Convertible geometry conversion attempts: {n_conv}", log)
        mesh_objects = _list_mesh_objects(scene)
        _unhide_for_render(scene, mesh_objects)
        if mesh_objects:
            return mesh_objects, None

    total, breakdown = _scene_object_summary(scene)
    mesh_objects = _list_mesh_objects(scene)

    if not mesh_objects:
        return None, (
            f"Imported {total} objects, 0 meshes. Types: [{breakdown}]."
            " Unable to derive renderable geometry (check OBJ contents or converters)."
        )

    _unhide_for_render(scene, mesh_objects)
    return mesh_objects, None


def _set_render_engine(scene) -> None:
    """Headless: prefer Cycles on CPU; fall back to EEVEE if needed."""
    import bpy
    try:
        prop = scene.render.bl_rna.properties["engine"]
        ids = {e.identifier for e in prop.enum_items}
    except (AttributeError, KeyError, TypeError):
        ids = set()
    if "CYCLES" in ids:
        scene.render.engine = "CYCLES"
        if hasattr(scene, "cycles"):
            if hasattr(scene.cycles, "device"):
                scene.cycles.device = "CPU"  # type: ignore[attr-defined]
            if hasattr(scene.cycles, "samples"):
                scene.cycles.samples = 16  # type: ignore[attr-defined]
        return
    for name in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        if name in ids:
            scene.render.engine = name
            return


def render_thumbnail(
    job: dict[str, Any],
    out_dir: Path,
    log: LogFn,
) -> None:
    """
    Read-only import of the mesh, render ``thumbnail.png`` into ``out_dir``, write ``result.json``.

    The source file on disk is never modified.
    """
    import bpy
    from mathutils import Vector

    job_id = str(job.get("job_id", ""))
    source_path = Path(str(job.get("source_path", "")))
    out_dir = out_dir.resolve()
    source_abs = str(source_path.resolve())
    out_abs = str(out_dir)
    params = job.get("params") or {}
    res_x = int(params.get("resolution_x", 512))
    res_y = int(params.get("resolution_y", 512))
    transparent = bool(params.get("transparent", True))

    jt = str(job.get("job_type", "generate_thumbnail"))

    def fail(msg: str) -> None:
        _append_log(out_dir, msg, log)
        _write_result(
            out_dir,
            job_id=job_id,
            job_type=jt,
            status="failed",
            source_file=source_abs,
            output_dir=out_abs,
            thumbnail_path=None,
            error_message=msg,
        )

    if not job_id:
        fail("Job JSON missing job_id.")
        return
    if not source_path.is_file():
        fail(f"Source file not found: {source_path}")
        return

    ext = source_path.suffix.lower()
    if ext not in (".stl", ".obj", ".fbx"):
        fail(f"Only .stl, .obj, and .fbx are supported in this proof-of-concept. Got: {ext}")
        return

    # Clean default scene
    try:
        bpy.ops.wm.read_factory_settings()
        bpy.ops.object.select_all(action="SELECT")
        bpy.ops.object.delete()
    except Exception as e:  # noqa: BLE001
        fail(f"Could not clear scene: {e}")
        return

    src_arg = str(source_path.resolve())
    if ext == ".stl":
        try:
            bpy.ops.wm.stl_import(filepath=src_arg)
        except Exception as e:  # noqa: BLE001
            fail(f"STL import failed: {e}")
            return
    elif ext == ".obj":
        try:
            bpy.ops.wm.obj_import(
                filepath=src_arg,
                forward_axis="NEGATIVE_Z",
                up_axis="Y",
            )
        except Exception as e:  # noqa: BLE001
            fail(f"OBJ import failed: {e}")
            return
    else:
        try:
            _ensure_addon_enabled("io_scene_fbx")
            # v0.1 thumbnails: mesh only. Some Blender builds/importers break when importing FBX
            # lights via Cycles settings; disabling Cycles avoids that code path.
            _ensure_addon_disabled("cycles")
            bpy.ops.import_scene.fbx(filepath=src_arg, use_anim=False, use_custom_props=False)
        except Exception as e:  # noqa: BLE001
            fail(f"FBX import failed: {e}")
            return

    mesh_objects, geom_err = _resolve_mesh_objects_for_thumbnail(
        scene=bpy.context.scene,
        ext=ext,
        out_dir=out_dir,
        log=log,
    )
    if geom_err:
        fail(geom_err)
        return
    if mesh_objects is None:
        fail("No mesh object found after import.")
        return

    for o in mesh_objects:
        o.select_set(True)
    if bpy.context.view_layer.objects.active is None and mesh_objects:
        bpy.context.view_layer.objects.active = mesh_objects[0]

    b_min = Vector((1e30, 1e30, 1e30))
    b_max = Vector((-1e30, -1e30, -1e30))
    for o in mesh_objects:
        for corner in o.bound_box:
            w = o.matrix_world @ Vector(corner)
            for i in range(3):
                b_min[i] = min(b_min[i], w[i])
                b_max[i] = max(b_max[i], w[i])
    center = (b_min + b_max) * 0.5
    size = b_max - b_min
    max_dim = max(size.x, size.y, size.z, 0.0001)
    dist = max_dim * 2.2
    if dist < 0.1:
        dist = 1.0

    try:
        bpy.ops.object.light_add(type="SUN", location=(center.x + dist, center.y - dist, center.z + dist * 0.6))
        sun = bpy.context.object
        if sun is not None and sun.data and hasattr(sun.data, "energy"):
            sun.data.energy = 2.0
    except Exception as e:  # noqa: BLE001
        _append_log(out_dir, f"Light add (non-fatal): {e}", log)

    try:
        cam_data = bpy.data.cameras.new(name="ThumbCamera")
        cam_obj = bpy.data.objects.new("ThumbCamera", cam_data)
        bpy.context.scene.collection.objects.link(cam_obj)
        cam_obj.location = (center.x + dist * 0.85, center.y - dist * 0.7, center.z + dist * 0.5)
        direction = center - Vector(cam_obj.location)
        if direction.length > 0:
            cam_obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
        bpy.context.scene.camera = cam_obj
    except Exception as e:  # noqa: BLE001
        fail(f"Camera setup failed: {e}")
        return

    scene = bpy.context.scene
    _set_render_engine(scene)

    scene.render.resolution_x = res_x
    scene.render.resolution_y = res_y
    scene.render.film_transparent = bool(transparent)
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA" if transparent else "RGB"

    thumb = out_dir / "thumbnail.png"
    scene.render.filepath = str(out_dir / "thumb_render")

    try:
        bpy.ops.render.render(write_still=True)
    except Exception as e:  # noqa: BLE001
        fail(f"Render failed: {e}")
        return

    if not thumb.is_file():
        for candidate in out_dir.glob("thumb_render*.png"):
            if candidate.is_file():
                try:
                    if candidate != thumb:
                        if thumb.exists():
                            thumb.unlink()
                        candidate.replace(thumb)
                except OSError:
                    shutil.copy2(candidate, thumb)
                break
        for candidate in out_dir.glob("*.png"):
            if candidate.is_file() and candidate.name not in (thumb.name,):
                if not thumb.is_file():
                    try:
                        shutil.copy2(candidate, thumb)
                    except OSError:
                        pass
                break

    if not thumb.is_file():
        fail("Render finished but thumbnail.png was not found in the output directory.")
        return

    _append_log(out_dir, f"Wrote {thumb}", log)
    _write_result(
        out_dir,
        job_id=job_id,
        job_type=jt,
        status="complete",
        source_file=source_abs,
        output_dir=out_abs,
        thumbnail_path=str(thumb),
        error_message=None,
    )
