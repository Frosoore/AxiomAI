"""
workers/db_worker.py

Stateless Database Task Dispatcher for Axiom AI.

Uses QThreadPool and QRunnable (from workers.db_tasks) to execute database
operations without the state-overwriting risks of a single QThread.
"""

from __future__ import annotations

import sqlite3
import json
from typing import Any

from PySide6.QtCore import QObject, Signal, QThreadPool

from axiom.schema import (
    get_connection,
    migrate_lore_book_table,
    migrate_stat_definitions_table,
    migrate_entities_table,
    migrate_scheduled_events_table,
    migrate_timeline_table,
    migrate_location_tables
)
from workers.db_tasks import (
    LoadStatsTask, LoadCheckpointsTask, RewindTask, AppendEventTask,
    LoadSessionHistoryTask, UpdateVariantTask, SnapshotTask, DeleteSaveTask, RenameSaveTask,
    PopulateEntitiesTask, TickModifiersTask, CreatePlayerEntityTask, DeleteEntityTask,
    LoadInventoryTask, LoadTimelineTask,
    PackSaveTask, UnpackSaveTask, DuplicateSaveTask, ExportSaveStateTask, EditSaveStateTask,
    RefreshDefinitionTask, ConvertFlatDbTask,
    PreviewPopulateTask, ApplyStagedSourceTask, CanonizeStoryTask
)


