"""Scan a folder for files whose extensions match the v1 default set."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable, Iterator

from meshcorral.services.scan_cancel import ScanCancelToken
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from meshcorral.ui.scan_timing_profiler import ScanTimingSession

from meshcorral.app.config import ALL_SUPPORTED_EXTENSIONS
from meshcorral.models.file_record import FileRecord
from meshcorral.services.archive_manifest_cache import ArchiveManifestCache
from meshcorral.services.metadata_cache import CachedAssetMetadata, MetadataCache
from meshcorral.services.scan_cache_diagnostics import ScanCacheDiagnostics
from meshcorral.utils.scan_ignores import IGNORED_DIRNAMES, is_ignored_file, is_ignored_path
from meshcorral.utils.validators import require_existing_directory

logger = logging.getLogger(__name__)


def scan_folder_sort_key(record: FileRecord) -> str:
    """Stable ordering for scanned rows (filesystem walk order undefined)."""

    return str(record.path).lower()


def _hydrate_from_cache(
    path: Path,
    suffix: str,
    cached: CachedAssetMetadata,
    *,
    network_optimistic: bool,
) -> FileRecord | None:
    """Build a :class:`FileRecord` from a cache row when hydration is allowed."""
    if not cached.is_usable_for_hydrate(network_optimistic=network_optimistic):
        return None
    return FileRecord(
        path=path,
        name=path.name,
        extension=suffix,
        parent_folder=path.parent.name,
        size_bytes=cached.size_bytes,
        modified_time=cached.modified_time,
        metadata_source="cache",
    )


def _maybe_index_archive(
    path: Path,
    archive_cache: ArchiveManifestCache | None,
    diagnostics: ScanCacheDiagnostics | None,
) -> None:
    """Index ``.zip`` manifests when an archive cache is provided (v0.8)."""
    if archive_cache is None or not ArchiveManifestCache.is_supported_archive(path):
        return
    result = archive_cache.ensure_indexed(path)
    if diagnostics is None:
        return
    if result is None:
        diagnostics.note_archive_index(reused=False, rebuilt=False, failed=True)
    else:
        diagnostics.note_archive_index(
            reused=result.reused_cache,
            rebuilt=result.rebuilt,
            failed=False,
        )


def iter_scan_file_records(
    folder: str | Path,
    recursive: bool = True,
    allowed_extensions: set[str] | frozenset[str] | None = None,
    *,
    after_dir_scanned: Callable[[int, Path], None] | None = None,
    lightweight: bool = False,
    metadata_cache: MetadataCache | None = None,
    source_root: str | None = None,
    network_optimistic: bool = False,
    archive_manifest_cache: ArchiveManifestCache | None = None,
    scan_cache_diagnostics: ScanCacheDiagnostics | None = None,
    cancel_token: ScanCancelToken | None = None,
    scan_timing: "ScanTimingSession | None" = None,
    strict_errors: bool = False,
) -> Iterator[FileRecord]:
    """Yield matching :class:`~meshcorral.models.file_record.FileRecord` entries while walking disk.

    Semantics match :func:`scan_folder` except results are streamed in walk order.

    ``after_dir_scanned`` is invoked after each scanned directory with the number of records
    yielded so far (including prior directories) and the directory path being left.

    When *lightweight* is True (Prime Performance v0.7 metadata-first virtualization),
    ``size_bytes`` and ``modified_time`` are left as ``None`` and ``path.stat()`` is not
    invoked. The non-recursive branch uses :func:`os.scandir` to avoid an extra
    ``Path.is_file()`` round trip per child.
    """
    root = Path(folder)
    require_existing_directory(root, "Scan folder")

    allow: set[str] | frozenset[str] = (
        allowed_extensions if allowed_extensions is not None else ALL_SUPPORTED_EXTENSIONS
    )

    yielded = 0

    def canceled() -> bool:
        return cancel_token is not None and cancel_token.is_canceled()

    def notify_dir_finished(dir_base: Path) -> None:
        """Report progress after finishing one directory."""

        if scan_timing is not None:
            scan_timing.current_folder = str(dir_base)
        if after_dir_scanned is not None:
            after_dir_scanned(yielded, dir_base)

    def record_for_path(path: Path) -> FileRecord | None:
        """Build a record for *path*, or skip on ignore / permission / extension rules."""
        nonlocal yielded

        from meshcorral.ui.scan_timing_profiler import timed_scan_item

        with timed_scan_item(scan_timing, kind="file", path=str(path)):
            if is_ignored_file(path) or is_ignored_path(path):
                return None

            suffix = path.suffix.lower().strip()
            if scan_timing is not None:
                scan_timing.set_current_extension(suffix)
            if not suffix or suffix not in allow:
                return None

            size_bytes: int | None = None
            modified_time: float | None = None
            metadata_source: str | None = None

            if lightweight and metadata_cache is not None:
                cached = metadata_cache.get(path)
                if cached is not None:
                    hydrated = _hydrate_from_cache(
                        path,
                        suffix,
                        cached,
                        network_optimistic=network_optimistic,
                    )
                    if hydrated is not None:
                        yielded += 1
                        if scan_cache_diagnostics is not None:
                            scan_cache_diagnostics.note_record(from_cache=True)
                        metadata_cache.upsert(
                            path=path,
                            ext=suffix,
                            size_bytes=hydrated.size_bytes,
                            modified_time=hydrated.modified_time,
                            file_exists=True,
                            source_root=source_root or "",
                        )
                        return hydrated
                    if scan_cache_diagnostics is not None:
                        scan_cache_diagnostics.note_record(from_cache=False)
                elif scan_cache_diagnostics is not None:
                    scan_cache_diagnostics.note_record(from_cache=False)
            elif not lightweight:
                try:
                    stat = path.stat()
                except OSError:
                    if strict_errors:
                        raise
                    return None
                size_bytes = int(stat.st_size)
                modified_time = float(stat.st_mtime)
                metadata_source = "stat"
                if metadata_cache is not None:
                    metadata_cache.upsert(
                        path=path,
                        ext=suffix,
                        size_bytes=size_bytes,
                        modified_time=modified_time,
                        file_exists=True,
                        source_root=source_root or "",
                        enriched=True,
                    )
                if scan_cache_diagnostics is not None:
                    scan_cache_diagnostics.note_record(from_cache=False)
            else:
                if scan_cache_diagnostics is not None:
                    scan_cache_diagnostics.note_record(from_cache=False)

            yielded += 1

            return FileRecord(
                path=path,
                name=path.name,
                extension=suffix,
                parent_folder=path.parent.name,
                size_bytes=size_bytes,
                modified_time=modified_time,
                metadata_source=metadata_source,
            )

    def traversal_error(error: OSError) -> None:
        if strict_errors:
            raise error

    if recursive:
        try:
            for dirpath, dirnames, filenames in os.walk(root, followlinks=False, onerror=traversal_error):
                if canceled():
                    return
                dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRNAMES]
                base = Path(dirpath)
                if scan_timing is not None:
                    scan_timing.current_folder = dirpath
                for name in filenames:
                    if canceled():
                        return
                    path = base / name
                    from meshcorral.ui.scan_timing_profiler import timed_scan_item

                    with timed_scan_item(scan_timing, kind="archive_index", path=str(path)):
                        _maybe_index_archive(
                            path, archive_manifest_cache, scan_cache_diagnostics
                        )
                    if canceled():
                        return
                    rec = record_for_path(path)
                    if rec is None:
                        continue
                    if canceled():
                        return
                    yield rec
                notify_dir_finished(base)
        except OSError:
            if strict_errors:
                raise
            logger.debug("recursive scan stopped early under %s", root, exc_info=True)
    else:
        try:
            with os.scandir(root) as entries:
                for entry in entries:
                    if canceled():
                        return
                    try:
                        if not entry.is_file(follow_symlinks=False):
                            continue
                    except OSError:
                        if strict_errors:
                            raise
                        continue
                    entry_path = Path(entry.path)
                    _maybe_index_archive(
                        entry_path, archive_manifest_cache, scan_cache_diagnostics
                    )
                    if canceled():
                        return
                    rec = record_for_path(entry_path)
                    if rec is None:
                        continue
                    if canceled():
                        return
                    yield rec
            notify_dir_finished(root)
        except OSError:
            if strict_errors:
                raise
            logger.debug("non-recursive scan failed under %s", root, exc_info=True)


def scan_folder(
    folder: str | Path,
    recursive: bool = True,
    allowed_extensions: set[str] | frozenset[str] | None = None,
) -> list[FileRecord]:
    """Return lightweight records for files under ``folder`` with allowed extensions."""

    collected = list(
        iter_scan_file_records(
            folder,
            recursive=recursive,
            allowed_extensions=allowed_extensions,
        )
    )
    return sorted(collected, key=scan_folder_sort_key)
