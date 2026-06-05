"""Move planning and execution service.

Safety principles:
- Always build a dry-run move plan first and show it to the user.
- Detect collisions (destination exists) and block those moves.
- Be explicit and predictable: default behavior is "move flat" into destination dir.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import NamedTuple

from meshcorral.models.move_plan import MovePlan
from meshcorral.utils.filesystem_errors import humanize_filesystem_error
from meshcorral.utils.path_utils import safe_resolve_path
from meshcorral.utils.validators import require_destination_baseline

log = logging.getLogger(__name__)


class PlanExecutionResult(NamedTuple):
    """Outcome of ``execute_move_plan`` or ``execute_copy_plan``.

    - ``success_count`` is how many files reached ``MOVED`` or ``COPIED``.
    - ``messages`` is one string per row, in the same order as ``items``.
    - ``items`` is the post-execution plan (use for UI updates and summaries).
    """

    success_count: int
    messages: list[str]
    items: list[MovePlan]


def _per_row_message(item: MovePlan) -> str:
    """Build a single-line description for ``PlanExecutionResult.messages``."""
    return f"{item.status} | {item.message} | {item.source_path} -> {item.destination_path}"


class MoveService:
    """Build and execute safe move plans."""

    STATUS_OK = "OK"
    STATUS_BLOCKED = "BLOCKED"
    STATUS_ERROR = "ERROR"
    STATUS_MOVED = "MOVED"
    STATUS_COPIED = "COPIED"

    def build_move_plan(
        self,
        sources: list[Path],
        destination_dir: Path,
        *,
        ready_message: str = "Ready to move.",
    ) -> list[MovePlan]:
        """Build a dry-run move plan.

        Rules:
        - Destination may be missing if its parent directory exists (created on execute).
        - Each move is flat: `destination_dir / source.name`.
        - If destination path exists, the item is BLOCKED (no silent overwrite).
        - If source missing/not a file, the item is ERROR.
        - Paths are normalized the same way for planning and execution.
        """
        dest_root = safe_resolve_path(Path(destination_dir))
        require_destination_baseline(dest_root, "Destination folder")

        # One row per path; same path selected twice would otherwise get duplicate
        # destination rows in a single plan.
        unique_sources = list(dict.fromkeys(safe_resolve_path(Path(p)) for p in sources))

        plan: list[MovePlan] = []
        # Destinations another selected file in this same plan will already use.
        dest_claimed: set[Path] = set()

        for src in unique_sources:
            dest = dest_root / src.name
            if not src.exists():
                plan.append(
                    MovePlan(
                        source_path=src,
                        destination_path=dest,
                        status=self.STATUS_ERROR,
                        message="Source does not exist.",
                    )
                )
                continue
            if not src.is_file():
                plan.append(
                    MovePlan(
                        source_path=src,
                        destination_path=dest,
                        status=self.STATUS_ERROR,
                        message="Source is not a file.",
                    )
                )
                continue
            # Must run before dest.exists() so a same-path move (source file already
            # under the destination dir) is not mislabeled as a name collision.
            try:
                same_file = src.resolve(strict=False) == dest.resolve(strict=False)
            except OSError:
                same_file = False
            if same_file:
                plan.append(
                    MovePlan(
                        source_path=src,
                        destination_path=dest,
                        status=self.STATUS_BLOCKED,
                        message="Source and destination are the same path.",
                    )
                )
                continue
            if dest in dest_claimed:
                plan.append(
                    MovePlan(
                        source_path=src,
                        destination_path=dest,
                        status=self.STATUS_BLOCKED,
                        message="Another selected file already uses this destination name.",
                    )
                )
                continue
            if dest.exists():
                plan.append(
                    MovePlan(
                        source_path=src,
                        destination_path=dest,
                        status=self.STATUS_BLOCKED,
                        message="Destination already exists (collision).",
                    )
                )
                continue

            plan.append(
                MovePlan(
                    source_path=src,
                    destination_path=dest,
                    status=self.STATUS_OK,
                    message=ready_message,
                )
            )
            dest_claimed.add(dest)
        return plan

    def _pre_execute_transfer_row(self, item: MovePlan) -> MovePlan | None:
        """Re-check same-path and collisions before touching the filesystem.

        Returns a replacement row if the transfer must be skipped, else ``None``.
        """
        try:
            src_r = safe_resolve_path(Path(item.source_path))
            dst_path = Path(item.destination_path)
            dst_r = safe_resolve_path(dst_path)
            if src_r == dst_r:
                return MovePlan(
                    source_path=item.source_path,
                    destination_path=item.destination_path,
                    status=self.STATUS_BLOCKED,
                    message="Source and destination are the same path.",
                )
            if dst_path.exists():
                return MovePlan(
                    source_path=item.source_path,
                    destination_path=item.destination_path,
                    status=self.STATUS_BLOCKED,
                    message="Destination already exists (collision).",
                )
        except OSError as exc:
            return MovePlan(
                source_path=item.source_path,
                destination_path=item.destination_path,
                status=self.STATUS_ERROR,
                message=humanize_filesystem_error(exc),
            )
        return None

    def execute_copy_plan(self, plan: list[MovePlan]) -> PlanExecutionResult:
        """Copy files for each OK item using the same destination paths as the plan.

        Only items with status OK are copied. Skipped items are returned unchanged
        in ``items`` with their preview-time statuses.
        """
        updated: list[MovePlan] = []
        for item in plan:
            if item.status != self.STATUS_OK:
                updated.append(item)
                continue

            blocked = self._pre_execute_transfer_row(item)
            if blocked is not None:
                updated.append(blocked)
                continue

            try:
                item.destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(item.source_path), str(item.destination_path))
                updated.append(
                    MovePlan(
                        source_path=item.source_path,
                        destination_path=item.destination_path,
                        status=self.STATUS_COPIED,
                        message="Copied successfully.",
                    )
                )
            except Exception as exc:
                log.exception("Copy failed for %s -> %s", item.source_path, item.destination_path)
                updated.append(
                    MovePlan(
                        source_path=item.source_path,
                        destination_path=item.destination_path,
                        status=self.STATUS_ERROR,
                        message=humanize_filesystem_error(exc),
                    )
                )
        return self._execution_result_copied(updated)

    def execute_move_plan(self, plan: list[MovePlan]) -> PlanExecutionResult:
        """Execute the provided plan and return updated statuses and summaries.

        Only items with status OK are attempted. All others are returned unchanged
        in ``items``.
        """
        updated: list[MovePlan] = []
        for item in plan:
            if item.status != self.STATUS_OK:
                updated.append(item)
                continue

            blocked = self._pre_execute_transfer_row(item)
            if blocked is not None:
                updated.append(blocked)
                continue

            try:
                item.destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item.source_path), str(item.destination_path))
                updated.append(
                    MovePlan(
                        source_path=item.source_path,
                        destination_path=item.destination_path,
                        status=self.STATUS_MOVED,
                        message="Moved successfully.",
                    )
                )
            except Exception as exc:
                log.exception("Move failed for %s -> %s", item.source_path, item.destination_path)
                updated.append(
                    MovePlan(
                        source_path=item.source_path,
                        destination_path=item.destination_path,
                        status=self.STATUS_ERROR,
                        message=humanize_filesystem_error(exc),
                    )
                )
        return self._execution_result_moved(updated)

    @staticmethod
    def _execution_result_moved(items: list[MovePlan]) -> PlanExecutionResult:
        success = sum(1 for p in items if p.status == MoveService.STATUS_MOVED)
        messages = [_per_row_message(p) for p in items]
        return PlanExecutionResult(success, messages, items)

    @staticmethod
    def _execution_result_copied(items: list[MovePlan]) -> PlanExecutionResult:
        success = sum(1 for p in items if p.status == MoveService.STATUS_COPIED)
        messages = [_per_row_message(p) for p in items]
        return PlanExecutionResult(success, messages, items)

