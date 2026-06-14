"""
workers/db_worker.py

Stateless Database Task Dispatcher for Axiom AI.

Uses QThreadPool and QRunnable (from workers.db_tasks) to execute database
operations without the state-overwriting risks of a single QThread.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Signal, QThreadPool

from workers.db_tasks import (
    LoadStatsTask, LoadCheckpointsTask, RewindTask, AppendEventTask,
    LoadSessionHistoryTask, UpdateVariantTask, DeleteSaveTask, RenameSaveTask,
    PopulateEntitiesTask, TickModifiersTask, CreatePlayerEntityTask, DeleteEntityTask,
    LoadInventoryTask, LoadTimelineTask,
    PackSaveTask, UnpackSaveTask, DuplicateSaveTask, ExportSaveStateTask, EditSaveStateTask,
    PrepareSaveTask,
    RefreshDefinitionTask, ConvertFlatDbTask,
    PreviewPopulateTask, ApplyStagedSourceTask, CanonizeStoryTask,
    LoadUniverseMetaTask, LoadEntitiesAndRulesTask, SaveUniverseMetaTask,
    SaveFullUniverseTask, LoadLibraryTask, LoadSavesTask, LoadFullUniverseTask,
    LoadGlobalPersonasTask, SaveGlobalPersonasTask,
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
    save_prepared = Signal(str)          # save db resynchronisée, prête à lancer (QA-042.6)
    # TICKET-029 — onglet « Fichiers » du Creator Studio
    definition_refreshed = Signal()      # source texte recompilée in-place dans le .db
    universe_converted = Signal(dict)    # {"source_dir", "db_path"} après conversion
    # TICKET-030 — Populate × Universe-as-Code
    populate_previewed = Signal(dict)    # {"diffs", "staged_dir", "src_dir", "counts"}
    staged_applied = Signal()            # arbre validé appliqué (source + .db)
    story_canonized = Signal(dict)       # idem preview + {"universe_db", "applied"}
    # TICKET-033 — annulation volontaire d'une génération (pas une erreur)
    generation_cancelled = Signal(str)
    event_payload_updated = Signal(bool)

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

    def update_event_payload(self, save_id: str, turn_id: int, event_type: str, new_payload: dict) -> None:
        from workers.db_tasks import UpdateEventPayloadTask
        task = UpdateEventPayloadTask(self._db_path, save_id, turn_id, event_type, new_payload)
        task.signals.result.connect(self.event_payload_updated.emit)
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

    def prepare_save_for_play(self, save_db: str) -> None:
        """Resynchronise une save avant lancement (hors main thread, QA-042.6)."""
        task = PrepareSaveTask(save_db)
        task.signals.result.connect(self.save_prepared.emit)
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

    def load_universe_meta(self) -> None:
        task = LoadUniverseMetaTask(self._db_path)
        task.signals.result.connect(self.universe_meta_loaded.emit)
        self._setup_task(task)

    def load_entities_and_rules(self) -> None:
        task = LoadEntitiesAndRulesTask(self._db_path)
        task.signals.result.connect(lambda res: (
            self.entities_loaded.emit(res[0]),
            self.rules_loaded.emit(res[1]),
            self.lore_book_loaded.emit(res[2]),
            self.stat_definitions_loaded.emit(res[3])
        ))
        self._setup_task(task)

    def save_universe_meta(self, meta: dict) -> None:
        """Atomic update of multiple keys in Universe_Meta."""
        task = SaveUniverseMetaTask(self._db_path, meta)
        task.signals.result.connect(lambda _: self.save_complete.emit())
        self._setup_task(task)

    def save_full_universe(self, entities, rules, meta, lore_book, stat_definitions=None, scheduled_events=None, story_setup=None, locations=None, connections=None) -> None:
        task = SaveFullUniverseTask(
            self._db_path, entities, rules, meta, lore_book,
            stat_definitions, scheduled_events, story_setup, locations, connections,
        )
        task.signals.result.connect(lambda _: self.save_complete.emit())
        self._setup_task(task)

    def load_library(self, library_dir: str) -> None:
        task = LoadLibraryTask(self._db_path, library_dir)
        task.signals.result.connect(self.library_loaded.emit)
        self._setup_task(task)

    def load_saves_async(self) -> None:
        task = LoadSavesTask(self._db_path)
        task.signals.result.connect(self.saves_loaded.emit)
        self._setup_task(task)

    def load_full_universe(self, save_id: str = "") -> None:
        """Atomic load of entities, rules, lore book, meta, stat definitions, scheduled events, and optionally history."""
        task = LoadFullUniverseTask(self._db_path, save_id)
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
        task = LoadGlobalPersonasTask(self._db_path)
        task.signals.result.connect(self.personas_loaded.emit)
        self._setup_task(task)

    def save_global_personas(self, personas: list[dict]) -> None:
        task = SaveGlobalPersonasTask(self._db_path, personas)
        task.signals.result.connect(lambda _: self.save_complete.emit())
        self._setup_task(task)  # TICKET-025 : la tâche n'était jamais dispatchée → personas jamais sauvegardées
