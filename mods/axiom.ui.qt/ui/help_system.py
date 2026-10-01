"""
ui/help_system.py

Decoupled core shim for the in-app documentation & tooltip system.
When the 'axiom.help_system' mod is active, delegates to mods.axiom.help_system.ui.help_system.
When the mod is disabled or absent, all operations are completely detached (zero-overhead no-ops).
"""

from __future__ import annotations

from typing import Any

_MOD_ID = "axiom.help_system"


def is_help_system_enabled(config: Any = None) -> bool:
    """Return True if the axiom.help_system mod is enabled and loaded."""
    try:
        from axiom.kernel.loader import is_mod_enabled
        from axiom.config import load_config
        cfg = config if config is not None else load_config()
        if not is_mod_enabled(_MOD_ID, cfg):
            return False
        import mods.axiom.help_system.ui.help_system
        return True
    except Exception:
        return False


def _get_mod():
    import mods.axiom.help_system.ui.help_system as _impl
    return _impl


def doc(widget, ref: str):
    """Attach doc tooltip if axiom.help_system is enabled, otherwise return widget unchanged."""
    if not is_help_system_enabled():
        return widget
    return _get_mod().doc(widget, ref)


def doc_tab(tab_widget, index: int, ref: str) -> None:
    """Attach tab tooltip if axiom.help_system is enabled, otherwise no-op."""
    if not is_help_system_enabled():
        return
    _get_mod().doc_tab(tab_widget, index, ref)


def tooltips_enabled() -> bool:
    """Check if tooltips are enabled."""
    if not is_help_system_enabled():
        return False
    return _get_mod().tooltips_enabled()


def install_tooltip_gate(app) -> None:
    """Install tooltip gate if axiom.help_system is enabled."""
    global _tooltip_gate
    if not is_help_system_enabled():
        _tooltip_gate = None
        return
    mod = _get_mod()
    mod.install_tooltip_gate(app)
    _tooltip_gate = getattr(mod, "_tooltip_gate", None)


def uninstall_tooltip_gate(app=None) -> None:
    """Uninstall tooltip gate."""
    global _tooltip_gate
    try:
        if is_help_system_enabled():
            _get_mod().uninstall_tooltip_gate(app)
    except Exception:
        pass
    _tooltip_gate = None


_tooltip_gate = None


def retranslate_tooltips() -> None:
    """Retranslate tooltips across all live widgets."""
    if not is_help_system_enabled():
        return
    _get_mod().retranslate_tooltips()


def tooltip_html(ref: str) -> str:
    """Return HTML content for a doc reference."""
    if not is_help_system_enabled():
        return ""
    return _get_mod().tooltip_html(ref)


def audit_undocumented(root, skip: tuple = ()) -> list[str]:
    """Audit undocumented widgets under root."""
    if not is_help_system_enabled():
        return []
    return _get_mod().audit_undocumented(root, skip=skip)


def entry_keys(ref: str) -> tuple[str, str]:
    if is_help_system_enabled():
        return _get_mod().entry_keys(ref)
    page, element = ref.split(".", 1) if "." in ref else (ref, "")
    return f"doc_{page}_{element}_t", f"doc_{page}_{element}"


def page_keys(page: str) -> tuple[str, str]:
    if is_help_system_enabled():
        return _get_mod().page_keys(page)
    return f"doc_page_{page}_t", f"doc_page_{page}"


def tour_keys(step: str) -> tuple[str, str]:
    if is_help_system_enabled():
        return _get_mod().tour_keys(step)
    return f"doc_tour_{step}_t", f"doc_tour_{step}"


def details_key(ref: str) -> str:
    if is_help_system_enabled():
        return _get_mod().details_key(ref)
    page, element = ref.split(".", 1) if "." in ref else (ref, "")
    return f"doc_{page}_{element}_d"


def has_details(ref: str) -> bool:
    if is_help_system_enabled():
        return _get_mod().has_details(ref)
    return False


def all_doc_keys() -> list[str]:
    if is_help_system_enabled():
        return _get_mod().all_doc_keys()
    return []


def _is_doc_tooltip_target(obj) -> bool:
    if not is_help_system_enabled():
        return False
    return _get_mod()._is_doc_tooltip_target(obj)


def __getattr__(name: str) -> Any:
    if is_help_system_enabled():
        mod = _get_mod()
        if hasattr(mod, name):
            return getattr(mod, name)
    if name == "PAGES":
        return {}
    if name in ("STUDIO_TAB_PAGES", "SETTINGS_TAB_PAGES", "TOUR_STEPS", "DETAILS"):
        return ()
    if name == "SETTINGS_GENERAL_PAGE":
        return ("settings", ())
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
