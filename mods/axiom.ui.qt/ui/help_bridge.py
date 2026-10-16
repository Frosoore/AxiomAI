"""mods/axiom.ui.qt/ui/help_bridge.py

Safe bridge to axiom.help_system for the Qt UI.
Ensures axiom.ui.qt never crashes when axiom.help_system is uninstalled, deleted, or disabled.
"""
from __future__ import annotations

from typing import Any, Callable
from PySide6.QtWidgets import QPushButton, QDialog

try:
    from mods.axiom.help_system.ui import help_system as _hs
    from mods.axiom.help_system.ui import help_dialogs as _hd
    _HELP_MOD_PRESENT = True
except (ImportError, ModuleNotFoundError):
    _hs = None
    _hd = None
    _HELP_MOD_PRESENT = False

CREATOR_TAB_PAGES: tuple[str, ...] = (
    getattr(_hs, "CREATOR_TAB_PAGES", None)
    if _hs is not None else (
        "creator_meta",
        "creator_stats",
        "creator_entities",
        "creator_map",
        "creator_rules",
        "creator_events",
        "creator_setup",
        "creator_lore",
        "creator_populate",
        "creator_files",
    )
)


def is_help_system_available(config: Any = None) -> bool:
    if not _HELP_MOD_PRESENT or _hs is None:
        return False
    try:
        return bool(_hs.is_help_system_enabled(config))
    except Exception:
        return False


def doc(widget: Any, ref: str) -> Any:
    if _HELP_MOD_PRESENT and _hs is not None and is_help_system_available():
        try:
            return _hs.doc(widget, ref)
        except Exception:
            pass
    return widget


def doc_tab(tab_widget: Any, index: int, ref: str) -> None:
    if _HELP_MOD_PRESENT and _hs is not None and is_help_system_available():
        try:
            _hs.doc_tab(tab_widget, index, ref)
        except Exception:
            pass


def retranslate_tooltips() -> None:
    if _HELP_MOD_PRESENT and _hs is not None and is_help_system_available():
        try:
            _hs.retranslate_tooltips()
        except Exception:
            pass


def install_tooltip_gate(app: Any) -> None:
    if _HELP_MOD_PRESENT and _hs is not None and is_help_system_available():
        try:
            _hs.install_tooltip_gate(app)
        except Exception:
            pass


def make_help_button(page: str | Callable[[], str], parent: Any = None) -> QPushButton:
    if _HELP_MOD_PRESENT and _hd is not None and is_help_system_available():
        try:
            return _hd.make_help_button(page, parent)
        except Exception:
            pass
    btn = QPushButton(parent)
    btn.setVisible(False)
    return btn


def ExplainPageDialog(*args: Any, **kwargs: Any) -> Any:
    if _HELP_MOD_PRESENT and _hd is not None and is_help_system_available():
        try:
            return _hd.ExplainPageDialog(*args, **kwargs)
        except Exception:
            pass

    class _DummyDialog(QDialog):
        def exec(self) -> int:
            return 0

    parent = kwargs.get("parent") or (args[1] if len(args) > 1 else None)
    return _DummyDialog(parent)


def DocDirectoryDialog(*args: Any, **kwargs: Any) -> Any:
    if _HELP_MOD_PRESENT and _hd is not None and is_help_system_available():
        try:
            return _hd.DocDirectoryDialog(*args, **kwargs)
        except Exception:
            pass

    class _DummyDialog(QDialog):
        def exec(self) -> int:
            return 0

    parent = kwargs.get("parent") or (args[0] if len(args) > 0 else None)
    return _DummyDialog(parent)


def QuickTourDialog(*args: Any, **kwargs: Any) -> Any:
    if _HELP_MOD_PRESENT and _hd is not None and is_help_system_available():
        try:
            return _hd.QuickTourDialog(*args, **kwargs)
        except Exception:
            pass

    class _DummyDialog(QDialog):
        def exec(self) -> int:
            return 0

    parent = kwargs.get("parent") or (args[0] if len(args) > 0 else None)
    return _DummyDialog(parent)


def settings_tab_help_html(tab_index: int) -> tuple[str, str]:
    if _HELP_MOD_PRESENT and _hd is not None and is_help_system_available():
        try:
            return _hd.settings_tab_help_html(tab_index)
        except Exception:
            pass
    return "", ""
