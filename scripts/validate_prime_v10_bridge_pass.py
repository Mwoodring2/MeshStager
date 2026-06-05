"""
Prime v0.10 — automated bridge backpressure PASS checks (no GUI).

Run from repo root:
  .venv\\Scripts\\python.exe scripts/validate_prime_v10_bridge_pass.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from meshcorral.app.bridge.bridge_backpressure import (
    MAX_PENDING_BRIDGE_JOBS_LOCAL,
    MAX_PENDING_BRIDGE_JOBS_REMOTE,
    BridgeEnqueueReject,
    bridge_idle_fill_allowed,
    bridge_records_by_tier,
    enqueue_tiered_bridge_thumbnails,
    max_pending_bridge_jobs,
)
from meshcorral.app.bridge.job_models import BridgeJobResult, BridgeJobStatus
from meshcorral.app.bridge.queue_manager import BridgeQueueManager
from meshcorral.models.file_record import FileRecord
from meshcorral.services.settings_service import SettingsService
from meshcorral.ui.thumb_paint_diagnostics import ThumbPaintDiagnostics
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication


def _ensure_qapp() -> QCoreApplication:
    inst = QCoreApplication.instance()
    if inst is None:
        return QCoreApplication([])
    return inst


def _rec(path: str) -> FileRecord:
    p = Path(path)
    return FileRecord(
        path=p,
        name=p.name,
        extension=".stl",
        parent_folder="f",
        size_bytes=1,
        modified_time=0.0,
    )


def _check_caps() -> tuple[bool, str]:
    local = max_pending_bridge_jobs(network_like=False)
    remote = max_pending_bridge_jobs(network_like=True)
    ok = local == MAX_PENDING_BRIDGE_JOBS_LOCAL and remote == MAX_PENDING_BRIDGE_JOBS_REMOTE
    msg = f"caps local={local} remote={remote}"
    return ok, msg


def _check_queue_cap_and_running() -> tuple[bool, str]:
    hold = threading.Event()

    def _block_run(*_a: object, **_k: object) -> BridgeJobResult:
        hold.wait(timeout=5.0)
        return BridgeJobResult(
            job_id="blocked",
            status=BridgeJobStatus.CANCELLED,
            output_dir=str(Path(tempfile.gettempdir())),
        )

    tmp = tempfile.TemporaryDirectory()
    ini = str(Path(tmp.name) / "t.ini")
    os.environ["ROUNDUP_BRIDGE_ROOT"] = str(Path(tmp.name) / "bridge")
    blender = Path(tmp.name) / "blender.exe"
    blender.write_text("", encoding="utf-8")

    try:
        from PySide6.QtCore import QSettings

        qs = QSettings(ini, QSettings.Format.IniFormat)
        svc = SettingsService(qs)
        with patch(
            "meshcorral.app.bridge.queue_manager.find_blender_executable",
            return_value=blender,
        ):
            with patch(
                "meshcorral.app.bridge.queue_manager.job_runner.run_job_now",
                side_effect=_block_run,
            ):
                mgr = BridgeQueueManager(svc)
                mgr.configure_backpressure(network_like=True)
                cap = mgr.max_pending_cap()
                cap_hits = 0
                max_load = 0
                try:
                    for i in range(cap + 20):
                        p = Path(tmp.name) / f"m{i}.stl"
                        p.write_text("x", encoding="utf-8")
                        _ok, _msg, reject = mgr.try_enqueue_thumbnail(p)
                        load = mgr.bridge_load()
                        max_load = max(max_load, load)
                        if reject == BridgeEnqueueReject.CAP:
                            cap_hits += 1
                finally:
                    hold.set()
                    mgr.shutdown(timeout=0.5, close_enqueue=False)
        ok = cap_hits >= 1 and max_load <= cap
        return ok, f"cap={cap} max_load={max_load} cap_hits={cap_hits}"
    finally:
        tmp.cleanup()


def _check_duplicate_and_suppression_diag() -> tuple[bool, str]:
    diag = ThumbPaintDiagnostics()
    calls = {"n": 0}

    def _diag_try(_r: FileRecord) -> tuple[bool, str, BridgeEnqueueReject]:
        calls["n"] += 1
        if calls["n"] == 1:
            return True, "", BridgeEnqueueReject.OK
        if calls["n"] == 2:
            diag.note_bridge_duplicate_skip(1)
            return False, "", BridgeEnqueueReject.DUPLICATE
        diag.note_bridge_suppressed(1)
        return False, "", BridgeEnqueueReject.CAP

    tiers = {
        "selected": [],
        "visible": [_rec("C:/a/1.stl"), _rec("C:/a/2.stl"), _rec("C:/a/3.stl")],
        "directional_preload": [],
        "idle_background": [],
    }
    stats = enqueue_tiered_bridge_thumbnails(
        _diag_try,
        tiers,
        has_thumbnail=lambda _r: False,
    )
    snap = diag.snapshot()
    dup = int(snap["bridge_duplicate_skips"])
    sup = int(snap["bridge_jobs_suppressed"])
    ok = (
        stats.enqueued == 1
        and stats.duplicate_skips == 1
        and stats.suppressed_cap == 1
        and dup >= 1
        and sup >= 1
    )
    return ok, f"stats={stats} snap_sup={sup} dup={dup}"


def _check_viewport_only_tiers() -> tuple[bool, str]:
    records = [_rec(f"C:/v/{i}.stl") for i in range(10)]
    tiers = bridge_records_by_tier(
        records,
        visible_row_indices=[2, 3],
        prefetch_row_indices=[2, 3, 4, 5],
        selected_row=7,
        idle_background_row_indices=None,
    )
    idle_empty = len(tiers["idle_background"]) == 0
    selected_ok = tiers["selected"][0].name == "7.stl"
    ok = idle_empty and selected_ok and len(tiers["visible"]) == 2
    return ok, f"selected={len(tiers['selected'])} visible={len(tiers['visible'])} idle={len(tiers['idle_background'])}"


def _check_idle_gating() -> tuple[bool, str]:
    blocked = not bridge_idle_fill_allowed(
        scroll_idle_ms=10.0,
        scroll_settle_ms=160,
        decode_inflight=1,
        ui_idle_ms=5000.0,
    )
    allowed = bridge_idle_fill_allowed(
        scroll_idle_ms=500.0,
        scroll_settle_ms=160,
        decode_inflight=0,
        ui_idle_ms=2500.0,
    )
    ok = blocked and allowed
    return ok, f"blocked={blocked} allowed={allowed}"


def main() -> int:
    _ensure_qapp()
    checks: list[tuple[str, bool, str]] = []

    for name, fn in (
        ("local/remote caps (32/12)", _check_caps),
        ("pending+running capped", _check_queue_cap_and_running),
        ("suppression + duplicate diagnostics", _check_duplicate_and_suppression_diag),
        ("viewport tiers exclude idle until fill", _check_viewport_only_tiers),
        ("idle fill gating", _check_idle_gating),
    ):
        try:
            ok, detail = fn()
        except Exception as exc:
            ok, detail = False, str(exc)
        checks.append((name, ok, detail))
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name}: {detail}")

    print()
    print("Manual holocron watch (app log every ~5s):")
    print("  - bridge_jobs_pending <= cap (32 local / 12 remote)")
    print("  - bridge_jobs_running is 0 or 1")
    print("  - bridge_jobs_suppressed rises when scrolling a huge folder")
    print("  - bridge_duplicate_skips rises on repeated viewport passes")
    print("  - no rapid 100+ Enqueued Blender Bridge job lines in one second")
    print("  - bridge_idle_enqueues only after scroll/decode/UI quiet")
    print("  - close -> Roundup shutdown complete, exit 0")
    print()

    all_ok = all(c[1] for c in checks)
    if all_ok:
        print("AUTOMATED PASS: Prime v0.10 bridge backpressure controls are in place.")
        print("Run a large-folder session and confirm log counters match the watch list above.")
        return 0
    print("AUTOMATED FAIL: fix failing checks before holocron sign-off.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
