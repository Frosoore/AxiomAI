"""axiom/image_generator.py

Backward-compatible re-export shim for AI image generation.
Canonical implementation is now in mods.axiom.illustrations.image_generator.
"""

from __future__ import annotations

import importlib
import sys

try:
    _impl = importlib.import_module("mods.axiom.illustrations.image_generator")
    sys.modules[__name__] = _impl
    globals().update({k: getattr(_impl, k) for k in dir(_impl) if not k.startswith("__")})
except Exception:
    _impl = None


def __getattr__(name: str):
    if _impl is not None and hasattr(_impl, name):
        return getattr(_impl, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
