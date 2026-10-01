"""axiom/stat_dynamics.py

Backward-compatible module proxy aliasing mods.core.stat_dynamics.stat_dynamics.
Canonical implementation is now in mods.core.stat_dynamics.stat_dynamics.
"""

from __future__ import annotations

import importlib
import sys

try:
    _impl = importlib.import_module("mods.core.stat_dynamics.stat_dynamics")
    sys.modules[__name__] = _impl
    globals().update({k: getattr(_impl, k) for k in dir(_impl) if not k.startswith("__")})
except Exception:
    _impl = None


def __getattr__(name: str):
    if _impl is not None and hasattr(_impl, name):
        return getattr(_impl, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
