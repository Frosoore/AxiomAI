"""ui/tabletop_view.py

Backward-compatible module proxy aliasing mods.axiom_ui_qt.ui.tabletop_view.
"""

from __future__ import annotations

import sys
import mods.axiom_ui_qt.ui.tabletop_view as _impl

sys.modules[__name__] = _impl
