"""Generated, temporary STL fixtures; no large binary assets in the repository."""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import gc
import io
import os
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch
import weakref
import numpy as np
from PIL import Image
from meshcorral.services.render import preview_geometry as pg
from meshcorral.services.render import render_cache as rc
from meshcorral.services.render import mesh_render_pipeline as mp
from meshcorral.services.render.solid_preview import render_solid_preview, encode_preview_png


def write_stl(path, triangles, *, count=None, header=b"solid binary STL"):
    data = np.zeros(len(triangles), dtype=pg.STL_DTYPE)
    data["vertices"] = triangles
    with path.open("wb") as stream:
        stream.write(header.ljust(80, b" ")[:80])
        stream.write(struct.pack("<I", len(data) if count is None else count))
        data.tofile(stream)


def tetra():
    v=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1]],dtype=np.float32)
    return v[[[0,2,1],[0,1,3],[0,3,2],[1,2,3]]]


class HeavyPreviewTests(unittest.TestCase):
    def setUp(self):
        self.stack=ExitStack(); self.addCleanup(self.stack.close)
        self.root=Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.source=self.root/"part.stl"
        write_stl(self.source,tetra())
        self.stack.enter_context(patch.object(pg,"PREVIEW_CACHE_DIR",self.root/"geometry"))
        self.stack.enter_context(patch.object(rc,"RENDER_CACHE_DIR",self.root/"png"))

    def render(self, **kwargs):
        return mp.MeshRenderPipeline().render_png_bytes(self.source,max_px=128,write_timing_log=False,**kwargs)

    def _assert_automatic_compact(self, count):
        import hashlib
        block = np.zeros(4000, dtype=pg.STL_DTYPE)
        block["vertices"] = np.tile(tetra(), (1000, 1, 1))
        with self.source.open("wb") as stream:
            stream.write(b"solid binary STL".ljust(80, b" "))
            stream.write(struct.pack("<I", count))
            for start in range(0, count, len(block)):
                block[:min(len(block), count-start)].tofile(stream)
        before = hashlib.sha256(self.source.read_bytes()).digest()
        stat = self.source.stat()
        with patch.object(pg, "build_preview", wraps=pg.build_preview) as build, \
             patch.object(mp, "render_solid_preview", wraps=mp.render_solid_preview) as solid, \
             patch.object(mp.MeshRenderPipeline, "_load_mesh", side_effect=AssertionError("legacy loader reached")):
            png, timing, _ = self.render(for_auto_enqueue=True)
        build.assert_called_once()
        solid.assert_called_once()
        self.assertEqual(timing.render_mode, "balanced")
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).digest(), before)
        self.assertEqual(self.source.stat().st_mtime_ns, stat.st_mtime_ns)

    def test_automatic_tiny_binary_uses_solid(self):
        self._assert_automatic_compact(4)

    def test_automatic_1_to_2_mib_binary_uses_solid(self):
        self._assert_automatic_compact(32000)

    def test_automatic_3_to_5_mib_binary_uses_solid(self):
        self._assert_automatic_compact(80000)

    def test_automatic_7_mib_binary_uses_solid(self):
        self._assert_automatic_compact(146800)

    def test_automatic_above_8_mib_binary_uses_solid(self):
        self._assert_automatic_compact(180000)

    def test_automatic_ascii_and_malformed_use_legacy(self):
        for data in (b"solid ascii\nendsolid ascii\n", b"", b"broken".ljust(84, b"x")):
            with self.subTest(data=data):
                self.source.write_bytes(data)
                with patch.object(pg, "build_preview", wraps=pg.build_preview) as build, \
                     patch.object(mp, "render_solid_preview") as solid, \
                     patch.object(mp.MeshRenderPipeline, "_load_mesh", side_effect=RuntimeError("legacy fallback")) as loader:
                    with self.assertRaisesRegex(RuntimeError, "legacy fallback"):
                        self.render(for_auto_enqueue=True)
                build.assert_called_once()
                loader.assert_called_once()
                solid.assert_not_called()

    def test_other_mesh_extensions_remain_legacy(self):
        for extension in (".obj", ".ply", ".glb", ".gltf"):
            with self.subTest(extension=extension):
                self.source = self.root / ("part" + extension)
                write_stl(self.source, tetra())
                with patch.object(pg, "build_preview") as build, \
                     patch.object(pg, "read_preview") as cache, \
                     patch.object(mp.MeshRenderPipeline, "_load_mesh", side_effect=RuntimeError("legacy fallback")):
                    with self.assertRaisesRegex(RuntimeError, "legacy fallback"):
                        self.render(for_auto_enqueue=True)
                build.assert_not_called()
                cache.assert_not_called()

    def test_uncached_binary_png_is_deterministic(self):
        with patch.object(mp, "read_cached_png", return_value=None), \
             patch.object(pg, "read_preview", return_value=None):
            first, _, _ = self.render(for_auto_enqueue=True)
            second, _, _ = self.render(for_auto_enqueue=True)
        self.assertEqual(first, second)

    def test_v3_png_is_invalidated_without_deleting_cache(self):
        with patch.object(rc, "THUMBNAIL_STYLE_VERSION", "thumbnail_style_v3"):
            self.render(for_auto_enqueue=True)
        old_paths = set((self.root / "png").iterdir())
        with patch.object(pg, "build_preview", side_effect=AssertionError("geometry reprocessed")):
            _, timing, _ = self.render(for_auto_enqueue=True)
        self.assertFalse(timing.used_cached_output)
        self.assertTrue(timing.used_preview_geometry)
        self.assertTrue(all(path.exists() for path in old_paths))
        self.assertEqual(rc.THUMBNAIL_STYLE_VERSION, "thumbnail_style_v4")

    def test_binary_count_and_solid_header(self):
        self.assertEqual(pg.binary_triangle_count(self.source),4)

    def test_unusual_binary_header(self):
        write_stl(self.source,tetra(),header=bytes(range(80)))
        self.assertEqual(pg.binary_triangle_count(self.source),4)
        self.assertIsNotNone(pg.build_preview(self.source,"proxy"))

    def test_ascii_rejected(self):
        self.source.write_text("solid test\nendsolid test\n")
        self.assertIsNone(pg.binary_triangle_count(self.source))

    def test_zero_bytes_rejected(self):
        self.source.write_bytes(b"")
        self.assertIsNone(pg.binary_triangle_count(self.source))

    def test_truncated_and_wrong_count_rejected(self):
        for count in (0,3,5,0xffffffff):
            with self.subTest(count=count):
                write_stl(self.source,tetra(),count=count)
                self.assertIsNone(pg.build_preview(self.source,"proxy"))

    def test_trailing_bytes_rejected(self):
        with self.source.open("ab") as stream: stream.write(b"trailing")
        self.assertIsNone(pg.binary_triangle_count(self.source))

    def test_nonfinite_and_degenerate_fallback(self):
        for triangles in (np.zeros((2,3,3)), np.full((2,3,3),np.nan),np.full((2,3,3),np.inf)):
            write_stl(self.source,triangles)
            self.assertIsNone(pg.build_preview(self.source,"proxy"))

    def test_small_binary_supported(self):
        geometry=pg.build_preview(self.source,"proxy")
        self.assertEqual(geometry.triangles.shape,(4,3,3))

    def test_deterministic_selection(self):
        a=pg.build_preview(self.source,"proxy"); b=pg.build_preview(self.source,"proxy")
        np.testing.assert_array_equal(a.triangles,b.triangles)
        np.testing.assert_array_equal(a.normals,b.normals)

    def test_full_triangle_range_including_last_component(self):
        triangles=np.tile(tetra(),(2000,1,1))
        triangles=np.concatenate((triangles,tetra()+[5,0,0]))
        write_stl(self.source,triangles)
        geometry=pg.build_preview(self.source,"proxy")
        self.assertGreater(geometry.triangles[:,:,0].max(),0.4)
        self.assertLess(geometry.triangles[:,:,0].min(),-0.4)
        self.assertGreaterEqual(len(geometry.triangles),8)

    def test_500k_and_1m_structural_fixtures_bounded(self):
        # Stream repeated tetra records; this tests structure/memory bounds, not visual realism.
        block=np.zeros(4000,dtype=pg.STL_DTYPE); block["vertices"]=np.tile(tetra(),(1000,1,1))
        for count in (500000,1000000):
            with self.subTest(count=count):
                with self.source.open("wb") as stream:
                    stream.write(b"binary".ljust(80,b" ")+struct.pack("<I",count))
                    for _ in range(count//len(block)): block.tofile(stream)
                self.assertEqual(pg.binary_triangle_count(self.source),count)
                geometry=pg.build_preview(self.source,"proxy")
                self.assertEqual(len(geometry.triangles),4)
                self.assertLess(geometry.triangles.nbytes+geometry.normals.nbytes,1024)

    def test_source_never_modified_and_handle_closed(self):
        before=self.source.read_bytes(); stat=self.source.stat()
        self.render()
        self.assertEqual(self.source.read_bytes(),before)
        self.assertEqual(self.source.stat().st_mtime_ns,stat.st_mtime_ns)
        self.source.rename(self.root/"moved.stl")

    def test_preview_cache_roundtrip(self):
        geometry=pg.build_preview(self.source,"proxy"); path=pg.cache_path(self.source,"proxy")
        pg.write_preview(path,geometry); actual=pg.read_preview(path)
        np.testing.assert_array_equal(actual.triangles,geometry.triangles)
        np.testing.assert_array_equal(actual.normals,geometry.normals)

    def test_cache_identity_size_mtime_path_recipe_tier(self):
        original=pg.cache_path(self.source,"proxy")
        stat=self.source.stat()
        os.utime(self.source,ns=(stat.st_atime_ns,stat.st_mtime_ns+1000))
        self.assertNotEqual(pg.cache_path(self.source,"proxy"),original)
        os.utime(self.source,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        with self.source.open("ab") as f: f.write(b"x")
        self.assertNotEqual(pg.cache_path(self.source,"proxy"),original)
        write_stl(self.source,tetra()); os.utime(self.source,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        self.assertEqual(pg.cache_path(self.source,"proxy"),original)
        with patch.object(pg,"PREVIEW_GEOMETRY_VERSION","next"):
            self.assertNotEqual(pg.cache_path(self.source,"proxy"),original)
        self.assertNotEqual(pg.cache_path(self.source,"high"),original)
        other=self.root/"other.stl"; other.write_bytes(self.source.read_bytes())
        os.utime(other,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        self.assertNotEqual(pg.cache_path(other,"proxy"),original)

    def test_corrupt_preview_rebuilt(self):
        self.render(); path=pg.cache_path(self.source,"balanced"); path.write_bytes(b"corrupted")
        with patch.object(rc,"THUMBNAIL_STYLE_VERSION","new"), patch.object(pg,"build_preview",wraps=pg.build_preview) as build:
            png,_,_=self.render()
        self.assertTrue(png.startswith(b"\x89PNG")); build.assert_called_once()
        self.assertIsNotNone(pg.read_preview(path))

    def test_malicious_array_header_rejected_before_allocation(self):
        path=self.root/"bad.npy"
        with path.open("wb") as f:
            np.lib.format.write_array_header_1_0(f,{"descr":"<f4","fortran_order":False,"shape":(10**12,4,3)})
        self.assertIsNone(pg.read_preview(path))

    def test_cache_nonfinite_array_rejected(self):
        path=self.root/"bad.npy"
        np.save(path,np.full((1,4,3),np.nan,dtype="<f4"))
        self.assertIsNone(pg.read_preview(path))

    def test_png_cache_avoids_geometry(self):
        first,_,_=self.render()
        with patch.object(pg,"read_preview",side_effect=AssertionError("geometry opened")), patch.object(mp.MeshRenderPipeline,"_load_mesh",side_effect=AssertionError("source loaded")):
            second,record,_=self.render()
        self.assertEqual(first,second); self.assertTrue(record.used_cached_output)

    def test_style_and_size_regeneration_reuse_geometry(self):
        self.render()
        with patch.object(pg,"build_preview",side_effect=AssertionError("source reparsed")), patch.object(mp.MeshRenderPipeline,"_load_mesh",side_effect=AssertionError("mesh loaded")):
            with patch.object(rc,"THUMBNAIL_STYLE_VERSION","next"):
                _,record,_=self.render()
                self.assertTrue(record.used_preview_geometry)
            _,record,_=mp.MeshRenderPipeline().render_png_bytes(self.source,max_px=144,write_timing_log=False)
            self.assertTrue(record.used_preview_geometry)

    def test_network_preview_hit_skips_staging(self):
        self.render()
        with patch.object(mp,"is_network_like_path",return_value=True),patch.object(mp,"stage_network_file",side_effect=AssertionError("copied")),patch.object(rc,"THUMBNAIL_STYLE_VERSION","new"):
            _,record,_=self.render()
        self.assertTrue(record.used_preview_geometry)
        self.assertFalse(record.used_staging)

    def test_permission_failure_still_renders(self):
        with patch.object(pg.os,"replace",side_effect=PermissionError("test")):
            png,_,_=self.render()
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertEqual(list((self.root/"geometry").glob("*.tmp")),[])

    def test_read_only_cache_parent_still_renders(self):
        blocked=self.root/"blocked"; blocked.write_text("file")
        with patch.object(pg,"PREVIEW_CACHE_DIR",blocked/"geometry"),patch.object(rc,"RENDER_CACHE_DIR",blocked/"png"):
            png,_,_=self.render()
        self.assertTrue(png.startswith(b"\x89PNG"))

    def test_corrupt_png_and_metadata_are_misses(self):
        self.render()
        path=next((self.root/"png").glob("*.png")); path.write_bytes(b"bad")
        _,record,_=self.render(); self.assertFalse(record.used_cached_output)
        for data in ('[]','{"size_bytes": []}', 'not json'):
            next((self.root/"png").glob("*.json")).write_text(data)
            _,record,_=self.render(); self.assertFalse(record.used_cached_output)

    def test_solid_png_transparent_background(self):
        png,_,summary=self.render()
        self.assertIsNone(summary) # no approximate counts passed to metadata system
        image=Image.open(io.BytesIO(png)); self.assertEqual(image.mode,"RGBA")
        alpha=np.asarray(image)[:,:,3]
        self.assertEqual(alpha[0,0],0); self.assertGreater(np.count_nonzero(alpha==255),1000)
        self.assertGreater(np.count_nonzero((alpha>0)&(alpha<255)),0)

    def test_ascii_and_optimized_failure_use_legacy_loader(self):
        for reason in (None, OSError("interrupted")):
            with self.subTest(reason=reason),patch.object(pg,"build_preview",return_value=None,side_effect=reason),patch.object(mp.MeshRenderPipeline,"_load_mesh",side_effect=RuntimeError("legacy reached")) as loader:
                with self.assertRaisesRegex(RuntimeError,"legacy reached"): self.render()
                loader.assert_called_once()

    def test_solid_failure_uses_original_renderer(self):
        with patch.object(mp,"render_solid_preview",side_effect=ValueError("bad projection")),patch.object(mp.MeshRenderPipeline,"_load_mesh",side_effect=RuntimeError("legacy reached")):
            with self.assertRaisesRegex(RuntimeError,"legacy reached"): self.render()

    def test_concurrent_writers_publish_complete_cache(self):
        geometry=pg.build_preview(self.source,"balanced"); path=pg.cache_path(self.source,"balanced")
        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda _:pg.write_preview(path,geometry),range(12)))
        np.testing.assert_array_equal(pg.read_preview(path).triangles,geometry.triangles)
        self.assertFalse(list(path.parent.glob("*.tmp")))

    def test_worker_geometry_not_retained(self):
        references=[]; thread_ids=[]; original=pg.build_preview
        def build(*args,**kwargs):
            geometry=original(*args,**kwargs)
            references.append(weakref.ref(geometry.triangles)); thread_ids.append(threading.get_ident())
            return geometry
        with patch.object(pg,"build_preview",side_effect=build),ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(self.render).result(timeout=10)
        gc.collect()
        self.assertNotEqual(thread_ids[0],threading.get_ident())
        self.assertIsNone(references[0]())

    def test_payload_bit_flip_detected(self):
        path=pg.cache_path(self.source,"balanced")
        pg.write_preview(path,pg.build_preview(self.source,"balanced"))
        raw=bytearray(path.read_bytes()); raw[-40] ^= 1; path.write_bytes(raw)
        self.assertIsNone(pg.read_preview(path))

    def test_midread_truncation_is_safe(self):
        original=pg._records
        def records(stream,count,timings):
            for vertices in original(stream,count,timings):
                yield vertices
                with self.source.open("wb") as target: target.write(b"truncated")
        with patch.object(pg,"_records",side_effect=records):
            with self.assertRaises(ValueError): pg.build_preview(self.source,"balanced")
        self.source.unlink()  # all handles released even on failure

    def test_source_change_does_not_publish_old_generation(self):
        original=pg.build_preview
        def changing(*args,**kwargs):
            geometry=original(*args,**kwargs)
            stat=self.source.stat()
            os.utime(self.source,ns=(stat.st_atime_ns,stat.st_mtime_ns+1000000))
            return geometry
        with patch.object(pg,"build_preview",side_effect=changing),patch.object(mp.MeshRenderPipeline,"_load_mesh",side_effect=RuntimeError("fallback")):
            with self.assertRaisesRegex(RuntimeError,"fallback"): self.render()
        self.assertFalse(list((self.root/"geometry").glob("*.npy")))

    def test_face_budget_exhaustion_falls_back(self):
        with patch.object(pg,"MAX_PREVIEW_TRIANGLES",1):
            self.assertIsNone(pg.build_preview(self.source,"balanced"))

    def test_opening_preserved_and_hq_has_more_geometry(self):
        u,v=80,40
        a=np.arange(u+1)*2*np.pi/u; b=np.arange(v+1)*2*np.pi/v
        x=(2+0.65*np.cos(b)[None,:])*np.cos(a)[:,None]
        y=(2+0.65*np.cos(b)[None,:])*np.sin(a)[:,None]
        z=np.broadcast_to(0.65*np.sin(b)[None,:],x.shape)
        points=np.stack([x,y,z],axis=-1)
        triangles=np.stack([np.stack([points[:-1,:-1],points[1:,:-1],points[1:,1:]],axis=-2),
                            np.stack([points[:-1,:-1],points[1:,1:],points[:-1,1:]],axis=-2)],axis=2).reshape(-1,3,3)
        write_stl(self.source,triangles)
        proxy=pg.build_preview(self.source,"proxy"); high=pg.build_preview(self.source,"high")
        self.assertGreaterEqual(len(high.triangles),len(proxy.triangles))
        image=render_solid_preview(proxy,128); alpha=np.asarray(image)[:,:,3]
        self.assertEqual(alpha[64,64],0)
        self.assertGreater(np.count_nonzero(alpha==255),2000)
        # Interior surface has no sampled-face speckling along the vertical ring.
        self.assertTrue(np.all(alpha[18:35,64] == 255))

    def test_timings_separate_fast_stages(self):
        _,record,_=self.render()
        self.assertGreater(record.load_import_s,0)
        self.assertGreater(record.preview_preparation_s,0)
        self.assertGreater(record.raster_render_s,0)
        self.assertGreater(record.png_encoding_s,0)
        self.assertGreater(record.stat_cache_lookup_s,0)
        self.assertEqual(record.geometry_metadata_s,0)

if __name__ == "__main__": unittest.main()
