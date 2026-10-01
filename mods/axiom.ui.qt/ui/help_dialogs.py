"""
ui/help_dialogs.py

Decoupled core shim for the in-app documentation dialogs & button.
When the 'axiom.help_system' mod is active, delegates to mods.axiom.help_system.ui.help_dialogs.
When the mod is disabled or absent, all operations are completely detached.
"""

from __future__ import annotations

from typing import Any
from PySide6.QtWidgets import QDialog, QPushButton

_MOD_ID = "axiom.help_system"


def is_help_system_enabled(config: Any = None) -> bool:
    """Return True if the axiom.help_system mod is enabled and loaded."""
    try:
        from axiom.kernel.loader import is_mod_enabled
        from axiom.config import load_config
        cfg = config if config is not None else load_config()
        if not is_mod_enabled(_MOD_ID, cfg):
            return False
        import mods.axiom.help_system.ui.help_dialogs
        return True
    except Exception:
        return False


def _get_mod():
    import mods.axiom.help_system.ui.help_dialogs as _impl
    return _impl


def settings_tab_help_html(tab_index: int) -> tuple[str, str]:
    """(window title, HTML) explaining active settings tab."""
    if not is_help_system_enabled():
        return "", ""
    return _get_mod().settings_tab_help_html(tab_index)


def make_help_button(page, parent=None) -> QPushButton:
    """The 'Information' button placed in each page header.

    If axiom.help_system is disabled, returns an invisible, inert button
    so caller layouts do not fail, while detaching all functionality.
    """
    if not is_help_system_enabled():
        btn = QPushButton(parent)
        btn.setVisible(False)
        return btn
    return _get_mod().make_help_button(page, parent)


class ExplainPageDialog(QDialog):
    """'Explain this page' dialog for a single page."""

    def __new__(cls, *args, **kwargs):
        if is_help_system_enabled():
            mod = _get_mod()
            return mod.ExplainPageDialog(*args, **kwargs)
        return super().__new__(cls)

    def __init__(self, page: str, parent=None, *, html: str | None = None, title: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title or "Help")

    def exec(self) -> int:
        return 0


class DocDirectoryDialog(QDialog):
    """Searchable directory of the whole app."""

    def __new__(cls, *args, **kwargs):
        if is_help_system_enabled():
            mod = _get_mod()
            return mod.DocDirectoryDialog(*args, **kwargs)
        return super().__new__(cls)

    def __init__(self, parent=None, *, current_page: str = "hub") -> None:
        super().__init__(parent)

    def exec(self) -> int:
        return 0


class QuickTourDialog(QDialog):
    """Paged welcome tour."""

    def __new__(cls, *args, **kwargs):
        if is_help_system_enabled():
            mod = _get_mod()
            return mod.QuickTourDialog(*args, **kwargs)
        return super().__new__(cls)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

    def exec(self) -> int:
        return 0
