"""axiom/time_system.py

Backward-compatible module proxy aliasing mods.axiom.time.time_system.
Canonical implementation is now in mods.axiom.time.time_system.
"""

from __future__ import annotations

import importlib
import sys

try:
    _impl = importlib.import_module("mods.axiom.time.time_system")
    sys.modules[__name__] = _impl
    globals().update({k: getattr(_impl, k) for k in dir(_impl) if not k.startswith("__")})
except Exception:
    _impl = None


def __getattr__(name: str):
    if _impl is not None and hasattr(_impl, name):
        return getattr(_impl, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
