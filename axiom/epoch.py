"""
axiom/epoch.py

Session Epoch Management for Axiom AI concurrency safety.

Tracks epochs to invalidate stale asynchronous workers (such as living memory
distillation) when a rewind, save change, or fork occurs concurrently.
"""

from __future__ import annotations

import threading
from typing import Callable

from axiom.logger import logger


class SessionEpochManager:
    """Thread-safe manager for tracking session epochs."""

    def __init__(self, initial_epoch: int = 0) -> None:
        self._epoch = initial_epoch
        self._lock = threading.Lock()

    @property
    def current(self) -> int:
        with self._lock:
            return self._epoch

    def bump(self) -> int:
        """Atomically increment the epoch and return the new value."""
        with self._lock:
            self._epoch += 1
            return self._epoch

    def set_epoch(self, val: int) -> None:
        with self._lock:
            self._epoch = val

    def validate(self, captured_epoch: int) -> bool:
        """Return True if captured_epoch matches current epoch."""
        with self._lock:
            return self._epoch == captured_epoch


_SAVE_EPOCH_MANAGERS: dict[str, SessionEpochManager] = {}
_REGISTRY_LOCK = threading.Lock()


def get_session_epoch_manager(save_id: str) -> SessionEpochManager:
    """Get or create the SessionEpochManager for a given save_id."""
    with _REGISTRY_LOCK:
        if save_id not in _SAVE_EPOCH_MANAGERS:
            _SAVE_EPOCH_MANAGERS[save_id] = SessionEpochManager(0)
        return _SAVE_EPOCH_MANAGERS[save_id]


def reset_session_epoch_managers() -> None:
    """Clear registered epoch managers (primarily for testing)."""
    with _REGISTRY_LOCK:
        _SAVE_EPOCH_MANAGERS.clear()
