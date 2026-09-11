"""Teardown-safe helpers for emitting Qt signals from worker threads.

A ``QRunnable`` running on a :class:`~PySide6.QtCore.QThreadPool` can outlive the
``QObject`` that owns the signals it reports through: the pool drains with a bounded
wait during shutdown, and tests routinely let an owner be garbage collected while a
decode is in flight. When that happens PySide raises
``RuntimeError: Signal source has been deleted`` from inside ``emit()``.

That is ordinary cancellation, not a fault, so the worker should stop quietly instead
of letting a traceback escape onto a pool thread where nothing can handle it.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

try:  # pragma: no cover - exercised implicitly on every PySide6 install
    from shiboken6 import isValid as _shiboken_is_valid
except ImportError:  # pragma: no cover - non-PySide fallback
    def _shiboken_is_valid(_obj: object) -> bool:
        """Assume alive when shiboken is unavailable."""
        return True


def is_qobject_alive(obj: object | None) -> bool:
    """
    Return True when *obj*'s underlying C++ object still exists.

    ``None`` and already-destroyed wrappers both report ``False`` so callers can treat
    a dead signal target the same way they treat an explicit cancel request.
    """
    if obj is None:
        return False
    try:
        return bool(_shiboken_is_valid(obj))
    except (RuntimeError, TypeError):
        return False


def emit_if_alive(owner: object | None, signal_name: str, *args: Any) -> bool:
    """
    Emit ``owner.<signal_name>(*args)``; return False if the target is gone.

    Attribute lookup is inside the guard because resolving a bound signal on a deleted
    wrapper raises too. A ``False`` result means "delivery cancelled by teardown" and
    the caller should abandon the remaining work.
    """
    if not is_qobject_alive(owner):
        logger.debug("signal %s skipped: target already destroyed", signal_name)
        return False
    try:
        signal = getattr(owner, signal_name)
        signal.emit(*args)
    except (RuntimeError, AttributeError) as exc:
        logger.debug("signal %s skipped during teardown: %s", signal_name, exc)
        return False
    return True
