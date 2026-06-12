"""
ui/help_system.py

TICKET-057 — integrated in-app documentation: the central registry.

ONE declarative registry (PAGES) drives the four documentation features:
  1. tooltips on hover            -> doc() / doc_tab()
  2. "explain this page" dialog   -> ui/help_dialogs.ExplainPageDialog
  3. searchable doc directory     -> ui/help_dialogs.DocDirectoryDialog
  4. coverage tooling             -> tools/doc_check.py + tests

How to document a NEW element (extension workflow):
  1. add its id to PAGES below (one string in the right page tuple),
  2. call doc(widget, "page.element") where the widget is built
     (or doc_tab(tab_widget, index, "page.element") for a tab),
  3. add the two i18n keys to EVERY core/locales/<lang>.toml:
        doc_<page>_<element>_t = short title
        doc_<page>_<element>   = explanation (1-3 sentences)
Run `python tools/doc_check.py` to list anything missing.
"""

from __future__ import annotations

import weakref

from core.localization import tr
from axiom.logger import logger

# ---------------------------------------------------------------------------
# Registry — source of truth for everything documentable in the app.
# Order matters: it is the display order in the dialogs.
# ---------------------------------------------------------------------------

PAGES: dict[str, tuple[str, ...]] = {
    "hub": (
        "import_st",
        "import",
        "create",
        "card_play",
        "card_edit",
        "card_export",
        "card_delete",
    ),
    "setup": (
        "tab_saves",
        "saves_list",
        "import_save",
        "export_save",
        "duplicate_save",
        "rename_save",
        "edit_save",
        "delete_save",
        "tab_persona",
        "persona_list",
        "add_persona",
        "player_name",
        "difficulty",
        "tab_story",
        "launch",
        "back",
    ),
    "tabletop": (
        "turn_time",
        "player_selector",
        "verbosity",
        "canon_auto",
        "canonize",
        "rewind",
        "back",
        "sidebar_stats",
        "sidebar_inventory",
        "sidebar_timeline",
        "chat_log",
        "chat_input",
        "send",
        "mini_dico",
    ),
    "creator": (
        "save",
        "back",
        "tab_meta",
        "world_lore",
        "system_prompt",
        "first_message",
        "companion",
        "tension",
        "llm_temp",
        "llm_top_p",
        "verbosity",
        "tab_stats",
        "tab_entities",
        "tab_map",
        "tab_rules",
        "tab_events",
        "tab_setup",
        "tab_lore",
        "tab_populate",
        "tab_files",
    ),
    "settings": (
        "tab_llm",
        "base_url",
        "api_key",
        "main_model",
        "extraction_model",
        "time_model",
        "test_connection",
        "tab_cloud",
        "cloud_provider",
        "cloud_key",
        "cloud_model",
        "gemini_fallback",
        "llm_rpm",
        "tab_params",
        "llm_temp",
        "llm_top_p",
        "tab_personas",
        "tab_image",
        "image_enable",
        "image_backend",
        "image_url",
        "image_gemini_model",
        "image_size",
        "image_steps",
        "image_cfg",
        "image_timeout",
        "image_workflow",
        "language",
        "chronicler",
        "font_size",
        "rag_chunks",
        "audio",
        "timekeeper",
        "doc_tooltips",
    ),
    # Chrome of the main window itself (status bar etc.) — shown in the
    # directory, but has no dedicated "explain this page" button.
    "app": (
        "volume",
        "cancel_generation",
    ),
}

# Steps of the first-launch quick tour, in order.
TOUR_STEPS: tuple[str, ...] = (
    "welcome",
    "hub",
    "create",
    "setup",
    "tabletop",
    "settings",
    "help",
)


# ---------------------------------------------------------------------------
# Key derivation
# ---------------------------------------------------------------------------

def entry_keys(ref: str) -> tuple[str, str]:
    """i18n keys (title, body) of an element ref like 'hub.import'."""
    page, element = ref.split(".", 1)
    return f"doc_{page}_{element}_t", f"doc_{page}_{element}"


def page_keys(page: str) -> tuple[str, str]:
    """i18n keys (title, intro) of a page."""
    return f"doc_page_{page}_t", f"doc_page_{page}"


def tour_keys(step: str) -> tuple[str, str]:
    """i18n keys (title, body) of a quick-tour step."""
    return f"doc_tour_{step}_t", f"doc_tour_{step}"


def all_doc_keys() -> list[str]:
    """Every i18n key the registry requires (used by tools/doc_check.py)."""
    keys: list[str] = []
    for page, elements in PAGES.items():
        keys.extend(page_keys(page))
        for element in elements:
            keys.extend(entry_keys(f"{page}.{element}"))
    for step in TOUR_STEPS:
        keys.extend(tour_keys(step))
    return keys


def _is_known(ref: str) -> bool:
    page, _, element = ref.partition(".")
    return element in PAGES.get(page, ())


# ---------------------------------------------------------------------------
# Tooltip attachment (brique 1) + retranslation
# ---------------------------------------------------------------------------

# Live widgets carrying a doc tooltip (weak: widgets die with their view).
_live_widgets: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()
# Tab tooltips: (weakref to QTabWidget, tab index, ref).
_live_tabs: list[tuple[weakref.ref, int, str]] = []


def tooltip_html(ref: str) -> str:
    """Rich-text tooltip (bold title + body — rich text makes Qt word-wrap)."""
    title_key, body_key = entry_keys(ref)
    return f"<b>{tr(title_key)}</b><br/>{tr(body_key)}"