class DbWorker(QObject):
    """Dispatches DB tasks to a QThreadPool.
    
    This replaces the old QThread-based DbWorker to prevent race conditions
    where multiple task setups would overwrite each other's parameters.
    """

    stats_loaded = Signal(list)
    inventory_loaded = Signal(dict)
    timeline_loaded = Signal(list)
    checkpoints_loaded = Signal(list)
    rewind_complete = Signal(dict)
    universe_meta_loaded = Signal(dict)
    stat_definitions_loaded = Signal(list)
    entities_loaded = Signal(list)
    rules_loaded = Signal(list)
    lore_book_loaded = Signal(list)
    scheduled_events_loaded = Signal(list)
    personas_loaded = Signal(list)
    library_loaded = Signal(list)
    saves_loaded = Signal(list)
    history_loaded = Signal(list, int, str)
    full_universe_loaded = Signal(dict)
    modifiers_ticked = Signal(list)
    variant_updated = Signal(str)
    integrity_validated = Signal(bool, dict)
    save_complete = Signal()
    error_occurred = Signal(str)
    status_update = Signal(str)
    # TICKET-028 — gestion des saves depuis le GUI
    save_packed = Signal(str)            # chemin de l'archive .axiomsave écrite
    save_unpacked = Signal(dict)         # {"save_id", "db_path"} ou {"needs_force", "message"}
    save_duplicated = Signal(dict)       # {"save_id", "db_path"}
    save_state_exported = Signal(str, str)  # (save_id, texte save_state.toml)
    save_edited = Signal(int)            # tour de la correction, -1 si rien à appliquer
    # TICKET-029 — onglet « Fichiers » du Creator Studio
    definition_refreshed = Signal()      # source texte recompilée in-place dans le .db
    universe_converted = Signal(dict)    # {"source_dir", "db_path"} après conversion
    # TICKET-030 — Populate × Universe-as-Code
    populate_previewed = Signal(dict)    # {"diffs", "staged_dir", "src_dir", "counts"}
    staged_applied = Signal()            # arbre validé appliqué (source + .db)
    story_canonized = Signal(dict)       # idem preview + {"universe_db", "applied"}
    # TICKET-033 — annulation volontaire d'une génération (pas une erreur)
    generation_cancelled = Signal(str)

    def __init__(self, db_path: str) -> None:
        super().__init__()
        self._db_path = db_path
        self._pool = QThreadPool.globalInstance()
        self._active_tasks: set[Any] = set()

    def _setup_task(self, task):
        """Connect task signals to worker signals and start it."""
        task.signals.status.connect(self.status_update.emit)
        task.signals.error.connect(self.error_occurred.emit)
        task.signals.cancelled.connect(self.generation_cancelled.emit)
        
        # Prevent GC of the task object
        self._active_tasks.add(task)
        task.signals.finished.connect(lambda: self._active_tasks.discard(task))
        
        self._pool.start(task)
        return task

    # ------------------------------------------------------------------
    # Dispatched Tasks
    # ------------------------------------------------------------------

    def load_stats(self, save_id: str) -> None:
        task = LoadStatsTask(self._db_path, save_id)
        task.signals.result.connect(self.stats_loaded.emit)
        self._setup_task(task)

    def load_inventory(self, save_id: str) -> None:
        task = LoadInventoryTask(self._db_path, save_id)
        task.signals.result.connect(self.inventory_loaded.emit)
        self._setup_task(task)

    def load_timeline(self, save_id: str) -> None:
        task = LoadTimelineTask(self._db_path, save_id)
        task.signals.result.connect(self.timeline_loaded.emit)
        self._setup_task(task)

    def load_stats_and_inventory(self, save_id: str) -> None:
        """Fetch both stats and inventory for all active entities."""
        from workers.db_tasks import LoadStatsAndInventoryTask
        task = LoadStatsAndInventoryTask(self._db_path, save_id)
        task.signals.result.connect(lambda res: (self.stats_loaded.emit(res[0]), self.inventory_loaded.emit(res[1])))
        self._setup_task(task)

    def load_full_game_state(self, save_id: str) -> None:
        """Fetch stats, inventory, and timeline in one go."""
        from workers.db_tasks import LoadFullGameStateTask
        task = LoadFullGameStateTask(self._db_path, save_id)
        task.signals.result.connect(lambda res: (
            self.stats_loaded.emit(res[0]), 
            self.inventory_loaded.emit(res[1]),
            self.timeline_loaded.emit(res[2])
        ))
        self._setup_task(task)

    def load_checkpoints(self, save_id: str) -> None:
        task = LoadCheckpointsTask(self._db_path, save_id)
        task.signals.result.connect(self.checkpoints_loaded.emit)
        self._setup_task(task)

    def validate_integrity(self, save_id: str) -> None:
        from workers.db_tasks import ValidateIntegrityTask
        task = ValidateIntegrityTask(self._db_path, save_id)
        task.signals.result.connect(lambda res: self.integrity_validated.emit(res[0], res[1]))
        self._setup_task(task)

    def execute_rewind(self, save_id: str, target_turn_id: int) -> None:
        task = RewindTask(self._db_path, save_id, target_turn_id)
        task.signals.result.connect(self.rewind_complete.emit)
        self._setup_task(task)

    def append_event(self, save_id: str, turn_id: int, etype: str, target: str, payload: Any) -> None:
        task = AppendEventTask(self._db_path, save_id, turn_id, etype, target, payload)
        task.signals.result.connect(lambda _: self.save_complete.emit())
        self._setup_task(task)

    def load_session_history(self, save_id: str) -> None:
        from workers.db_tasks import LoadSessionHistoryTask
        task = LoadSessionHistoryTask(self._db_path, save_id)
        task.signals.result.connect(lambda res: self.history_loaded.emit(res[0], res[1], res[2]))
        self._setup_task(task)

    def switch_narrative_variant(self, save_id: str, turn_id: int, index: int) -> None:
        from workers.db_tasks import UpdateVariantTask
        task = UpdateVariantTask(self._db_path, save_id, turn_id, index)
        task.signals.result.connect(self.variant_updated.emit)
        task.signals.result.connect(lambda _: self.save_complete.emit())
        self._setup_task(task)

    def delete_save(self, save_id: str) -> None:
        task = DeleteSaveTask(self._db_path, save_id)
        task.signals.result.connect(lambda _: self.save_complete.emit())
        self._setup_task(task)

    def rename_save(self, save_id: str, new_name: str) -> None:
        task = RenameSaveTask(self._db_path, save_id, new_name)
        task.signals.result.connect(lambda _: self.save_complete.emit())
        self._setup_task(task)

    # --- TICKET-028 : gestion des saves depuis le GUI ------------------

    def pack_save_to(self, save_id: str, output_path: str) -> None:
        """Exporte une save en archive .axiomsave."""
        task = PackSaveTask(self._db_path, save_id, output_path)
        task.signals.result.connect(self.save_packed.emit)
        self._setup_task(task)

    def unpack_save_from(self, archive_path: str, force: bool = False) -> None:
        """Importe une archive .axiomsave dans cet univers."""
        task = UnpackSaveTask(self._db_path, archive_path, force)
        task.signals.result.connect(self.save_unpacked.emit)
        self._setup_task(task)

    def duplicate_save(self, save_id: str, new_name: str | None = None) -> None:
        """Duplique une save (= « save manuelle » / point de branche)."""
        task = DuplicateSaveTask(self._db_path, save_id, new_name)
        task.signals.result.connect(self.save_duplicated.emit)
        self._setup_task(task)

    def export_save_state(self, save_id: str) -> None:
        """Matérialise l'état d'une save en texte save_state.toml (édition)."""
        task = ExportSaveStateTask(self._db_path, save_id)
        task.signals.result.connect(lambda res: self.save_state_exported.emit(res[0], res[1]))
        self._setup_task(task)

    def apply_save_state_edit(self, save_id: str, original_text: str, edited_text: str) -> None:
        """Applique le diff d'un save_state.toml édité (correction en place)."""
        task = EditSaveStateTask(self._db_path, save_id, original_text, edited_text)
        task.signals.result.connect(self.save_edited.emit)
        self._setup_task(task)

    # --- TICKET-029 : onglet « Fichiers » du Creator Studio -------------

    def refresh_definition_from(self, src_dir: str) -> None:
        """Recompile la définition depuis la source texte (in-place, runtime intact)."""
        task = RefreshDefinitionTask(self._db_path, src_dir)
        task.signals.result.connect(lambda _: self.definition_refreshed.emit())
        self._setup_task(task)

    def convert_flat_to_folder(self) -> None:
        """Convertit le .db plat de ce worker en univers-dossier."""
        task = ConvertFlatDbTask(self._db_path)
        task.signals.result.connect(self.universe_converted.emit)
        self._setup_task(task)

    # --- TICKET-030 : Populate × Universe-as-Code -----------------------

    def preview_populate(self, targets: list[str], mode: str = "auto",
                         custom_text: str | None = None) -> None:
        """Populate ciblé en sandbox → diff texte à valider (univers-dossier)."""
        task = PreviewPopulateTask(self._db_path, targets, mode, custom_text)
        task.signals.result.connect(self.populate_previewed.emit)
        self._setup_task(task)

    def apply_staged(self, staged_dir: str, src_dir: str,
                     save_db: str | None = None) -> None:
        """Applique un arbre source validé (source + recompilation in-place)."""
        task = ApplyStagedSourceTask(self._db_path, staged_dir, src_dir, save_db)
        task.signals.result.connect(lambda _: self.staged_applied.emit())
        self._setup_task(task)

    def canonize_story(self, narrative_text: str, preview: bool = True) -> None:
        """Extrait le canon de l'histoire récente vers la définition de l'univers."""
        task = CanonizeStoryTask(self._db_path, narrative_text, preview)
        task.signals.result.connect(self.story_canonized.emit)
        self._setup_task(task)

    def tick_modifiers(self, save_id: str, elapsed_minutes: int) -> None:
        task = TickModifiersTask(self._db_path, save_id, elapsed_minutes)
        task.signals.result.connect(self.modifiers_ticked.emit)
        task.signals.result.connect(lambda _: self.save_complete.emit())
        self._setup_task(task)

    def create_player_entity(self, name: str, description: str = "") -> None:
        task = CreatePlayerEntityTask(self._db_path, name, description)
        task.signals.result.connect(lambda _: self.save_complete.emit())
        self._setup_task(task)

    def delete_entity(self, entity_id: str) -> None:
        task = DeleteEntityTask(self._db_path, entity_id)
        task.signals.result.connect(lambda _: self.save_complete.emit())
        self._setup_task(task)

    def take_snapshot_async(self, save_id: str, turn_id: int) -> None:
        """Periodic background snapshot to keep Event Sourcing performance high."""
        task = SnapshotTask(self._db_path, save_id, turn_id)
        self._setup_task(task)

    def populate_entities(self, mode: str = "auto", custom_text: str | None = None) -> None:
        """AI-driven entity generation (asynchronous)."""
        task = PopulateEntitiesTask(self._db_path, mode, custom_text)
        task.signals.result.connect(lambda _: self.load_full_universe())
        self._setup_task(task)

    def populate_lore(self, mode: str = "auto", custom_text: str | None = None) -> None:
        """AI-driven lore book generation (asynchronous)."""
        from workers.db_tasks import PopulateLoreTask
        task = PopulateLoreTask(self._db_path, mode, custom_text)
        task.signals.result.connect(lambda _: self.load_full_universe())
        self._setup_task(task)

    def populate_map(self, mode: str = "auto", custom_text: str | None = None) -> None:
        """AI-driven world map generation (asynchronous)."""
        from workers.db_tasks import PopulateMapTask
        task = PopulateMapTask(self._db_path, mode, custom_text)
        task.signals.result.connect(lambda _: self.load_full_universe())
        self._setup_task(task)

    def populate_meta(self, mode: str = "auto", custom_text: str | None = None) -> None:
        from workers.db_tasks import PopulateMetaTask
        task = PopulateMetaTask(self._db_path, mode, custom_text)
        task.signals.result.connect(lambda _: self.load_full_universe())
        self._setup_task(task)

    def populate_stats(self, mode: str = "auto", custom_text: str | None = None) -> None:
        from workers.db_tasks import PopulateStatsTask
        task = PopulateStatsTask(self._db_path, mode, custom_text)
        task.signals.result.connect(lambda _: self.load_full_universe())
        self._setup_task(task)

    def populate_rules(self, mode: str = "auto", custom_text: str | None = None) -> None:
        from workers.db_tasks import PopulateRulesTask
        task = PopulateRulesTask(self._db_path, mode, custom_text)
        task.signals.result.connect(lambda _: self.load_full_universe())
        self._setup_task(task)

    def populate_events(self, mode: str = "auto", custom_text: str | None = None) -> None:
        from workers.db_tasks import PopulateEventsTask
        task = PopulateEventsTask(self._db_path, mode, custom_text)
        task.signals.result.connect(lambda _: self.load_full_universe())
        self._setup_task(task)

    def load_full_universe(self, save_id: str | None = None) -> None:
        from workers.db_tasks import LoadFullUniverseTask
        task = LoadFullUniverseTask(self._db_path, save_id)
        task.signals.result.connect(self._on_load_full_universe_result)
        self._setup_task(task)

    # ------------------------------------------------------------------
    # Legacy/Remaining tasks (to be refactored into db_tasks.py later if needed)
    # For now, we run them synchronously in a wrapper task for compatibility
    # ------------------------------------------------------------------

    def load_universe_meta(self) -> None:
        class TempTask(LoadStatsTask):
            def execute(self) -> dict:
                with get_connection(self.db_path) as conn:
                    rows = conn.execute("SELECT key, value FROM Universe_Meta;").fetchall()
                return {row[0]: row[1] for row in rows}
        
        task = TempTask(self._db_path, "")
        task.signals.result.connect(self.universe_meta_loaded.emit)
        self._setup_task(task)

    def load_entities_and_rules(self) -> None:
        class TempTask(LoadStatsTask):
            def execute(self) -> tuple:
                migrate_lore_book_table(self.db_path)
                migrate_stat_definitions_table(self.db_path)
                migrate_entities_table(self.db_path)
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    e_rows = conn.execute("SELECT entity_id, entity_type, name, description FROM Entities WHERE is_active = 1;").fetchall()
                    entities = []
                    for r in e_rows:
                        eid = r["entity_id"]
                        stats = {s["stat_key"]: s["stat_value"] for s in conn.execute("SELECT stat_key, stat_value FROM Entity_Stats WHERE entity_id = ?;", (eid,))}
                        entities.append({
                            "entity_id": eid,
                            "entity_type": r["entity_type"],
                            "name": r["name"],
                            "description": r["description"],
                            "stats": stats
                        })
                    
                    rules = []
                    r_rows = conn.execute("SELECT rule_id, priority, conditions, actions, target_entity FROM Rules;").fetchall()
                    for r in r_rows:
                        rules.append({
                            "rule_id": r["rule_id"], "priority": r["priority"],
                            "conditions": json.loads(r["conditions"]) if r["conditions"] else {},
                            "actions": json.loads(r["actions"]) if r["actions"] else [],
                            "target_entity": r["target_entity"]
                        })
                    
                    lb_rows = conn.execute("SELECT entry_id, category, name, content FROM Lore_Book;").fetchall()
                    lore = [{"entry_id": r["entry_id"], "category": r["category"], "name": r["name"], "content": r["content"]} for r in lb_rows]

                    sd_rows = conn.execute("SELECT stat_id, name, description, value_type, parameters FROM Stat_Definitions;").fetchall()
                    stat_defs = []
                    for r in sd_rows:
                        stat_defs.append({
                            "stat_id": r["stat_id"], "name": r["name"], "description": r["description"],
                            "value_type": r["value_type"], "parameters": json.loads(r["parameters"])
                        })
                return entities, rules, lore, stat_defs

        task = TempTask(self._db_path, "")
        task.signals.result.connect(lambda res: (
            self.entities_loaded.emit(res[0]),
            self.rules_loaded.emit(res[1]),
            self.lore_book_loaded.emit(res[2]),
            self.stat_definitions_loaded.emit(res[3])
        ))
        self._setup_task(task)

    def save_universe_meta(self, meta: dict) -> None:
        """Atomic update of multiple keys in Universe_Meta."""
        class TempTask(LoadStatsTask):
            def execute(self) -> bool:
                with sqlite3.connect(self.db_path) as conn:
                    for k, v in meta.items():
                        conn.execute("INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES (?, ?);", (k, str(v)))
                    conn.commit()
                # TICKET-027 : univers-dossier → l'arbo texte reste la vérité.
                from axiom.library import sync_source_if_any
                sync_source_if_any(self.db_path)
                return True
        task = TempTask(self._db_path, "")
        task.signals.result.connect(lambda _: self.save_complete.emit())
        self._setup_task(task)

    def save_full_universe(self, entities, rules, meta, lore_book, stat_definitions=None, scheduled_events=None, story_setup=None, locations=None, connections=None) -> None:
        class TempTask(LoadStatsTask):
            def execute(self) -> bool:
                from axiom.schema import migrate_story_setup_table
                migrate_lore_book_table(self.db_path)
                migrate_stat_definitions_table(self.db_path)
                migrate_entities_table(self.db_path)
                migrate_scheduled_events_table(self.db_path)
                migrate_story_setup_table(self.db_path)
                migrate_location_tables(self.db_path)
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("PRAGMA foreign_keys=ON;")
                    conn.execute("DELETE FROM Entity_Stats;")
                    conn.execute("DELETE FROM Entities;")
                    for e in entities:
                        eid = e.get("entity_id", "").strip()
                        if not eid: continue
                        conn.execute("INSERT INTO Entities (entity_id, entity_type, name, description, is_active) VALUES (?, ?, ?, ?, 1);",
                                   (eid, e.get("entity_type", "npc"), e.get("name", ""), e.get("description", "")))
                        for sk, sv in e.get("stats", {}).items():
                            conn.execute("INSERT INTO Entity_Stats (entity_id, stat_key, stat_value) VALUES (?, ?, ?);", (eid, str(sk), str(sv)))
                    
                    conn.execute("DELETE FROM Rules;")
                    for r in rules:
                        conn.execute("INSERT INTO Rules (rule_id, priority, conditions, actions, target_entity) VALUES (?, ?, ?, ?, ?);",
                                   (r["rule_id"], int(r.get("priority", 0)), json.dumps(r.get("conditions", {})), json.dumps(r.get("actions", [])), r.get("target_entity", "*")))
                    
                    conn.execute("DELETE FROM Stat_Definitions;")
                    if stat_definitions:
                        for s in stat_definitions:
                            conn.execute("INSERT INTO Stat_Definitions (stat_id, name, description, value_type, parameters) VALUES (?, ?, ?, ?, ?);",
                                       (s["stat_id"], s["name"], s.get("description", ""), s["value_type"], json.dumps(s.get("parameters", {}))))

                    for k, v in meta.items():
                        conn.execute("INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES (?, ?);", (k, str(v)))
                    
                    conn.execute("DELETE FROM Lore_Book;")
                    for l in lore_book:
                        conn.execute("INSERT INTO Lore_Book (entry_id, category, name, content) VALUES (?, ?, ?, ?);", (l["entry_id"], l.get("category", ""), l.get("name", ""), l.get("content", "")))
                    
                    conn.execute("DELETE FROM Scheduled_Events;")
                    if scheduled_events:
                        for ev in scheduled_events:
                            conn.execute("INSERT INTO Scheduled_Events (event_id, trigger_minute, title, description) VALUES (?, ?, ?, ?);",
                                       (ev["event_id"], int(ev["trigger_minute"]), ev["title"], ev["description"]))
                    
                    conn.execute("DELETE FROM Story_Setup;")
                    if story_setup:
                        for ss in story_setup:
                            conn.execute(
                                "INSERT INTO Story_Setup (setup_id, question, type, options, max_selections, priority) VALUES (?, ?, ?, ?, ?, ?);",
                                (ss["setup_id"], ss["question"], ss["type"], json.dumps(ss.get("options", [])), ss.get("max_selections", 1), ss.get("priority", 0))
                            )
                    
                    conn.execute("DELETE FROM Location_Connections;")
                    conn.execute("DELETE FROM Locations;")
                    if locations:
                        for l in locations:
                            conn.execute(
                                "INSERT INTO Locations (location_id, name, scale, parent_id, description, x, y) VALUES (?, ?, ?, ?, ?, ?, ?);",
                                (l["location_id"], l["name"], l["scale"], l.get("parent_id"), l.get("description", ""), l.get("x", 0), l.get("y", 0))
                            )
                    if connections:
                        for c in connections:
                            conn.execute(
                                "INSERT INTO Location_Connections (source_id, target_id, distance_km) VALUES (?, ?, ?);",
                                (c["source_id"], c["target_id"], int(c["distance_km"]))
                            )
                    conn.commit()
                # TICKET-027 : univers-dossier → l'arbo texte reste la vérité.
                from axiom.library import sync_source_if_any
                sync_source_if_any(self.db_path)
                return True

        task = TempTask(self._db_path, "")
        task.signals.result.connect(lambda _: self.save_complete.emit())
        self._setup_task(task)

    def load_library(self, library_dir: str) -> None:
        from axiom.library import discover_universes
        class TempTask(LoadStatsTask):
            def execute(self) -> list:
                # *.db plat (legacy) + dossiers source Universe-as-Code (compilés à la demande).
                return discover_universes(library_dir)
        task = TempTask(self._db_path, "")
        task.signals.result.connect(self.library_loaded.emit)
        self._setup_task(task)

    def load_saves_async(self) -> None:
        from axiom.savestore import list_saves
        class TempTask(LoadStatsTask):
            def execute(self) -> list:
                # §7.6 : saves séparées (saves/<univers>/) + legacy embarquées.
                # Chaque ligne porte db_path (base à ouvrir) et storage.
                return list_saves(self.db_path)
        task = TempTask(self._db_path, "")
        task.signals.result.connect(self.saves_loaded.emit)
        self._setup_task(task)

    def load_full_universe(self, save_id: str = "") -> None:
        """Atomic load of entities, rules, lore book, meta, stat definitions, scheduled events, and optionally history."""
        class TempTask(LoadStatsTask):
            def execute(self) -> tuple:
                migrate_lore_book_table(self.db_path)
                migrate_stat_definitions_table(self.db_path)
                migrate_entities_table(self.db_path)
                migrate_scheduled_events_table(self.db_path)
                migrate_location_tables(self.db_path)
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    # 1. Entities
                    e_rows = conn.execute("SELECT entity_id, entity_type, name, description FROM Entities WHERE is_active = 1;").fetchall()
                    entities = []
                    for r in e_rows:
                        eid = r["entity_id"]
                        stats = {s["stat_key"]: s["stat_value"] for s in conn.execute("SELECT stat_key, stat_value FROM Entity_Stats WHERE entity_id = ?;", (eid,))}
                        entities.append({
                            "entity_id": eid,
                            "entity_type": r["entity_type"],
                            "name": r["name"],
                            "description": r["description"],
                            "stats": stats
                        })
                    
                    # 2. Rules
                    rules = []
                    r_rows = conn.execute("SELECT rule_id, priority, conditions, actions, target_entity FROM Rules;").fetchall()
                    for r in r_rows:
                        rules.append({
                            "rule_id": r["rule_id"], "priority": r["priority"],
                            "conditions": json.loads(r["conditions"]) if r["conditions"] else {},
                            "actions": json.loads(r["actions"]) if r["actions"] else [],
                            "target_entity": r["target_entity"]
                        })
                    
                    # 3. Lore
                    lb_rows = conn.execute("SELECT entry_id, category, name, content FROM Lore_Book;").fetchall()
                    lore = [{"entry_id": r["entry_id"], "category": r["category"], "name": r["name"], "content": r["content"]} for r in lb_rows]
                    
                    # 4. Meta
                    m_rows = conn.execute("SELECT key, value FROM Universe_Meta;").fetchall()
                    meta = {row["key"]: row["value"] for row in m_rows}

                    # 5. Stat Definitions
                    sd_rows = conn.execute("SELECT stat_id, name, description, value_type, parameters FROM Stat_Definitions;").fetchall()
                    stat_defs = []
                    for r in sd_rows:
                        stat_defs.append({
                            "stat_id": r["stat_id"], "name": r["name"], "description": r["description"],
                            "value_type": r["value_type"], "parameters": json.loads(r["parameters"])
                        })
                    
                    # 6. Scheduled Events
                    se_rows = conn.execute("SELECT event_id, trigger_minute, title, description FROM Scheduled_Events;").fetchall()
                    scheduled_events = [{"event_id": r["event_id"], "trigger_minute": r["trigger_minute"], "title": r["title"], "description": r["description"]} for r in se_rows]

                    # 7. Story Setup
                    from axiom.schema import migrate_story_setup_table
                    migrate_story_setup_table(self.db_path)
                    ss_rows = conn.execute("SELECT setup_id, question, type, options, max_selections, priority FROM Story_Setup ORDER BY priority ASC;").fetchall()
                    story_setup = [{
                        "setup_id": r["setup_id"],
                        "question": r["question"],
                        "type": r["type"],
                        "options": json.loads(r["options"]),
                        "max_selections": r["max_selections"],
                        "priority": r["priority"]
                    } for r in ss_rows]

                    # 8. History
                    history = []
                    max_tid = 0
                    difficulty = "Normal"
                    if save_id:
                        # Fetch difficulty
                        d_row = conn.execute("SELECT difficulty FROM Saves WHERE save_id = ?;", (save_id,)).fetchone()
                        if d_row: difficulty = d_row[0]

                        h_rows = conn.execute("SELECT turn_id, event_type, payload FROM Event_Log WHERE save_id = ? AND event_type IN ('user_input', 'narrative_text', 'hero_intent') ORDER BY event_id ASC;", (save_id,)).fetchall()
                        for row in h_rows:
                            max_tid = max(max_tid, row[0])
                            history.append({"turn_id": row[0], "event_type": row[1], "payload": json.loads(row[2])})
                            
                    # 9. Locations
                    loc_rows = conn.execute("SELECT location_id, name, scale, parent_id, description, x, y FROM Locations;").fetchall()
                    locations = [dict(r) for r in loc_rows]

                    # 10. Connections
                    conn_rows = conn.execute("SELECT source_id, target_id, distance_km FROM Location_Connections;").fetchall()
                    connections = [dict(r) for r in conn_rows]
                            
                return entities, rules, lore, meta, stat_defs, scheduled_events, story_setup, history, max_tid, locations, connections, difficulty

        task = TempTask(self._db_path, save_id)
        task.signals.result.connect(self._on_load_full_universe_result)
        self._setup_task(task)

    def _on_load_full_universe_result(self, res: tuple) -> None:
        """Handle the multi-element result from load_full_universe."""
        self.entities_loaded.emit(res[0])
        self.rules_loaded.emit(res[1])
        self.lore_book_loaded.emit(res[2])
        self.universe_meta_loaded.emit(res[3])
        self.stat_definitions_loaded.emit(res[4])
        self.scheduled_events_loaded.emit(res[5])
        
        self.full_universe_loaded.emit({
            "entities": res[0],
            "rules": res[1],
            "lore_book": res[2],
            "meta": res[3],
            "stat_definitions": res[4],
            "scheduled_events": res[5],
            "story_setup": res[6],
            "locations": res[9],
            "connections": res[10]
        })
        
        # history (res[7]), max_tid (res[8]), difficulty (res[11])
        if len(res) > 7 and res[7] is not None:
            diff = res[11] if len(res) > 11 else "Normal"
            self.history_loaded.emit(res[7], res[8], diff)

    def load_global_personas(self) -> None:
        class TempTask(LoadStatsTask):
            def execute(self) -> list:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    rows = conn.execute("SELECT persona_id, name, description FROM Global_Personas;").fetchall()
                return [dict(r) for r in rows]
        task = TempTask(self._db_path, "")
        task.signals.result.connect(self.personas_loaded.emit)
        self._setup_task(task)

    def save_global_personas(self, personas: list[dict]) -> None:
        class TempTask(LoadStatsTask):
            def execute(self) -> bool:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("DELETE FROM Global_Personas;")
                    for p in personas:
                        conn.execute("INSERT INTO Global_Personas (persona_id, name, description) VALUES (?, ?, ?);", (p["persona_id"], p["name"], p["description"]))
                    conn.commit()
                return True
        task = TempTask(self._db_path, "")
        task.signals.result.connect(lambda _: self.save_complete.emit())
        self._setup_task(task)  # TICKET-025 : la tâche n'était jamais dispatchée → personas jamais sauvegardées
