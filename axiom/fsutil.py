"""axiom.fsutil — atomic filesystem swaps hardened for Windows.

On Windows, a file we have just finished writing can still be briefly held by
*another* process: Windows Defender real-time scanning, the Search indexer, or
a lingering memory-mapped SQLite ``-shm`` handle. The very next ``os.replace``
or ``unlink`` then fails with ``PermissionError`` — WinError 32, *"the process
cannot access the file because it is being used by another process"* — even
though all of our own handles are closed. These locks are transient: a short
bounded retry clears them.

This is exactly the symptom that crashed the Hub on first launch
(``universe.db.tmp -> universe.db``): the cache compiler wrote a fresh
``universe.db.tmp`` and Defender grabbed it for a scan a microsecond before the
rename.

On POSIX the very first attempt always succeeds, so these helpers add zero
overhead there.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

# Delays (seconds) between attempts. The first attempt is immediate; the rest
# back off up to ~1.5 s total — ample for an antivirus scan of a small universe
# db, while never freezing the UI indefinitely on a genuinely stuck file.
_RETRY_DELAYS: tuple[float, ...] = (0.0, 0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5)


def replace_with_retry(src, dst) -> None:
    """``os.replace(src, dst)``, retried on transient Windows sharing locks."""
    src_s, dst_s = os.fspath(src), os.fspath(dst)
    _retry(lambda: os.replace(src_s, dst_s))


def unlink_with_retry(path, missing_ok: bool = False) -> None:
    """``Path.unlink``, retried on transient Windows sharing locks."""
    p = Path(path)

    def _do() -> None:
        try:
            p.unlink()
        except FileNotFoundError:
            if not missing_ok:
                raise

    _retry(_do)


def _retry(op) -> None:
    """Run ``op`` retrying on ``PermissionError`` (WinError 32/5 sharing lock).

    ``FileNotFoundError`` is re-raised immediately (it is never a transient
    lock). Any other error escapes on the first try.
    """
    last: PermissionError | None = None
    for delay in _RETRY_DELAYS:
        if delay:
            time.sleep(delay)
        try:
            op()
            return
        except PermissionError as exc:  # ERROR_SHARING_VIOLATION / ACCESS_DENIED
            last = exc
    assert last is not None  # loop ran at least once
    raise last
