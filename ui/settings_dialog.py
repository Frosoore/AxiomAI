"""ui/settings_dialog.py

Backward-compatible module proxy aliasing mods.axiom_ui_qt.ui.settings_dialog.
"""

from __future__ import annotations

import sys
import mods.axiom_ui_qt.ui.settings_dialog as _impl

sys.modules[__name__] = _impl
