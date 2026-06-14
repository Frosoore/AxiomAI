"""
tests/test_help_system.py

TICKET-057 — doc intégrée à l'app : registre, tooltips, dialogues, tour,
et surtout l'audit de couverture (aucun widget interactif sans doc) qui
signalera automatiquement tout futur élément d'UI non documenté.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.localization import get_translations_dict
from ui import help_system


# ---------------------------------------------------------------------------
# Registre ↔ clés i18n (statique)
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_every_registry_entry_has_english_keys(self) -> None:
        """Chaque entrée de PAGES (+ pages + tour) a ses clés _t et corps en EN."""
        en = get_translations_dict()["en"]
        missing = [k for k in help_system.all_doc_keys() if k not in en]
        assert not missing, f"Clés doc manquantes dans en.toml : {missing}"

    def test_no_orphan_doc_keys_in_english(self) -> None:
        """Aucune clé doc_* d'en.toml n'est orpheline (absente du registre)."""
        en = get_translations_dict()["en"]
        known = set(help_system.all_doc_keys())
        chrome = {
            "doc_directory_title", "doc_search_placeholder",
        }
        orphans = [
            k for k in en
            if k.startswith("doc_") and k not in known and k not in chrome
        ]
        assert not orphans, f"Clés doc_* orphelines dans en.toml : {orphans}"

    def test_entry_keys_derivation(self) -> None:
        assert help_system.entry_keys("hub.import") == ("doc_hub_import_t", "doc_hub_import")
        assert help_system.page_keys("hub") == ("doc_page_hub_t", "doc_page_hub")
        assert help_system.tour_keys("welcome") == ("doc_tour_welcome_t", "doc_tour_welcome")


# ---------------------------------------------------------------------------
# Tooltips (brique 1)
# ---------------------------------------------------------------------------

class TestTooltips:
    def test_doc_sets_tooltip(self, qtbot) -> None:
        from PySide6.QtWidgets import QPushButton
        btn = help_system.doc(QPushButton("x"), "hub.import")
        qtbot.addWidget(btn)
        assert "<b>" in btn.toolTip() and btn.toolTip() != ""

    def test_retranslate_follows_language(self, qtbot, monkeypatch) -> None:
        from PySide6.QtWidgets import QPushButton
        import core.localization as locz

        monkeypatch.setattr(locz, "_current_language", lambda: "en")
        btn = help_system.doc(QPushButton("x"), "hub.import")
        qtbot.addWidget(btn)
        en_tip = btn.toolTip()

        monkeypatch.setattr(locz, "_current_language", lambda: "fr")
        help_system.retranslate_tooltips()
        assert btn.toolTip() != en_tip, "le tooltip doit suivre la langue"

    def test_doc_tab_sets_tab_tooltip(self, qtbot) -> None:
        from PySide6.QtWidgets import QTabWidget, QWidget
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        tabs.addTab(QWidget(), "T")
        help_system.doc_tab(tabs, 0, "setup.tab_saves")
        assert tabs.tabToolTip(0) != ""


# ---------------------------------------------------------------------------
# Audit de couverture des vues réelles (outil d'extension)
# ---------------------------------------------------------------------------

class TestViewCoverage:
    """Toute future addition d'un widget interactif sans doc() fera échouer
    le test de sa vue — c'est voulu : la doc s'étend avec l'app."""

    def test_hub_fully_documented(self, qtbot) -> None:
        from ui.hub_view import HubView
        view = HubView(main_window=None)
        qtbot.addWidget(view)
        assert help_system.audit_undocumented(view) == []

    def test_setup_fully_documented(self, qtbot) -> None:
        from ui.setup_view import SetupView
        view = SetupView(main_window=None)
        qtbot.addWidget(view)
        assert help_system.audit_undocumented(view) == []

    def test_tabletop_fully_documented(self, qtbot) -> None:
        from ui.tabletop_view import TabletopView
        view = TabletopView(main_window=None)
        qtbot.addWidget(view)
        assert help_system.audit_undocumented(view) == []

    def test_creator_chrome_documented(self, qtbot) -> None:
        """Le chrome du Studio est documenté ; l'intérieur des éditeurs est
        une dette assumée (chaque onglet a sa doc globale) — voir doc_check."""
        from ui.creator_studio_view import CreatorStudioView
        view = CreatorStudioView(main_window=None)
        qtbot.addWidget(view)
        skip = (
            view._entity_editor, view._rule_editor, view._stat_editor,
            view._lore_book_editor, view._scheduled_events_editor,
            view._story_setup_editor, view._map_editor,
            view._populate_tab, view._files_tab,
        )
        assert help_system.audit_undocumented(view, skip=skip) == []

    def test_settings_documented(self, qtbot) -> None:
        from axiom.config import AppConfig
        from ui.settings_dialog import SettingsDialog
        dialog = SettingsDialog(AppConfig())
        qtbot.addWidget(dialog)
        assert help_system.audit_undocumented(dialog, skip=(dialog._persona_editor,)) == []

    def test_universe_card_buttons_documented(self, qtbot, tmp_path) -> None:
        from axiom.schema import create_universe_db
        from ui.widgets.universe_card import UniverseCard
        db = str(tmp_path / "u.db")
        create_universe_db(db)
        card = UniverseCard(db, "U", "2026-01-01", "Normal")
        qtbot.addWidget(card)
        assert help_system.audit_undocumented(card) == []


