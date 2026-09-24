"""Cold-process thumbnail benchmark; inputs are never changed, caches are isolated.

Example: python scripts/benchmark_mesh_thumbnails.py part.stl --output results.json
Use --synthetic-dir DIRECTORY to generate explicitly labelled torus test assets.
No warm-up. Cold means empty application caches, NOT a flushed OS page cache.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def peak_memory_mb():
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ("peak", "working", "a", "b", "c", "d", "e", "f")]
        c = Counters(); c.cb = ctypes.sizeof(c)
        kernel = ctypes.WinDLL("kernel32"); kernel.GetCurrentProcess.restype = wintypes.HANDLE
        fn = ctypes.WinDLL("psapi").GetProcessMemoryInfo
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if fn(kernel.GetCurrentProcess(), ctypes.byref(c), c.cb): return c.peak / 1048576
        return None
    import resource
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return value / (1048576 if sys.platform == "darwin" else 1024)


def worker(path, px, output_dir):
    from dataclasses import asdict
    from PIL import Image
    from meshcorral.services.render import mesh_render_pipeline as pipeline
    from meshcorral.services.render import render_cache
    stages = {}
    def timed(name, fn):
        def call(*args, **kwargs):
            start = time.perf_counter()
            try: return fn(*args, **kwargs)
            finally: stages[name] = stages.get(name, 0.0) + time.perf_counter() - start
        return call
    with tempfile.TemporaryDirectory(prefix="mesh-thumbnail-bench-") as tmp, ExitStack() as stack:
        stack.enter_context(patch.object(render_cache, "RENDER_CACHE_DIR", Path(tmp)/"png"))
        try:
            from meshcorral.services.render import preview_geometry as preview
            stack.enter_context(patch.object(preview, "PREVIEW_CACHE_DIR", Path(tmp)/"geometry"))
        except ImportError: pass
        for name, attr in [("stat_cache_lookup", "read_cached_png"), ("source_import", "_load_mesh"),
                           ("geometry_preparation", "prepare_mesh_arrays"), ("png_write", "write_cached_png")]:
            obj = pipeline.MeshRenderPipeline if attr == "_load_mesh" else pipeline
            original = getattr(obj, attr)
            replacement = timed(name, original)
            stack.enter_context(patch.object(obj, attr, staticmethod(replacement) if attr == "_load_mesh" else replacement))
        stack.enter_context(patch.object(Image.Image, "save", timed("png_encoding", Image.Image.save)))
        renderer = pipeline.MeshRenderPipeline()
        start = time.perf_counter()
        png, record, _ = renderer.render_png_bytes(Path(path), max_px=px, for_auto_enqueue=True, write_timing_log=False)
        cold = time.perf_counter()-start
        measured_stages = {
            "stat_cache_lookup_s": getattr(record, "stat_cache_lookup_s", stages.get("stat_cache_lookup", 0.0)),
            "source_load_import_s": record.load_import_s,
            "geometry_preparation_s": record.geometry_metadata_s + stages.get("geometry_preparation", 0.0),
            "preview_preparation_s": getattr(record, "preview_preparation_s", 0.0),
            "raster_render_s": getattr(record, "raster_render_s", 0.0) or max(0.0, record.preview_proxy_s + record.render_hq_s - stages.get("png_encoding", 0.0)),
            "png_encoding_s": stages.get("png_encoding", 0.0),
            "png_write_s": stages.get("png_write", 0.0),
        }
        result = {"stages": measured_stages, "path":str(path), "bytes":Path(path).stat().st_size, "cold_s":cold,
                  "cold_stages":dict(stages), "timing":asdict(record), "peak_mb":peak_memory_mb()}
        if output_dir:
            target=Path(output_dir); target.mkdir(parents=True,exist_ok=True)
            (target/(Path(path).stem+".png")).write_bytes(png)
        start = time.perf_counter()
        _, warm, _ = renderer.render_png_bytes(Path(path),max_px=px,for_auto_enqueue=True,write_timing_log=False)
        result["warm_s"] = time.perf_counter()-start
        result["warm_hit"] = warm.used_cached_output
        # New output size guarantees a PNG miss while retaining preview geometry.
        start=time.perf_counter()
        _, regen, _=renderer.render_png_bytes(Path(path),max_px=px-16,for_auto_enqueue=True,write_timing_log=False)
        result["regeneration_s"]=time.perf_counter()-start
        result["regeneration_timing"]=asdict(regen)
    return result


def synthetic(directory):
    import numpy as np
    import struct
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    paths=[]
    for u,v in [(250,200),(500,500),(1000,500),(1500,750)]:
        # Closed curved torus with a real opening; distinct triangles, not repeats.
        a=np.arange(u+1)*2*np.pi/u; b=np.arange(v+1)*2*np.pi/v
        x=(2+0.65*np.cos(b)[None,:])*np.cos(a)[:,None]
        y=(2+0.65*np.cos(b)[None,:])*np.sin(a)[:,None]
        z=np.broadcast_to(0.65*np.sin(b)[None,:],x.shape)
        points=np.stack([x,y,z],axis=-1).astype("<f4")
        tris=np.stack([np.stack([points[:-1,:-1],points[1:,:-1],points[1:,1:]],axis=-2),
                       np.stack([points[:-1,:-1],points[1:,1:],points[:-1,1:]],axis=-2)],axis=2).reshape(-1,3,3)
        records=np.zeros(len(tris),dtype=[("n","<f4",3),("v","<f4",(3,3)),("a","<u2")]); records["v"]=tris
        path=directory/f"synthetic_torus_{len(tris)}.stl"
        with path.open("wb") as f:
            f.write(b"MeshStager SYNTHETIC torus benchmark".ljust(80,b" ")); f.write(struct.pack("<I",len(tris))); records.tofile(f)
        paths.append(path)
    return paths


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("files",nargs="*",type=Path); ap.add_argument("--output",type=Path)
    ap.add_argument("--images",type=Path); ap.add_argument("--px",type=int,default=192)
    ap.add_argument("--synthetic-dir",type=Path); ap.add_argument("--worker",action="store_true",help=argparse.SUPPRESS)
    args=ap.parse_args()
    if args.worker:
        print(json.dumps(worker(args.files[0],args.px,args.images))); return
    paths=args.files+(synthetic(args.synthetic_dir) if args.synthetic_dir else [])
    if not paths: ap.error("provide mesh paths or --synthetic-dir")
    results=[]
    for path in paths:
        cmd=[sys.executable,__file__,str(path),"--worker","--px",str(args.px)]
        if args.images: cmd += ["--images",str(args.images)]
        completed=subprocess.run(cmd,capture_output=True,text=True,check=True)
        row=json.loads(completed.stdout); results.append(row)
        print(f"{path.name}: cold={row['cold_s']:.3f}s warm={row['warm_s']:.4f}s peak={row['peak_mb']:.1f}MiB",flush=True)
    if args.output: args.output.write_text(json.dumps(results,indent=2),encoding="utf-8")

if __name__ == "__main__": main()
