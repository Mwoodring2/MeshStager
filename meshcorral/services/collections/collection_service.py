"""Validated collection operations and immutable search snapshots."""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterable, Mapping
from pathlib import Path
from types import MappingProxyType

from meshcorral.services.collections.collection_repository import (
    Collection, CollectionRepository,
)

logger = logging.getLogger(__name__)


class CollectionError(ValueError):
    """A safe, user-facing collection failure."""


class CollectionService:
    """Owned and closed by the UI; no worker threads or filesystem mutation."""

    def __init__(self, repository: CollectionRepository | None = None) -> None:
        self._repo = repository or CollectionRepository()

    def close(self) -> None:
        self._repo.close()

    def _call(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except sqlite3.IntegrityError as exc:
            if getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_CONSTRAINT_UNIQUE:
                raise CollectionError("A collection with this name already exists.") from exc
            logger.warning("Collection constraint failure: %s", exc)
            raise CollectionError("The collection change could not be saved. Please try again.") from exc
        except (sqlite3.Error, OSError) as exc:
            logger.warning("Collection storage unavailable: %s", exc)
            raise CollectionError("Collections could not be saved or loaded. Please try again.") from exc
        except ValueError as exc:
            raise CollectionError(str(exc)) from exc

    def create_collection(self, name: str) -> Collection:
        return self._call(self._repo.create_collection, name)

    def rename_collection(self, collection_id: int, name: str) -> Collection:
        return self._call(self._repo.rename_collection, collection_id, name)

    def delete_collection(self, collection_id: int) -> bool:
        return self._call(self._repo.delete_collection, collection_id)

    def list_collections(self) -> list[Collection]:
        return self._call(self._repo.list_collections)

    def get_collection(self, collection_id: int) -> Collection:
        return self._call(self._repo.get_collection, collection_id)

    def add_assets(self, collection_id: int, paths: Iterable[Path | str]) -> int:
        return self._call(self._repo.change_members, collection_id, paths, add=True)

    def remove_assets(self, collection_id: int, paths: Iterable[Path | str]) -> int:
        return self._call(self._repo.change_members, collection_id, paths, add=False)

    def get_members(self, collection_id: int) -> frozenset[str]:
        return self._call(self._repo.get_members, collection_id)

    def get_collections_for_asset(self, path: Path | str) -> list[Collection]:
        return self._call(self._repo.get_collections_for_asset, path)

    def membership_snapshot(self) -> Mapping[str, frozenset[int]]:
        members: dict[str, set[int]] = {}
        for collection_id, path in self._call(self._repo.membership_rows):
            members.setdefault(path, set()).add(collection_id)
        return MappingProxyType({path: frozenset(ids) for path, ids in members.items()})
