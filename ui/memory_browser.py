"""ui/memory_browser.py

Re-export shim for backwards compatibility.
Canonical implementation is now in mods/axiom.living_memory/ui/memory_browser.py.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

_target_path = Path(__file__).resolve().parent.parent / "mods" / "axiom.living_memory" / "ui" / "memory_browser.py"
_mod_name = "_axiom_living_memory_ui_browser"

if _mod_name not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_mod_name, _target_path)
    if _spec and _spec.loader:
        _module = importlib.util.module_from_spec(_spec)
        sys.modules[_mod_name] = _module
        _spec.loader.exec_module(_module)
    else:
        raise ImportError(f"Cannot load module from {_target_path}")
else:
    _module = sys.modules[_mod_name]

MemoryBrowserDialog = getattr(_module, "MemoryBrowserDialog")
_TextEditDialog = getattr(_module, "_TextEditDialog")
_table = getattr(_module, "_table")
_tune_columns = getattr(_module, "_tune_columns")
_selected_id = getattr(_module, "_selected_id")
_TREND_STYLE = getattr(_module, "_TREND_STYLE")
_ID_ROLE = getattr(_module, "_ID_ROLE")

__all__ = [
    "MemoryBrowserDialog",
    "_TextEditDialog",
    "_table",
    "_tune_columns",
    "_selected_id",
    "_TREND_STYLE",
    "_ID_ROLE",
]