def doc(widget, ref: str):
    """Attach the documentation of `ref` ('page.element') to a widget.

    Sets its tooltip now and registers it so retranslate_tooltips() can
    refresh it on language change. Returns the widget (chainable).
    """
    if not _is_known(ref):
        logger.warning(f"help_system: unknown doc ref '{ref}' (add it to PAGES)")
    widget.setToolTip(tooltip_html(ref))
    _live_widgets[widget] = ref
    return widget


def doc_tab(tab_widget, index: int, ref: str) -> None:
    """Same as doc(), for one tab of a QTabWidget."""
    if not _is_known(ref):
        logger.warning(f"help_system: unknown doc ref '{ref}' (add it to PAGES)")
    tab_widget.setTabToolTip(index, tooltip_html(ref))
    _live_tabs.append((weakref.ref(tab_widget), index, ref))


def tooltips_enabled() -> bool:
    """User preference: show the doc tooltips on hover (settings toggle)."""
    try:
        from axiom.config import load_config
        return bool(load_config().doc_tooltips_enabled)
    except Exception:
        return True


def install_tooltip_gate(app) -> None:
    """App-level event filter muting doc tooltips when the user disabled them.

    The tooltips stay attached to the widgets (doc(), audits and the dialogs
    are untouched) — only their display on hover is suppressed, so the toggle
    takes effect immediately in both directions. Non-doc tooltips (e.g. the
    '?' help buttons) are not affected.
    """
    global _tooltip_gate
    if _tooltip_gate is not None:
        return

    from PySide6.QtCore import QEvent, QObject

    class _TooltipGate(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.ToolTip and not tooltips_enabled():
                return _is_doc_tooltip_target(obj)
            return False

    _tooltip_gate = _TooltipGate(app)
    app.installEventFilter(_tooltip_gate)


_tooltip_gate = None


def _is_doc_tooltip_target(obj) -> bool:
    """True if `obj` would show a doc tooltip (registered widget or tab bar)."""
    try:
        if obj in _live_widgets:
            return True
    except TypeError:  # non-hashable / non-widget event targets
        return False
    from PySide6.QtWidgets import QTabBar
    if isinstance(obj, QTabBar):
        parent = obj.parentWidget()
        return any(t() is parent for t, _, _ in _live_tabs)
    return False


def retranslate_tooltips() -> None:
    """Re-apply every registered tooltip in the current language."""
    for widget, ref in list(_live_widgets.items()):
        widget.setToolTip(tooltip_html(ref))
    alive: list[tuple[weakref.ref, int, str]] = []
    for tabs_ref, index, ref in _live_tabs:
        tabs = tabs_ref()
        if tabs is None:
            continue
        tabs.setTabToolTip(index, tooltip_html(ref))
        alive.append((tabs_ref, index, ref))
    _live_tabs[:] = alive


# ---------------------------------------------------------------------------
# Coverage audit (extension tooling, used by tools/doc_check.py and tests)
# ---------------------------------------------------------------------------

def audit_undocumented(root, skip: tuple = ()) -> list[str]:
    """List interactive widgets under `root` that carry no tooltip.

    `skip`: container widgets whose children are knowingly not yet
    documented (acknowledged debt — keep that list shrinking).
    Returns human-readable descriptions, empty list = full coverage.
    """
    from PySide6.QtWidgets import (
        QAbstractButton,
        QAbstractSpinBox,
        QComboBox,
        QDialogButtonBox,
        QLineEdit,
        QListWidget,
        QPlainTextEdit,
        QSlider,
        QTabBar,
        QTabWidget,
        QTextEdit,
        QWidget,
    )

    interactive = (
        QAbstractButton,
        QAbstractSpinBox,
        QComboBox,
        QLineEdit,
        QListWidget,
        QPlainTextEdit,
        QSlider,
        QTextEdit,
    )

    def _under(widget, ancestors) -> bool:
        parent = widget.parentWidget()
        while parent is not None:
            if parent in ancestors:
                return True
            parent = parent.parentWidget()
        return False

    def _inside_composite(widget) -> bool:
        # Internal children of composite inputs (the QLineEdit inside a
        # QComboBox/QSpinBox…) inherit the parent's tooltip behaviour.
        # QTabBar scroll arrows and standard QDialogButtonBox buttons are
        # Qt chrome, not app elements — out of the doc's scope.
        parent = widget.parentWidget()
        while parent is not None:
            if isinstance(parent, interactive + (QTabBar, QDialogButtonBox)):
                return True
            parent = parent.parentWidget()
        return False

    missing: list[str] = []
    for widget in root.findChildren(QWidget):
        if not isinstance(widget, interactive):
            continue
        if skip and _under(widget, skip):
            continue
        if _inside_composite(widget):
            continue
        if widget.toolTip():
            continue
        label = ""
        if hasattr(widget, "text"):
            try:
                label = widget.text()
            except TypeError:
                label = ""
        missing.append(f"{type(widget).__name__}({label or widget.objectName() or 'unnamed'})")

    tab_widgets = list(root.findChildren(QTabWidget))
    if isinstance(root, QTabWidget):
        tab_widgets.insert(0, root)
    for tabs in tab_widgets:
        if skip and (_under(tabs, skip) or tabs in skip):
            continue
        for i in range(tabs.count()):
            if not tabs.tabToolTip(i):
                missing.append(f"tab({tabs.tabText(i)})")
    return missing