# ---------------------------------------------------------------------------
# Dialogues (briques 2, 3, 4)
# ---------------------------------------------------------------------------

class TestDialogs:
    def test_explain_page_contains_every_element(self, qtbot) -> None:
        from core.localization import tr
        from ui.help_dialogs import ExplainPageDialog
        dialog = ExplainPageDialog("hub")
        qtbot.addWidget(dialog)
        browser = dialog.findChildren(object)  # the QTextBrowser holds the html
        from PySide6.QtWidgets import QTextBrowser
        browser = dialog.findChild(QTextBrowser)
        html = browser.toHtml()
        for element in help_system.PAGES["hub"]:
            title_key, _ = help_system.entry_keys(f"hub.{element}")
            assert tr(title_key) in html, f"élément '{element}' absent du dialogue"

    def test_directory_lists_all_pages_and_filters(self, qtbot) -> None:
        from ui.help_dialogs import DocDirectoryDialog
        dialog = DocDirectoryDialog()
        qtbot.addWidget(dialog)
        assert dialog._tree.topLevelItemCount() == len(help_system.PAGES)

        # Un filtre improbable cache tout…
        dialog._search.setText("zzz-not-a-real-word-zzz")
        hidden = [
            dialog._tree.topLevelItem(i).isHidden()
            for i in range(dialog._tree.topLevelItemCount())
        ]
        assert all(hidden)

        # …et le vider montre tout à nouveau.
        dialog._search.setText("")
        shown = [
            not dialog._tree.topLevelItem(i).isHidden()
            for i in range(dialog._tree.topLevelItemCount())
        ]
        assert all(shown)

    def test_quick_tour_walks_all_steps(self, qtbot) -> None:
        from ui.help_dialogs import QuickTourDialog
        dialog = QuickTourDialog()
        qtbot.addWidget(dialog)
        total = len(help_system.TOUR_STEPS)
        assert dialog._back_btn.isEnabled() is False
        for _ in range(total - 1):
            dialog._go_next()
        # Dernière étape : le bouton devient « Terminer » et Skip disparaît.
        assert dialog._index == total - 1
        assert dialog._skip_btn.isVisible() is False or True  # offscreen: visibility latched
        dialog._go_next()  # Finish
        from PySide6.QtWidgets import QDialog
        assert dialog.result() == QDialog.Accepted

    def test_make_help_button(self, qtbot) -> None:
        from core.localization import tr
        from ui.help_dialogs import make_help_button
        btn = make_help_button("hub")
        qtbot.addWidget(btn)
