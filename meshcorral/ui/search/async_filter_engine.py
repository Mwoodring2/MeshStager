"""Debounced async filtering for large working sets."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot, QMetaObject, Qt, Q_ARG

from meshcorral.models.file_record import FileRecord
from meshcorral.models.thumb_health import ThumbHealth
from meshcorral.services.metadata.metadata_summary_registry import MetadataSummaryRegistry
from meshcorral.services.search_service import filter_records
from meshcorral.ui.search.query_parser import parse_query
from meshcorral.ui.search.search_index import SearchIndex
from meshcorral.utils.qt_object_safety import is_qobject_alive

logger = logging.getLogger(__name__)

ASYNC_FILTER_THRESHOLD = 400


@dataclass(frozen=True, slots=True)
class FilterRunResult:
    """Outcome of one filter pass (sync or async)."""

    epoch: int
    records: list[FileRecord]
    match_count: int
    pending: bool = False
    cancelled: bool = False


def compute_filtered_records(
    all_records: list[FileRecord],
    *,
    query_text: str,
    search_index: SearchIndex,
    extension_filter: str = "All",
    folder_filter: str = "All Folders",
    category_filter: str = "All",
    asset_mode: str | None = None,
    thumb_health_filter: str = "All",
    thumb_health_for: Callable[[FileRecord], ThumbHealth] | None = None,
    metadata_registry: MetadataSummaryRegistry | None = None,
    user_tags_for: Callable[[FileRecord], tuple[str, ...]] | None = None,
    favorite_filter: str | None = None,
    is_favorite_for: Callable[[FileRecord], bool] | None = None,
    collection_filter: Callable[[FileRecord], bool] | None = None,
    housekeeping_filter: Callable[[FileRecord], bool] | None = None,
    collections_for: Callable[[FileRecord], tuple[str, ...]] | None = None,
) -> list[FileRecord]:
    """
    Apply combo filters (extension, folder, category, asset mode, thumb health)
    then structured/plain query matching via *search_index*.
    """
    from meshcorral.services.favorites.favorite_filter import FAVORITE_FILTER_ALL

    combo = filter_records(
        all_records,
        search_text="",
        extension_filter=extension_filter,
        folder_filter=folder_filter,
        category_filter=category_filter,
        asset_mode=asset_mode,
        thumb_health_filter=thumb_health_filter,
        thumb_health_for=thumb_health_for,
        favorite_filter=favorite_filter or FAVORITE_FILTER_ALL,
        is_favorite_for=is_favorite_for,
        collection_filter=collection_filter,
        housekeeping_filter=housekeeping_filter,
    )
    parsed = parse_query(query_text)
    if parsed.is_empty():
        return combo
    search_index.rebuild_if_stale(all_records, user_tags_for=user_tags_for, collections_for=collections_for)
    return search_index.filter_records(
        combo,
        parsed,
        metadata_registry,
        user_tags_for=user_tags_for,
        collections_for=collections_for,
    )


class _FilterRunnable(QRunnable):
    """Background filter pass; drops result when epoch is stale."""

    def __init__(
        self,
        engine: AsyncFilterEngine,
        epoch: int,
        snapshot: list[FileRecord],
        kwargs: dict[str, object],
        query_text: str,
        index: SearchIndex,
        active_epoch_fn: Callable[[], int],
        metadata_registry: MetadataSummaryRegistry | None,
        user_tags_for: Callable[[FileRecord], tuple[str, ...]] | None,
    ) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._engine = engine
        self._epoch = epoch
        self._snapshot = snapshot
        self._kwargs = kwargs
        self._query_text = query_text
        # Collection providers capture a generation. Do not let overlapping
        # requests overwrite each other's mutable index with different snapshots.
        self._index = SearchIndex() if "collections_for" in kwargs else index
        self._active_epoch_fn = active_epoch_fn
        self._metadata_registry = metadata_registry
        self._user_tags_for = user_tags_for

    @Slot()
    def run(self) -> None:
        if not is_qobject_alive(self._engine):
            logger.debug("search filter cancelled (engine torn down before epoch %s)", self._epoch)
            return
        if self._active_epoch_fn() != self._epoch:
            logger.debug("search filter cancelled (epoch %s stale at start)", self._epoch)
            return
        try:
            records = compute_filtered_records(
                self._snapshot,
                query_text=self._query_text,
                search_index=self._index,
                metadata_registry=self._metadata_registry,
                user_tags_for=self._user_tags_for,
                **self._kwargs,  # type: ignore[arg-type]
            )
        except Exception:
            logger.exception("async search filter failed for epoch %s", self._epoch)
            return
        if self._active_epoch_fn() != self._epoch:
            logger.debug("search filter cancelled (epoch %s stale at end)", self._epoch)
            return
        if not is_qobject_alive(self._engine):
            logger.debug("search filter cancelled (engine torn down during epoch %s)", self._epoch)
            return
        self._engine._stash_worker_result(
            FilterRunResult(
                epoch=self._epoch,
                records=records,
                match_count=len(records),
            )
        )
        try:
            QMetaObject.invokeMethod(
                self._engine,
                "_deliver_worker_result",
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(int, self._epoch),
            )
        except RuntimeError as exc:
            logger.debug("search filter delivery cancelled during teardown: %s", exc)


class AsyncFilterEngine(QObject):
    """
    Debounced-friendly filter runner with epoch cancellation.

    Small working sets run synchronously on the caller thread; larger sets use
    :class:`QThreadPool` and deliver results via :meth:`results_ready`.
    """

    results_ready = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._epoch = 0
        self._pool = QThreadPool.globalInstance()
        self._search_index = SearchIndex()
        self._pending_runnable: _FilterRunnable | None = None
        self._worker_result: FilterRunResult | None = None

    @property
    def search_index(self) -> SearchIndex:
        """Index rebuilt with the working set during filter passes."""
        return self._search_index

    def current_epoch(self) -> int:
        """Latest request epoch (stale results have a lower value)."""
        return self._epoch

    def _stash_worker_result(self, result: FilterRunResult) -> None:
        """Written on worker thread; consumed on main via :meth:`_deliver_worker_result`."""
        self._worker_result = result

    def request_filter(
        self,
        all_records: list[FileRecord],
        combo_kwargs: dict[str, object],
        query_text: str,
        *,
        force_sync: bool = False,
        metadata_registry: MetadataSummaryRegistry | None = None,
        user_tags_for: Callable[[FileRecord], tuple[str, ...]] | None = None,
    ) -> FilterRunResult:
        """
        Start or run immediately a filter pass.

        Returns a sync :class:`FilterRunResult` when the set is small or
        *force_sync* is true; otherwise bumps epoch and queues background work
        (caller should wait for :meth:`results_ready`).
        """
        self._epoch += 1
        epoch = self._epoch
        use_async = (
            not force_sync
            and len(all_records) >= ASYNC_FILTER_THRESHOLD
            and bool((query_text or "").strip())
        )

        if not use_async:
            records = compute_filtered_records(
                all_records,
                query_text=query_text,
                search_index=self._search_index,
                metadata_registry=metadata_registry,
                user_tags_for=user_tags_for,
                **combo_kwargs,  # type: ignore[arg-type]
            )
            return FilterRunResult(
                epoch=epoch,
                records=records,
                match_count=len(records),
                pending=False,
            )

        snapshot = list(all_records)
        runnable = _FilterRunnable(
            self,
            epoch,
            snapshot,
            combo_kwargs,
            query_text,
            self._search_index,
            self.current_epoch,
            metadata_registry,
            user_tags_for,
        )
        self._pending_runnable = runnable
        self._pool.start(runnable)
        return FilterRunResult(
            epoch=epoch,
            records=[],
            match_count=0,
            pending=True,
            cancelled=False,
        )

    @Slot(int)
    def _deliver_worker_result(self, epoch: int) -> None:
        """Main-thread delivery slot for background filter results."""
        result = self._worker_result
        self._worker_result = None
        if result is None:
            return
        self._on_runnable_finished(epoch, result)

    @Slot(int, object)
    def _on_runnable_finished(self, epoch: int, result: object) -> None:
        if not isinstance(result, FilterRunResult):
            return
        if epoch != self._epoch:
            logger.debug("search filter dropped stale epoch %s (current %s)", epoch, self._epoch)
            return
        self.results_ready.emit(result)
