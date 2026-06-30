"""
ui/creator_studio_view.py

Creator Studio screen for Axiom AI.
Provides a spreadsheet-like interface for building universe content.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QShortcut, QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.entity_editor import EntityEditorWidget
from ui.widgets.lore_book_editor import LoreBookEditorWidget
from ui.widgets.rule_editor import RuleEditorWidget
from ui.widgets.stat_definition_editor import StatDefinitionEditorWidget
from ui.widgets.scheduled_events_editor import ScheduledEventsEditorWidget
from ui.widgets.story_setup_editor import StorySetupEditorWidget
from ui.widgets.populate_tab import PopulateTabWidget
from ui.widgets.map_editor import MapEditorWidget
from ui.widgets.universe_files_tab import UniverseFilesTabWidget
from workers.db_worker import DbWorker
from axiom.config import load_config
from core.localization import tr

if TYPE_CHECKING:
    from ui.main_window import MainWindow


def _meta_float(meta: dict, key: str, default: float) -> float:
    """Read a numeric Universe_Meta value, tolerating malformed content."""
    try:
        return float(meta.get(key, default))
    except (TypeError, ValueError):
        return default


class CreatorStudioView(QWidget):
    """The universe builder screen."""

    def __init__(self, main_window: "MainWindow", parent=None) -> None:
        super().__init__(parent)
        self._main_window = main_window
        self._db_path: str | None = None
        self._db_worker: DbWorker | None = None
        self._save_worker: DbWorker | None = None
        
        # Pending AI operations (Chain: Save -> AI Task)
        self._pending_ai_tasks: list[str] = []
        self._pending_ai_mode: str = "auto"
        self._pending_ai_text: str | None = None
        self._pending_ai_preview: bool = False  # TICKET-030

        self._setup_ui()
        self._setup_shortcuts()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        self._universe_label = QLabel(tr("creator_studio"))
        self._universe_label.setStyleSheet("font-size: 24px; font-weight: bold;")
        header.addWidget(self._universe_label)
        header.addStretch()

        from ui.help_system import doc, doc_tab
        from ui.help_dialogs import make_help_button

        self._save_btn = doc(QPushButton(f"{tr('save_changes')} (Ctrl+S)"), "creator.save")
        self._back_btn = doc(QPushButton(tr("hub")), "creator.back")
        header.addWidget(self._save_btn)
        header.addWidget(self._back_btn)
        # Tab-aware: the Information button explains the tab you're on, not the
        # whole Studio (Metadata, Stats, Rules… each have their own page).
        self._help_btn = make_help_button(self.current_doc_page, self)
        header.addWidget(self._help_btn)
        layout.addLayout(header)

        # Tabs
        self._tabs = QTabWidget()
        self._entity_editor = EntityEditorWidget()
        self._rule_editor = RuleEditorWidget()
        self._stat_editor = StatDefinitionEditorWidget()
        self._lore_book_editor = LoreBookEditorWidget()
        self._scheduled_events_editor = ScheduledEventsEditorWidget()
        self._story_setup_editor = StorySetupEditorWidget()
        self._map_editor = MapEditorWidget()
        self._populate_tab = PopulateTabWidget()
        self._files_tab = UniverseFilesTabWidget()

        self._tabs.addTab(self._build_lore_tab(), tr("tab_meta"))
        self._tabs.addTab(self._stat_editor, tr("stats"))
        self._tabs.addTab(self._entity_editor, tr("tab_entities"))
        self._tabs.addTab(self._map_editor, tr("tab_map"))
        self._tabs.addTab(self._rule_editor, tr("tab_rules"))
        self._tabs.addTab(self._scheduled_events_editor, tr("tab_events"))
        self._tabs.addTab(self._story_setup_editor, tr("tab_setup"))
        self._tabs.addTab(self._lore_book_editor, tr("tab_lore"))
        self._tabs.addTab(self._populate_tab, tr("populate"))
        self._tabs.addTab(self._files_tab, tr("tab_files"))  # TICKET-029
        for idx, ref in enumerate((
            "creator.tab_meta", "creator.tab_stats", "creator.tab_entities",
            "creator.tab_map", "creator.tab_rules", "creator.tab_events",
            "creator.tab_setup", "creator.tab_lore", "creator.tab_populate",
            "creator.tab_files",
        )):
            doc_tab(self._tabs, idx, ref)
        layout.addWidget(self._tabs)

        # Connections
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self._save_btn.clicked.connect(self._on_save_clicked)
        self._back_btn.clicked.connect(self._on_back_clicked)
        
        self._lore_book_editor.populate_requested.connect(self._on_populate_requested_single)
        self._populate_tab.populate_requested.connect(self._on_populate_requested)
        self._map_editor.populate_requested.connect(self._on_map_populate_requested)
        self._files_tab.file_saved.connect(self._on_source_file_saved)
        self._files_tab.convert_requested.connect(self._on_convert_requested)

    def _setup_shortcuts(self) -> None:
        self._save_shortcut = QShortcut(QKeySequence("Ctrl+S"), self)
        self._save_shortcut.activated.connect(self._on_save_clicked)
        
        # Tab Navigation (Ctrl+1 to Ctrl+7)
        for i in range(7):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{i+1}"), self)
            shortcut.activated.connect(lambda idx=i: self._tabs.setCurrentIndex(idx))

    def _build_lore_tab(self) -> QWidget:
        from ui.help_system import doc

        tab = QWidget()
        layout = QVBoxLayout(tab)

        self._lore_group = QGroupBox(tr("world_lore"))
        lore_layout = QVBoxLayout(self._lore_group)
        self._lore_edit = doc(QPlainTextEdit(), "creator_meta.world_lore")
        self._lore_edit.setPlaceholderText(tr("global_lore_placeholder"))
        lore_layout.addWidget(self._lore_edit)
        layout.addWidget(self._lore_group)

        self._desc_group = QGroupBox(tr("universe_description_title"))
        desc_layout = QVBoxLayout(self._desc_group)
        self._description_edit = doc(QPlainTextEdit(), "creator_meta.description")
        self._description_edit.setPlaceholderText(tr("universe_description_placeholder"))
        self._description_edit.setMaximumHeight(80)
        desc_layout.addWidget(self._description_edit)
        layout.addWidget(self._desc_group)

        self._prompt_group = QGroupBox(tr("sys_prompt_override"))
        prompt_layout = QVBoxLayout(self._prompt_group)
        self._system_prompt_edit = doc(QPlainTextEdit(), "creator_meta.system_prompt")
        self._system_prompt_edit.setPlaceholderText(tr("system_prompt_placeholder"))
        self._system_prompt_edit.setMinimumHeight(80)
        prompt_layout.addWidget(self._system_prompt_edit)
        layout.addWidget(self._prompt_group)

        self._first_msg_group = QGroupBox(tr("init_narrative"))
        first_msg_layout = QVBoxLayout(self._first_msg_group)
        self._first_message_edit = doc(QPlainTextEdit(), "creator_meta.first_message")
        self._first_message_edit.setPlaceholderText(tr("first_msg_placeholder"))
        self._first_message_edit.setMinimumHeight(80)
        first_msg_layout.addWidget(self._first_message_edit)
        layout.addWidget(self._first_msg_group)

        # B-3: per-character memory styles (one "Name: what they remember" per
        # line). Stored in Universe_Meta as belief_missions JSON; drives how the
        # living-memory consolidator forms beliefs for each character.
        self._belief_missions_group = QGroupBox(tr("belief_missions_title"))
        bm_layout = QVBoxLayout(self._belief_missions_group)
        self._belief_missions_edit = doc(QPlainTextEdit(), "creator_meta.belief_missions")
        self._belief_missions_edit.setPlaceholderText(tr("belief_missions_placeholder"))
        self._belief_missions_edit.setMinimumHeight(60)
        bm_layout.addWidget(self._belief_missions_edit)
        layout.addWidget(self._belief_missions_group)

        self._tension_group = QGroupBox(tr("world_tension_level"))
        tension_form = QFormLayout(self._tension_group)
        self._tension_spin = doc(QDoubleSpinBox(), "creator_meta.tension")
        self._tension_spin.setRange(0.0, 1.0)
        self._tension_spin.setSingleStep(0.05)
        self._tension_label_row = QLabel(f"{tr('tension')} (0.0-1.0):")
        tension_form.addRow(self._tension_label_row, self._tension_spin)

        self._temp_spin = doc(QDoubleSpinBox(), "creator_meta.llm_temp")
        self._temp_spin.setRange(0.0, 1.0)
        self._temp_spin.setSingleStep(0.05)
        self._temp_label_row = QLabel(tr("llm_temp"))
        tension_form.addRow(self._temp_label_row, self._temp_spin)

        self._top_p_spin = doc(QDoubleSpinBox(), "creator_meta.llm_top_p")
        self._top_p_spin.setRange(0.0, 1.0)
        self._top_p_spin.setSingleStep(0.05)
        self._top_p_label_row = QLabel(tr("llm_top_p"))
        tension_form.addRow(self._top_p_label_row, self._top_p_spin)

        from PySide6.QtWidgets import QComboBox, QCheckBox
        self._verbosity_combo = doc(QComboBox(), "creator_meta.verbosity")
        # TICKET-032 : la valeur CANONIQUE vit dans itemData, le texte affiché
        # n'est que la traduction (sinon « équilibré » finissait en base).
        for level in ("short", "balanced", "talkative"):
            self._verbosity_combo.addItem(tr(level), level)
        self._verbosity_label_row = QLabel(f"{tr('verbosity')}:")
        tension_form.addRow(self._verbosity_label_row, self._verbosity_combo)

        # Companion Mode Feature
        self._companion_group = QGroupBox(tr("companion_feature"))
        companion_layout = QFormLayout(self._companion_group)
        self._companion_enabled_check = doc(QCheckBox(tr("enable_companion_mode")), "creator_meta.companion")
        self._companion_hero_combo = doc(QComboBox(), "creator_meta.companion")
        companion_layout.addRow(self._companion_enabled_check)
        companion_layout.addRow(tr("main_hero"), self._companion_hero_combo)
        layout.addWidget(self._companion_group)

        layout.addWidget(self._tension_group)
        layout.addStretch()
        return tab

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def current_doc_page(self) -> str:
        """Doc page id for the active tab (drives the tab-aware Information/F1)."""
        from ui.help_system import CREATOR_TAB_PAGES
        idx = self._tabs.currentIndex()
        if 0 <= idx < len(CREATOR_TAB_PAGES):
            return CREATOR_TAB_PAGES[idx]
        return "creator"

    def retranslate_ui(self) -> None:
        self._universe_label.setText(tr("creator_studio"))
        self._save_btn.setText(f"{tr('save_changes')} (Ctrl+S)")
        self._back_btn.setText(tr("hub"))
        self._tabs.setTabText(0, tr("tab_meta"))
        self._tabs.setTabText(1, tr("stats"))
        self._tabs.setTabText(2, tr("tab_entities"))
        self._tabs.setTabText(3, tr("tab_map"))
        self._tabs.setTabText(4, tr("tab_rules"))
        self._tabs.setTabText(5, tr("tab_events"))
        self._tabs.setTabText(6, tr("tab_setup"))
        self._tabs.setTabText(7, tr("tab_lore"))
        self._tabs.setTabText(8, tr("populate"))
        self._tabs.setTabText(9, tr("tab_files"))
        self._files_tab.retranslate_ui()

        self._lore_group.setTitle(tr("world_lore"))
        self._desc_group.setTitle(tr("universe_description_title"))
        self._prompt_group.setTitle(tr("sys_prompt_override"))
        self._first_msg_group.setTitle(tr("init_narrative"))
        self._belief_missions_group.setTitle(tr("belief_missions_title"))
        self._belief_missions_edit.setPlaceholderText(tr("belief_missions_placeholder"))
        self._tension_group.setTitle(tr("world_tension_level"))
        self._tension_label_row.setText(f"{tr('tension')} (0.0-1.0):")
        self._temp_label_row.setText(tr("llm_temp"))
        self._top_p_label_row.setText(tr("llm_top_p"))
        self._verbosity_label_row.setText(f"{tr('verbosity')}:")
        for i in range(self._verbosity_combo.count()):
            self._verbosity_combo.setItemText(i, tr(self._verbosity_combo.itemData(i)))
        
        self._lore_edit.setPlaceholderText(tr("global_lore_placeholder"))
        self._description_edit.setPlaceholderText(tr("universe_description_placeholder"))
        self._system_prompt_edit.setPlaceholderText(tr("system_prompt_placeholder"))
        self._first_message_edit.setPlaceholderText(tr("first_msg_placeholder"))

        self._entity_editor.retranslate_ui()
        self._rule_editor.retranslate_ui()
        self._stat_editor.retranslate_ui()
        self._lore_book_editor.retranslate_ui()
        self._scheduled_events_editor.retranslate_ui()
        self._story_setup_editor.retranslate_ui()
        
        self._companion_group.setTitle(tr("companion_feature"))
        self._companion_enabled_check.setText(tr("enable_companion_mode"))

    def load_universe(self, db_path: str) -> None:
        self._db_path = db_path
        self._db_worker = DbWorker(db_path)
        self._db_worker.full_universe_loaded.connect(self._on_full_universe_loaded)
        self._db_worker.error_occurred.connect(self._on_worker_error)
        self._db_worker.status_update.connect(self._main_window.on_status_update)
        self._db_worker.load_full_universe()
        self._files_tab.set_universe(db_path)  # TICKET-029
        # TICKET-030 : preview de Populate (sandbox + diff) si univers-dossier.
        from axiom.library import universe_root_for
        self._populate_tab.set_preview_supported(universe_root_for(db_path) is not None)
        self._db_worker.populate_previewed.connect(self._on_populate_previewed)
        self._db_worker.staged_applied.connect(self._on_staged_applied)
        # TICKET-029 : refresh/conversion passent par CE worker (pas d'instance
        # jetable par action : une référence écrasée en plein vol risque le GC).
        self._db_worker.definition_refreshed.connect(self._on_definition_refreshed)
        self._db_worker.universe_converted.connect(self._on_universe_converted)
        # TICKET-033 : annulation volontaire ≠ erreur (pas de popup).
        self._db_worker.generation_cancelled.connect(
            lambda _msg: self._main_window.on_status_update(tr("generation_cancelled")))

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(dict)
    def _on_full_universe_loaded(self, data: dict) -> None:
        sdefs = data.get("stat_definitions", [])
        self._stat_editor.populate(sdefs)
        
        entities = data.get("entities", [])
        self._entity_editor.populate(entities)
        self._entity_editor.set_stat_definitions(sdefs)
        
        # Populate Hero Selector
        self._companion_hero_combo.clear()
        for e in entities:
            name = e.get("name", e["entity_id"])
            self._companion_hero_combo.addItem(name, e["entity_id"])

        self._rule_editor.populate(data.get("rules", []))
        self._rule_editor.set_stat_definitions(sdefs)
        self._lore_book_editor.populate(data.get("lore_book", []))
        self._scheduled_events_editor.set_events_and_calendar(data.get("scheduled_events", []), data.get("meta", {}))
        self._story_setup_editor.populate(data.get("story_setup", []))
        self._map_editor.populate(data.get("locations", []), data.get("connections", []))
        self._on_meta_loaded(data.get("meta", {}))

    @Slot(int)
    def _on_tab_changed(self, index: int) -> None:
        if index in (2, 3):
            sdefs = self._stat_editor.collect_data()
            self._entity_editor.set_stat_definitions(sdefs)
            self._rule_editor.set_stat_definitions(sdefs)
        # TICKET-029 : la source bouge après chaque save Studio (TICKET-027),
        # l'onglet Fichiers se relit à chaque activation.
        if self._tabs.widget(index) is self._files_tab:
            self._files_tab.refresh()

    @Slot()
    def _on_save_clicked(self) -> None:
        if not self._db_path: return

        events, cal_meta = self._scheduled_events_editor.collect_data()
        locs, conns = self._map_editor.collect_data()
        
        meta = {
            "global_lore": self._lore_edit.toPlainText().strip(),
            "universe_description": self._description_edit.toPlainText().strip(),
            "system_prompt": self._system_prompt_edit.toPlainText().strip(),
            "first_message": self._first_message_edit.toPlainText().strip(),
            "world_tension_level": str(self._tension_spin.value()),
            "llm_temperature": str(self._temp_spin.value()),
            "llm_top_p": str(self._top_p_spin.value()),
            "llm_verbosity": self._verbosity_combo.currentData() or "balanced",
            "companion_mode_enabled": "1" if self._companion_enabled_check.isChecked() else "0",
            "companion_hero_id": self._companion_hero_combo.currentData() or "",
            "calendar_config": cal_meta.get("calendar_config", "{}"),
        }
        # B-3: per-character memory styles → belief_missions JSON (empty = absent).
        import json as _json
        from axiom.missions import parse_missions_text
        _bm = parse_missions_text(self._belief_missions_edit.toPlainText())
        meta["belief_missions"] = _json.dumps(_bm, ensure_ascii=False) if _bm else ""

        data = {
            "meta": meta,
            "stat_definitions": self._stat_editor.collect_data(),
            "entities": self._entity_editor.collect_data(),
            "rules": self._rule_editor.collect_data(),
            "lore_book": self._lore_book_editor.collect_data(),
            "scheduled_events": events,
            "story_setup": self._story_setup_editor.collect_data(),
            "locations": locs,
            "connections": conns
        }

        self._save_worker = DbWorker(self._db_path)
        self._save_worker.save_complete.connect(self._on_save_complete)
        self._save_worker.error_occurred.connect(self._on_worker_error)
        self._save_worker.save_full_universe(
            data["entities"], data["rules"], data["meta"], 
            data["lore_book"], data["stat_definitions"], data["scheduled_events"],
            data["story_setup"], data["locations"], data["connections"]
        )

    @Slot()
    def _on_save_complete(self) -> None:
        self._main_window.on_status_update(tr("universe_saved"))
        if self._pending_ai_tasks:
            tasks = list(self._pending_ai_tasks)
            self._pending_ai_tasks = []
            # TICKET-030 : mode preview — tout le lot part dans une sandbox,
            # le diff texte sera proposé avant application.
            if self._pending_ai_preview:
                self._pending_ai_preview = False
                self._db_worker.preview_populate(
                    tasks, self._pending_ai_mode, self._pending_ai_text)
                return
            for task in tasks:
                if task == "meta":
                    self._db_worker.populate_meta(self._pending_ai_mode, self._pending_ai_text)
                elif task == "stats":
                    self._db_worker.populate_stats(self._pending_ai_mode, self._pending_ai_text)
                elif task == "entities":
                    self._db_worker.populate_entities(self._pending_ai_mode, self._pending_ai_text)
                elif task == "rules":
                    self._db_worker.populate_rules(self._pending_ai_mode, self._pending_ai_text)
                elif task == "events":
                    self._db_worker.populate_events(self._pending_ai_mode, self._pending_ai_text)
                elif task == "lore":
                    self._db_worker.populate_lore(self._pending_ai_mode, self._pending_ai_text)

    @Slot(list, str, object, bool)
    def _on_populate_requested(self, tasks: list[str], mode: str, text: str | None,
                               preview: bool = False) -> None:
        self._pending_ai_tasks = tasks
        self._pending_ai_mode = mode
        self._pending_ai_text = text
        self._pending_ai_preview = preview
        self._on_save_clicked()

    @Slot(str, object)
    def _on_populate_requested_single(self, task: str, text: str | None) -> None:
        """Helper for single-tab populate buttons."""
        self._on_populate_requested([task], "auto", text, False)

    def _on_meta_loaded(self, meta: dict) -> None:
        name = meta.get("universe_name", "Universe")
        self._universe_label.setText(f"{tr('creator_studio')} - {name}")
        self._lore_edit.setPlainText(meta.get("global_lore", ""))
        self._description_edit.setPlainText(meta.get("universe_description", ""))
        self._system_prompt_edit.setPlainText(meta.get("system_prompt", ""))
        self._first_message_edit.setPlainText(meta.get("first_message", ""))
        # B-3: belief_missions JSON → "Name: mission" lines.
        from axiom.missions import get_belief_missions_from_value, missions_to_text
        self._belief_missions_edit.setPlainText(
            missions_to_text(get_belief_missions_from_value(meta.get("belief_missions", "")))
        )
        # Meta values come from user-editable sources (universe.toml, imported
        # .axiom) — a malformed number must not crash the Studio.
        self._tension_spin.setValue(_meta_float(meta, "world_tension_level", 0.3))
        self._temp_spin.setValue(_meta_float(meta, "llm_temperature", 0.7))
        self._top_p_spin.setValue(_meta_float(meta, "llm_top_p", 1.0))
        
        # TICKET-032 : normalise les valeurs historiques stockées localisées.
        from core.localization import canonical_verbosity
        v = canonical_verbosity(meta.get("llm_verbosity", "balanced"))
        self._verbosity_combo.setCurrentIndex(max(0, self._verbosity_combo.findData(v)))

        # Companion Feature
        enabled = meta.get("companion_mode_enabled") == "1"
        self._companion_enabled_check.setChecked(enabled)
        
        hero_id = meta.get("companion_hero_id", "")
        if hero_id:
            h_idx = self._companion_hero_combo.findData(hero_id)
            if h_idx >= 0:
                self._companion_hero_combo.setCurrentIndex(h_idx)

    @Slot()
    def _on_back_clicked(self) -> None:
        self._main_window.show_hub()

    @Slot(str)
    def _on_map_populate_requested(self, custom_text: str) -> None:
        if not self._db_path: return
        self._on_save_clicked() # Save before AI generation
        worker = DbWorker(self._db_path)
        worker.full_universe_loaded.connect(self._on_full_universe_loaded)
        worker.status_update.connect(self._main_window.on_status_update)
        worker.error_occurred.connect(self._on_worker_error)
        worker.populate_map(custom_text=custom_text)

    # --- TICKET-029 : onglet « Fichiers » -------------------------------

    @Slot(str)
    def _on_source_file_saved(self, _path: str) -> None:
        """Un fichier source a été écrit : recompile la définition in-place,
        puis recharge les vues classiques du Studio (texte = vérité)."""
        if not self._db_path:
            return
        from axiom.library import universe_root_for
        src_root = universe_root_for(self._db_path)
        if src_root is None:
            return
        self._db_worker.refresh_definition_from(str(src_root))

    @Slot()
    def _on_definition_refreshed(self) -> None:
        self._main_window.on_status_update(tr("files_saved_refreshed"))
        self._db_worker.load_full_universe()

    @Slot()
    def _on_convert_requested(self) -> None:
        """Convertit le .db plat courant en univers-dossier puis recharge le Studio."""
        if not self._db_path:
            return
        self._db_worker.convert_flat_to_folder()

    @Slot(dict)
    def _on_universe_converted(self, info: dict) -> None:
        self._main_window.on_status_update(tr("files_converted_msg"))
        # Recharge le Studio sur le nouveau cache (l'onglet Fichiers passe en mode arbo).
        self.load_universe(info["db_path"])

    # --- TICKET-030 : Populate ciblé avec prévisualisation ---------------

    @Slot(dict)
    def _on_populate_previewed(self, info: dict) -> None:
        if not info.get("diffs"):
            QMessageBox.information(self, tr("populate"), tr("preview_no_changes"))
            return
        from ui.widgets.diff_preview_dialog import DiffPreviewDialog
        dialog = DiffPreviewDialog(info["diffs"], self)
        if dialog.exec() == QDialog.Accepted:
            self._db_worker.apply_staged(info["staged_dir"], info["src_dir"])
        else:
            from workers.db_tasks import discard_staged_source
            discard_staged_source(info["staged_dir"])

    @Slot()
    def _on_staged_applied(self) -> None:
        self._main_window.on_status_update(tr("staged_applied_msg"))
        self._db_worker.load_full_universe()
        if self._tabs.currentWidget() is self._files_tab:
            self._files_tab.refresh()

    @Slot(str)
    def _on_worker_error(self, message: str) -> None:
        self._pending_ai_tasks = []
        self._pending_ai_preview = False
        QMessageBox.critical(self, tr("error"), message)