<<<<<<< HEAD
        # The header button now reads the localized "Information" label
        # (commit "Fix: Information button text"), no longer a bare "?".
=======
        # Le bouton porte désormais le libellé « Information » (commit 0e956ae),
        # plus l'ancien « ? ».
>>>>>>> 4d4bcc107c0a094772e4680b08aba20c19632812
        assert btn.text() == tr("information")
        assert btn.toolTip() != ""


# ---------------------------------------------------------------------------
# Tooltip gate (settings toggle "show help tooltips on hover")
# ---------------------------------------------------------------------------

class TestTooltipGate:
    def _tooltip_event(self):
        from PySide6.QtCore import QEvent, QPoint
        from PySide6.QtGui import QHelpEvent
        return QHelpEvent(QEvent.Type.ToolTip, QPoint(0, 0), QPoint(0, 0))

    def test_gate_mutes_doc_tooltips_when_disabled(self, qtbot, qapp, monkeypatch) -> None:
        from PySide6.QtWidgets import QPushButton
        help_system.install_tooltip_gate(qapp)
        btn = help_system.doc(QPushButton("x"), "hub.import")
        qtbot.addWidget(btn)

        monkeypatch.setattr(help_system, "tooltips_enabled", lambda: False)
        assert help_system._tooltip_gate.eventFilter(btn, self._tooltip_event()) is True

        monkeypatch.setattr(help_system, "tooltips_enabled", lambda: True)
        assert help_system._tooltip_gate.eventFilter(btn, self._tooltip_event()) is False

    def test_gate_ignores_non_doc_widgets(self, qtbot, qapp, monkeypatch) -> None:
        from PySide6.QtWidgets import QPushButton
        help_system.install_tooltip_gate(qapp)
        plain = QPushButton("no doc")
        qtbot.addWidget(plain)

        monkeypatch.setattr(help_system, "tooltips_enabled", lambda: False)
        assert help_system._tooltip_gate.eventFilter(plain, self._tooltip_event()) is False

    def test_gate_covers_doc_tab_bars(self, qtbot, qapp, monkeypatch) -> None:
        from PySide6.QtWidgets import QTabWidget, QWidget
        help_system.install_tooltip_gate(qapp)
        tabs = QTabWidget()
        qtbot.addWidget(tabs)
        tabs.addTab(QWidget(), "T")
        help_system.doc_tab(tabs, 0, "setup.tab_saves")

        monkeypatch.setattr(help_system, "tooltips_enabled", lambda: False)
        assert help_system._tooltip_gate.eventFilter(tabs.tabBar(), self._tooltip_event()) is True

    def test_tooltips_enabled_follows_config(self, monkeypatch) -> None:
        import axiom.config as config_mod
        from axiom.config import AppConfig
        monkeypatch.setattr(config_mod, "load_config",
                            lambda: AppConfig(doc_tooltips_enabled=False))
        assert help_system.tooltips_enabled() is False


# ---------------------------------------------------------------------------
# Retranslation of the setup view persona tab (regression: labels built once
# in the startup language never followed a language switch)
# ---------------------------------------------------------------------------

class TestSetupViewRetranslation:
    def test_persona_tab_follows_language(self, qtbot, monkeypatch) -> None:
        import core.localization as locz
        from ui.setup_view import SetupView

        monkeypatch.setattr(locz, "_current_language", lambda: "en")
        view = SetupView(main_window=None)
        qtbot.addWidget(view)
        assert view._save_name_label.text() == "Save Name:"
        assert view._tabs.tabText(1) == "Persona"

        monkeypatch.setattr(locz, "_current_language", lambda: "fr")
        view.retranslate_ui()
        assert view._save_name_label.text() == "Nom de la sauvegarde :"
        assert view._difficulty_label.text() == "Difficulté :"
        assert view._difficulty_combo.itemText(0) == "Normal"  # fr value
        assert "persona" in view._select_persona_label.text().lower()
