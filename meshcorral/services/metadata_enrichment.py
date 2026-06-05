"""Background stat enrichment for lightweight-scanned records (Prime Performance v0.7).

The scanner emits :class:`~meshcorral.models.file_record.FileRecord` rows with
``size_bytes`` and ``modified_time`` deferred. This module supplies a stateless
batched stat pump that the UI runs on a worker thread to fill them in incrementally
without blocking initial table population.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Defaults tuned for local SSD; remote callers pass smaller batches + longer sleeps.
DEFAULT_BATCH_SIZE: int = 64
DEFAULT_BATCH_PAUSE_S: float = 0.005


@dataclass(frozen=True, slots=True)
class MetadataUpdate:
    """Resolved stat metadata for a single scanned path."""

    path_key: str
    size_bytes: int | None
    modified_time: float | None


def stat_metadata_for(path: Path) -> tuple[int | None, float | None]:
    """
    Return ``(size_bytes, modified_time)`` for *path*, or ``(None, None)`` on failure.

    Performs exactly one ``Path.stat()``. Never raises.
    """
    try:
        st = path.stat()
    except OSError:
        return None, None
    return int(st.st_size), float(st.st_mtime)


def iter_metadata_batches(
    path_keys_and_paths: Sequence[tuple[str, Path]],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    batch_pause_s: float = DEFAULT_BATCH_PAUSE_S,
    is_cancelled: Callable[[], bool] | None = None,
) -> Iterable[list[MetadataUpdate]]:
    """
    Stat *path_keys_and_paths* in chunks and yield :class:`MetadataUpdate` lists.

    Sleeps *batch_pause_s* between chunks to keep network shares from saturating.
    *is_cancelled* (when provided) is polled per batch — stops generating cleanly.
    """
    if not path_keys_and_paths:
        return
    size = max(1, int(batch_size))
    pause = max(0.0, float(batch_pause_s))
    batch: list[MetadataUpdate] = []
    n = 0
    t0 = time.perf_counter()
    for key, path in path_keys_and_paths:
        if is_cancelled is not None and is_cancelled():
            break
        sz, mt = stat_metadata_for(path)
        batch.append(MetadataUpdate(path_key=str(key), size_bytes=sz, modified_time=mt))
        n += 1
        if len(batch) >= size:
            yield batch
            batch = []
            if pause > 0.0:
                time.sleep(pause)
    if batch:
        yield batch
    logger.debug(
        "metadata enrichment finished: %s paths in %.2fms", n, (time.perf_counter() - t0) * 1000.0
    )
