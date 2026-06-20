"""
workers/db_tasks.py

Atomic, stateless database tasks for Axiom AI using QRunnable and QThreadPool.
This eliminates the DbWorker state-overwriting anti-pattern.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import traceback
from contextlib import closing
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal

from axiom.backends.base import GenerationCancelled
from axiom.logger import logger
from axiom.events import EventSourcer
from axiom.checkpoint import CheckpointManager
from axiom.schema import get_connection


class TaskSignals(QObject):
    """Signals for QRunnable tasks."""
    result = Signal(object)
    error = Signal(str)
    status = Signal(str)
    cancelled = Signal(str)  # TICKET-033 : annulation volontaire (pas une erreur)
    finished = Signal()


# --- TICKET-033 : registre des générations annulables en cours ----------------
# Le bouton « Annuler » de la barre de statut (MainWindow) ne connaît pas les
# vues : il passe par ce registre process-wide.

_ACTIVE_GENERATIONS: set["BaseDbTask"] = set()
_ACTIVE_LOCK = threading.Lock()


def active_generation_count() -> int:
    """Nombre de générations annulables en cours d'exécution."""
    with _ACTIVE_LOCK:
        return len(_ACTIVE_GENERATIONS)


def cancel_active_generations() -> int:
    """Demande l'arrêt de toutes les générations en cours. Retourne leur nombre.

    Annulation coopérative : effective à la prochaine frontière (attente de
    retry, frontière de chunk/cible) — le travail déjà commité reste.
    """
    with _ACTIVE_LOCK:
        tasks = list(_ACTIVE_GENERATIONS)
    for task in tasks:
        task.cancel()
    return len(tasks)


class BaseDbTask(QRunnable):
    """Base class for all stateless DB tasks."""

    #: TICKET-033 — les tâches de génération longue (LLM) se déclarent
    #: annulables : inscrites au registre dès la construction (une tâche encore
    #: en file QThreadPool doit aussi être touchée par « Annuler »), `cancel()`
    #: arme l'event coopératif transmis au moteur/backend.
    cancellable: bool = False

    def __init__(self, db_path: str):
        super().__init__()
        self.db_path = db_path
        self.signals = TaskSignals()
        self.cancel_event = threading.Event()
        if self.cancellable:
            with _ACTIVE_LOCK:
                _ACTIVE_GENERATIONS.add(self)

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        try:
            # Annulée alors qu'elle attendait encore son thread : ne pas démarrer.
            if self.cancellable and self.cancel_event.is_set():
                raise GenerationCancelled("Generation cancelled before start.")
            result = self.execute()
            self.signals.result.emit(result)
        except GenerationCancelled as exc:
            logger.info(f"DB Task cancelled: {exc}")
            self.signals.cancelled.emit(str(exc))
        except Exception as exc:
            logger.error(f"DB Task Error: {exc}\n{traceback.format_exc()}")
            self.signals.error.emit(str(exc))
        finally:
            if self.cancellable:
                with _ACTIVE_LOCK:
                    _ACTIVE_GENERATIONS.discard(self)
            self.signals.finished.emit()

    def execute(self) -> Any:
        raise NotImplementedError("Subclasses must implement execute()")

    def _sync_definition_source(self) -> None:
        """TICKET-027 : après une écriture de DÉFINITION (Populate, delete entité),
        si la db est le cache d'un univers-dossier, resynchronise l'arbo texte
        (la source reste la vérité). Non bloquant, no-op pour un .db plat."""
        from axiom.library import sync_source_if_any
        sync_source_if_any(self.db_path)


# ---------------------------------------------------------------------------
# Task Implementations
# ---------------------------------------------------------------------------

class LoadStatsTask(BaseDbTask):
    def __init__(self, db_path: str, save_id: str):
        super().__init__(db_path)
        self.save_id = save_id

    def execute(self) -> list[dict]:
        self.signals.status.emit("Loading stats...")
        with get_connection(self.db_path) as conn:
            entity_rows = conn.execute(
                "SELECT e.entity_id, e.name, e.entity_type "
                "FROM Entities e WHERE e.is_active = 1;"
            ).fetchall()

        es = EventSourcer(self.db_path)
        snapshots: list[dict] = []
        for row in entity_rows:
            entity_id = row[0]
            stats = es.get_current_stats(self.save_id, entity_id)
            snapshots.append({
                "entity_id": entity_id,
                "name": row[1],
                "entity_type": row[2],
                "stats": stats,
            })
        return snapshots


class LoadCheckpointsTask(BaseDbTask):
    def __init__(self, db_path: str, save_id: str):
        super().__init__(db_path)
        self.save_id = save_id

    def execute(self) -> list[int]:
        self.signals.status.emit("Loading checkpoints...")
        cm = CheckpointManager(self.db_path)
        return cm.list_checkpoints(self.save_id)


class RewindTask(BaseDbTask):
    def __init__(self, db_path: str, save_id: str, target_turn_id: int):
        super().__init__(db_path)
        self.save_id = save_id
        self.target_turn_id = target_turn_id

    def execute(self) -> dict:
        self.signals.status.emit(f"Rewinding to turn {self.target_turn_id}...")
        
        # Fail-safe: Create an auto-backup before destructive rewind
        from database.backup_manager import create_auto_backup
        create_auto_backup(self.db_path, f"rewind_to_turn_{self.target_turn_id}")
        
        # Truncate assets (illustrations) for rolled back turns (TICKET-048)
        try:
            from axiom import paths
            from axiom.savestore import truncate_assets_in
            assets_dir = paths.get_assets_dir() / self.save_id
            truncate_assets_in(assets_dir, self.target_turn_id)
        except Exception:
            pass

        cm = CheckpointManager(self.db_path)
        return cm.rewind(self.save_id, self.target_turn_id)



class AppendEventTask(BaseDbTask):
    def __init__(self, db_path: str, save_id: str, turn_id: int, etype: str, target: str, payload: Any):
        super().__init__(db_path)
        self.save_id = save_id
        self.turn_id = turn_id
        self.etype = etype
        self.target = target
        self.payload = payload

    def execute(self) -> int:
        es = EventSourcer(self.db_path)
        event_id = es.append_event(
            self.save_id, self.turn_id, self.etype, self.target, self.payload
        )
        return event_id


class LoadSessionHistoryTask(BaseDbTask):
    def __init__(self, db_path: str, save_id: str):
        super().__init__(db_path)
        self.save_id = save_id

    def execute(self) -> tuple[list[dict], int, str]:
        with get_connection(self.db_path) as conn:
            # Fetch difficulty
            row = conn.execute("SELECT difficulty FROM Saves WHERE save_id = ?;", (self.save_id,)).fetchone()
            difficulty = row[0] if row else "Normal"

            rows = conn.execute(
                "SELECT turn_id, event_type, payload FROM Event_Log "
                "WHERE save_id = ? AND event_type IN ('user_input', 'narrative_text', 'hero_intent') "
                "ORDER BY event_id ASC;",
                (self.save_id,)
            ).fetchall()

        history: list[dict] = []
        max_turn_id = 0
        for row in rows:
            turn_id = row[0]
            max_turn_id = max(max_turn_id, turn_id)
            history.append({
                "turn_id": turn_id,
                "event_type": row[1],
                "payload": json.loads(row[2])
            })
        return history, max_turn_id, difficulty


class UpdateVariantTask(BaseDbTask):
    def __init__(self, db_path: str, save_id: str, turn_id: int, index: int):
        super().__init__(db_path)
        self.save_id = save_id
        self.turn_id = turn_id
        self.index = index

    def execute(self) -> str:
        with get_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT payload FROM Event_Log "
                "WHERE save_id = ? AND turn_id = ? AND event_type = 'narrative_text';",
                (self.save_id, self.turn_id)
            ).fetchone()
            
            if not row:
                raise ValueError("Event not found for variant update.")
            
            payload_data = json.loads(row[0])
            if not isinstance(payload_data, dict) or "variants" not in payload_data:
                text = payload_data.get("text", "") if isinstance(payload_data, dict) else str(payload_data)
                payload_data = {"active": 0, "variants": [text]}
            
            payload_data["active"] = self.index
            new_text = payload_data["variants"][self.index]
            
            conn.execute(
                "UPDATE Event_Log SET payload = ? "
                "WHERE save_id = ? AND turn_id = ? AND event_type = 'narrative_text';",
                (json.dumps(payload_data), self.save_id, self.turn_id)
            )
            
            conn.commit()
        return new_text


class UpdateEventPayloadTask(BaseDbTask):
    def __init__(self, db_path: str, save_id: str, turn_id: int, event_type: str, new_payload: dict):
        super().__init__(db_path)
        self.save_id = save_id
        self.turn_id = turn_id
        self.event_type = event_type
        self.new_payload = new_payload

    def execute(self) -> bool:
        self.signals.status.emit("Updating database event...")
        es = EventSourcer(self.db_path)
        return es.update_event_payload(
            self.save_id, self.turn_id, self.event_type, self.new_payload
        )


class DeleteSaveTask(BaseDbTask):

    def __init__(self, db_path: str, save_id: str):
        super().__init__(db_path)
        self.save_id = save_id

    def execute(self) -> bool:
        import shutil
        self.signals.status.emit("Deleting save...")

        # 1. Delete via savestore (§7.6 : la ligne Saves peut vivre dans un
        # fichier séparé — résolution + suppression du fichier s'il se vide).
        from axiom.savestore import delete_save
        delete_save(self.db_path, self.save_id)

        # 2. Delete Vector Memory directory if it exists
        from axiom import paths
        vector_dir = paths.get_vector_dir() / self.save_id
        if vector_dir.exists():
            shutil.rmtree(str(vector_dir))

        self.signals.status.emit("Save deleted.")
        return True


class RenameSaveTask(BaseDbTask):
    def __init__(self, db_path: str, save_id: str, new_name: str):
        super().__init__(db_path)
        self.save_id = save_id
        self.new_name = new_name

    def execute(self) -> bool:
        self.signals.status.emit("Renaming save...")
        # §7.6 : la save peut vivre dans son propre fichier.
        from axiom.savestore import resolve_save_db
        db = resolve_save_db(self.db_path, self.save_id) or self.db_path
        with get_connection(db) as conn:
            conn.execute(
                "UPDATE Saves SET player_name = ? WHERE save_id = ?;",
                (self.new_name, self.save_id)
            )
            conn.commit()
        return True


# ---------------------------------------------------------------------------
# TICKET-028 — gestion des saves depuis le GUI (coquilles fines sur le moteur)
# ---------------------------------------------------------------------------

class PackSaveTask(BaseDbTask):
    """Exporte une save en archive `.axiomsave` (db_path = base UNIVERS)."""

    def __init__(self, db_path: str, save_id: str, output_path: str):
        super().__init__(db_path)
        self.save_id = save_id
        self.output_path = output_path

    def execute(self) -> str:
        from axiom.savestore import pack_save
        self.signals.status.emit("Exporting save...")
        return str(pack_save(self.db_path, self.save_id, self.output_path))


class UnpackSaveTask(BaseDbTask):
    """Importe une archive `.axiomsave` (db_path = base UNIVERS de destination).

    Une archive issue d'un autre univers n'est PAS une erreur fatale : la tâche
    renvoie {"needs_force": True, ...} pour que la vue demande confirmation et
    relance avec force=True.
    """

    def __init__(self, db_path: str, archive_path: str, force: bool = False):
        super().__init__(db_path)
        self.archive_path = archive_path
        self.force = force

    def execute(self) -> dict:
        from axiom.savestore import SaveStoreError, unpack_save
        self.signals.status.emit("Importing save...")
        try:
            return unpack_save(self.archive_path, self.db_path, force=self.force)
        except SaveStoreError as exc:
            if "force" in str(exc) and not self.force:
                return {"needs_force": True, "message": str(exc)}
            raise


class DuplicateSaveTask(BaseDbTask):
    """Duplique une save (= « save manuelle ») — db_path = base UNIVERS."""

    def __init__(self, db_path: str, save_id: str, new_name: str | None = None):
        super().__init__(db_path)
        self.save_id = save_id
        self.new_name = new_name

    def execute(self) -> dict:
        from axiom.savestore import duplicate_save
        self.signals.status.emit("Duplicating save...")
        return duplicate_save(self.db_path, self.save_id, player_name=self.new_name)


class PrepareSaveTask(BaseDbTask):
    """Resynchronise la définition d'une save avant lancement (db_path = save db).

    `refresh_save_definition` peut recompiler la définition (hash + transaction) :
    hors du main thread pour ne pas geler l'UI au clic « Lancer » (QA-042.6).
    Renvoie le chemin de la base, prête à passer à `Session`.
    """

    def execute(self) -> str:
        from axiom.savestore import refresh_save_definition
        self.signals.status.emit("Preparing save...")
        refresh_save_definition(self.db_path)
        return self.db_path


class ExportSaveStateTask(BaseDbTask):
    """Matérialise l'état d'une save en texte `save_state.toml` (pour édition)."""

    def __init__(self, db_path: str, save_id: str):
        super().__init__(db_path)
        self.save_id = save_id

    def execute(self) -> tuple[str, str]:
        import tempfile
        from pathlib import Path
        from axiom.saves import export_save_state
        from axiom.savestore import resolve_save_db

        self.signals.status.emit("Reading save state...")
        db = resolve_save_db(self.db_path, self.save_id) or self.db_path
        tmp = Path(tempfile.gettempdir()) / f"axiom_save_state_{self.save_id}.toml"
        try:
            export_save_state(db, self.save_id, tmp)
            text = tmp.read_text(encoding="utf-8")
        finally:
            tmp.unlink(missing_ok=True)
        return self.save_id, text


class EditSaveStateTask(BaseDbTask):
    """Applique un `save_state.toml` édité comme correction en place.

    Seul le **diff** entre le texte d'origine et le texte édité est apposé
    (events `manual_edit` append-only, rewind préservé). Renvoie le tour de la
    correction, ou -1 si rien n'a changé.
    """

    def __init__(self, db_path: str, save_id: str, original_text: str, edited_text: str):
        super().__init__(db_path)
        self.save_id = save_id
        self.original_text = original_text
        self.edited_text = edited_text

    def execute(self) -> int:
        import tomllib
        from axiom.saves import SaveError, apply_correction, diff_save_states
        from axiom.savestore import resolve_save_db

        self.signals.status.emit("Applying save edit...")
        try:
            before = tomllib.loads(self.original_text)
            after = tomllib.loads(self.edited_text)
        except tomllib.TOMLDecodeError as exc:
            raise SaveError(f"save_state.toml invalide : {exc}") from exc

        patch = diff_save_states(before, after)
        if not any(patch.values()):
            return -1
        db = resolve_save_db(self.db_path, self.save_id) or self.db_path
        return apply_correction(db, self.save_id, patch)


# ---------------------------------------------------------------------------
# TICKET-029 — onglet « Fichiers » du Creator Studio
# ---------------------------------------------------------------------------

class RefreshDefinitionTask(BaseDbTask):
    """Recompile la définition depuis la source texte, in-place dans le `.db`.

    Même sémantique que `axiom dev` : une source malformée lève CompileError
    (remontée en signal error), le `.db` reste inchangé.
    """

    def __init__(self, db_path: str, src_dir: str):
        super().__init__(db_path)
        self.src_dir = src_dir

    def execute(self) -> bool:
        from axiom.dev import refresh_definition
        self.signals.status.emit("Recompiling universe definition...")
        refresh_definition(self.src_dir, self.db_path)
        return True


class ConvertFlatDbTask(BaseDbTask):
    """Convertit un `.db` plat (legacy) en univers-dossier Universe-as-Code."""

    def execute(self) -> dict:
        from axiom.library import convert_flat_db_to_folder
        self.signals.status.emit("Converting universe to source folder...")
        return convert_flat_db_to_folder(self.db_path)


# ---------------------------------------------------------------------------
# TICKET-030 — Populate × Universe-as-Code (sandbox de prévisualisation)
# ---------------------------------------------------------------------------

def _stage_source_change(universe_db: str, mutate: Callable[[str], Any]) -> dict:
    """Joue une mutation de définition dans une sandbox et met en scène le diff.

    Copie le `.db` univers dans un dossier temporaire, applique `mutate` à la
    copie, reconstruit l'arbre source futur (sync db→texte, TICKET-027) et le
    diffe contre la source réelle. RIEN n'est écrit dans l'univers réel : le
    `staged_dir` retourné attend `ApplyStagedSourceTask` (ou un simple rmtree
    de son parent pour annuler). `staged_dir` vide = aucun changement.
    """
    import shutil
    import tempfile
    from pathlib import Path

    from axiom.library import diff_source_trees, sync_source_from_db, universe_root_for
    from core.localization import tr

    src_root = universe_root_for(universe_db)
    if src_root is None:
        raise ValueError(tr("uac_folder_required"))

    stage_root = Path(tempfile.mkdtemp(prefix="axiom_stage_"))
    tmp_db = stage_root / "preview.db"
    with closing(sqlite3.connect(universe_db)) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    shutil.copyfile(universe_db, tmp_db)

    def _synced_copy(name: str) -> Path:
        tree = stage_root / name
        shutil.copytree(src_root, tree,
                        ignore=shutil.ignore_patterns(".axiom-cache", ".git"))
        sync_source_from_db(tmp_db, tree)
        return tree

    # Baseline = la source telle que la sync la normaliserait SANS la mutation :
    # le diff ne montre que l'effet de la génération, pas le bruit de
    # reformatage d'une source écrite à la main.
    baseline = _synced_copy("baseline")
    try:
        result = mutate(str(tmp_db))
        staged = _synced_copy("tree")
    except BaseException:
        # Mutation échouée ou annulée : pas de sandbox orpheline sur le disque.
        shutil.rmtree(stage_root, ignore_errors=True)
        raise
    diffs = diff_source_trees(baseline, staged)
    if not diffs:
        shutil.rmtree(stage_root, ignore_errors=True)
        return {"result": result, "diffs": [], "staged_dir": "", "src_dir": str(src_root)}
    return {"result": result, "diffs": diffs, "staged_dir": str(staged), "src_dir": str(src_root)}


def discard_staged_source(staged_dir: str) -> None:
    """Annule une prévisualisation : supprime la sandbox (db temporaire incluse)."""
    import shutil
    from pathlib import Path

    if staged_dir:
        shutil.rmtree(Path(staged_dir).parent, ignore_errors=True)


class PreviewPopulateTask(BaseDbTask):
    """Populate ciblé en sandbox : génère sur une COPIE et renvoie le diff texte.

    db_path = cache de l'univers-dossier. `targets` ⊆ {meta, stats, entities,
    rules, events, lore}. Le résultat porte `diffs` + `staged_dir` (à appliquer
    via ApplyStagedSourceTask après validation utilisateur).
    """

    cancellable = True  # TICKET-033

    def __init__(self, db_path: str, targets: list[str], mode: str = "auto",
                 custom_text: str | None = None):
        super().__init__(db_path)
        self.targets = targets
        self.mode = mode
        self.custom_text = custom_text

    def execute(self) -> dict:
        from axiom.populate import POPULATE_TARGETS

        def mutate(tmp_db: str) -> dict:
            counts: dict[str, object] = {}
            for target in self.targets:
                if self.cancel_event.is_set():
                    raise GenerationCancelled("Populate preview annulé.")
                fn = POPULATE_TARGETS.get(target)
                if fn is None:
                    continue
                counts[target] = fn(tmp_db, self.mode, self.custom_text,
                                    on_status=self.signals.status.emit,
                                    cancel=self.cancel_event)
            return counts

        info = _stage_source_change(self.db_path, mutate)
        info["counts"] = info.pop("result")
        return info


class ApplyStagedSourceTask(BaseDbTask):
    """Applique un arbre source validé (sandbox) à l'univers réel.

    db_path = cache de l'univers ; `save_db` optionnel = save en cours à
    resynchroniser après application (canonisation en pleine partie).
    """

    def __init__(self, db_path: str, staged_dir: str, src_dir: str,
                 save_db: str | None = None):
        super().__init__(db_path)
        self.staged_dir = staged_dir
        self.src_dir = src_dir
        self.save_db = save_db

    def execute(self) -> bool:
        from axiom.library import apply_staged_source
        from axiom.savestore import refresh_save_definition

        self.signals.status.emit("Applying changes to universe source...")
        apply_staged_source(self.staged_dir, self.src_dir, self.db_path)
        discard_staged_source(self.staged_dir)
        if self.save_db:
            refresh_save_definition(self.save_db)
        return True


def _insert_canon(db: str, entities: list, lore: list) -> dict:
    """Insère les éléments canon extraits (idempotent : les ids/noms connus sont sautés)."""
    import uuid

    from axiom.populate import entity_id_for

    inserted = {"entities": 0, "lore": 0}
    with get_connection(db) as conn:
        existing_ids = {str(r[0]).lower() for r in conn.execute("SELECT entity_id FROM Entities;")}
        for ent in entities or []:
            name = str(ent.get("name", "")).strip()
            if not name:
                continue
            eid = entity_id_for(name)
            if eid in existing_ids:
                continue
            etype = str(ent.get("entity_type", "npc")).lower()
            if etype not in ("npc", "faction"):
                etype = "npc"
            conn.execute(
                "INSERT INTO Entities (entity_id, name, entity_type, description, is_active) "
                "VALUES (?, ?, ?, ?, 1);",
                (eid, name, etype, str(ent.get("description", "")).strip()),
            )
            existing_ids.add(eid)
            inserted["entities"] += 1

        existing_lore = {str(r[0]).lower() for r in conn.execute("SELECT name FROM Lore_Book;")}
        for entry in lore or []:
            name = str(entry.get("name", "")).strip()
            if not name or name.lower() in existing_lore:
                continue
            conn.execute(
                "INSERT INTO Lore_Book (entry_id, category, name, keywords, content) "
                "VALUES (?, ?, ?, ?, ?);",
                (str(uuid.uuid4()), str(entry.get("category", "General")) or "General",
                 name, "", str(entry.get("content", "")).strip()),
            )
            existing_lore.add(name.lower())
            inserted["lore"] += 1
        conn.commit()
    return inserted


class CanonizeStoryTask(BaseDbTask):
    """Canonise l'histoire récente dans la définition de l'UNIVERS (TICKET-030).

    db_path = base de la save en cours (l'univers lié est retrouvé via
    Save_Meta ; une save embarquée dans le cache d'un univers-dossier marche
    aussi). `preview=True` → sandbox + diff à valider ; `preview=False`
    (toggle « canon auto ») → application directe + resync de la save.
    """

    cancellable = True  # TICKET-033

    def __init__(self, db_path: str, narrative_text: str, preview: bool = True):
        super().__init__(db_path)
        self.narrative_text = narrative_text
        self.preview = preview

    def _resolve_universe_db(self) -> str:
        from axiom.library import universe_root_for
        from core.localization import tr
        from axiom.savestore import is_separated_save_db
        from pathlib import Path

        candidate = self.db_path
        if is_separated_save_db(self.db_path):
            with closing(sqlite3.connect(self.db_path)) as conn:
                meta = dict(conn.execute("SELECT key, value FROM Save_Meta;").fetchall())
            candidate = meta.get("universe_db", "")
        if candidate and Path(candidate).is_file() and universe_root_for(candidate):
            return candidate
        raise ValueError(tr("uac_folder_required"))

    def execute(self) -> dict:
        from axiom.config import build_llm_from_config, load_config, resolve_extraction_model
        from axiom.prompts import build_canonize_prompt
        from axiom.savestore import refresh_save_definition

        universe_db = self._resolve_universe_db()

        self.signals.status.emit("Reading universe canon...")
        with get_connection(universe_db) as conn:
            existing_entities = [str(r[0]) for r in conn.execute(
                "SELECT name FROM Entities WHERE is_active = 1;")]
            existing_lore = [str(r[0]) for r in conn.execute("SELECT name FROM Lore_Book;")]
            row = conn.execute(
                "SELECT value FROM Universe_Meta WHERE key = 'global_lore';").fetchone()
            global_lore = row[0] if row else ""

        self.signals.status.emit("Canonizing recent story...")
        cfg = load_config()
        llm = build_llm_from_config(cfg, model_override=resolve_extraction_model(cfg))
        # TICKET-033 : compte à rebours de retry visible + annulation.
        llm.on_status = self.signals.status.emit
        llm.cancel_event = self.cancel_event
        prompt = build_canonize_prompt(
            self.narrative_text, existing_entities, existing_lore, global_lore)
        resp = llm.complete(prompt, response_format="json")
        data = resp.tool_call if isinstance(resp.tool_call, dict) else {}
        entities = data.get("entities", [])
        lore = data.get("lore_entries", [])

        info = _stage_source_change(
            universe_db, lambda tmp_db: _insert_canon(tmp_db, entities, lore))
        info["counts"] = info.pop("result")
        info["universe_db"] = universe_db
        info["applied"] = False

        if not self.preview and info["staged_dir"]:
            from axiom.library import apply_staged_source
            apply_staged_source(info["staged_dir"], info["src_dir"], universe_db)
            discard_staged_source(info["staged_dir"])
            refresh_save_definition(self.db_path)
            info["staged_dir"] = ""
            info["applied"] = True
        return info


class TickModifiersTask(BaseDbTask):
    def __init__(self, db_path: str, save_id: str, elapsed_minutes: int):
        super().__init__(db_path)
        self.save_id = save_id
        self.elapsed_minutes = elapsed_minutes

    def execute(self) -> list[str]:
        from axiom.modifiers import ModifierProcessor
        mp = ModifierProcessor(self.db_path)
        return mp.tick_modifiers(self.save_id, self.elapsed_minutes)


# ---------------------------------------------------------------------------
# Populate* — coquilles fines (migration B3 : la logique vit dans axiom.populate)
# ---------------------------------------------------------------------------

class _BasePopulateTask(BaseDbTask):
    """Coquille Qt commune des générateurs Populate.

    Toute la logique (contexte, prompt, insertion idempotente, sync source
    TICKET-027, reprise par chunk TICKET-031) vit côté moteur dans
    `axiom.populate` — ce wrapper ne fait que déporter l'appel hors du thread
    principal et brancher la progression sur les signaux Qt.
    """

    _TARGET: str = ""  # clé dans axiom.populate.POPULATE_TARGETS
    cancellable = True  # TICKET-033

    def __init__(self, db_path: str, mode: str = "auto", custom_text: str | None = None):
        super().__init__(db_path)
        self.mode = mode
        self.custom_text = custom_text

    def execute(self):
        from axiom.populate import POPULATE_TARGETS
        return POPULATE_TARGETS[self._TARGET](
            self.db_path, self.mode, self.custom_text,
            on_status=self.signals.status.emit,
            cancel=self.cancel_event,
        )


class PopulateMetaTask(_BasePopulateTask):
    """AI-driven metadata refinement (Name, Global Lore, First Message)."""
    _TARGET = "meta"


class PopulateStatsTask(_BasePopulateTask):
    """AI-driven stat definitions generation."""
    _TARGET = "stats"


class PopulateRulesTask(_BasePopulateTask):
    """AI-driven rule generation."""
    _TARGET = "rules"


class PopulateEventsTask(_BasePopulateTask):
    """AI-driven event scheduling."""
    _TARGET = "events"


class PopulateEntitiesTask(_BasePopulateTask):
    """AI-driven entity generation (commit par chunk → reprise, TICKET-031)."""
    _TARGET = "entities"


class PopulateLoreTask(_BasePopulateTask):
    """AI-driven lore expansion."""
    _TARGET = "lore"


class PopulateMapTask(_BasePopulateTask):
    """AI-driven map generation (Locations & Connections)."""
    _TARGET = "map"


class CreatePlayerEntityTask(BaseDbTask):
    """Crée une entité joueur (coquille fine : logique dans axiom.db_helpers, B4).

    Remplace l'ancienne version Qt au corps DUPLIQUÉ (la 2e définition, active,
    référençait `datetime` sans import → NameError latent sur nom vide/collision).
    """

    def __init__(self, db_path: str, name: str, description: str = ""):
        super().__init__(db_path)
        self.name = name
        self.description = description

    def execute(self) -> str:
        from axiom.db_helpers import create_player_entity
        self.signals.status.emit(f"Creating player entity '{self.name}'...")
        eid = create_player_entity(self.db_path, self.name, self.description)
        self.signals.status.emit(f"Player {eid} created.")
        return eid


class LoadInventoryTask(BaseDbTask):
    """Fetch inventory for all active entities."""
    def __init__(self, db_path: str, save_id: str):
        super().__init__(db_path)
        self.save_id = save_id

    def execute(self) -> dict:
        from axiom.db_helpers import get_inventory
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT entity_id FROM Entities WHERE is_active = 1;"
            ).fetchall()
        
        inventory_map = {}
        for row in rows:
            eid = row[0]
            inv = get_inventory(self.db_path, self.save_id, eid)
            if inv:
                inventory_map[eid] = inv
        return inventory_map


class LoadTimelineTask(BaseDbTask):
    """Fetch the event timeline."""
    def __init__(self, db_path: str, save_id: str):
        super().__init__(db_path)
        self.save_id = save_id

    def execute(self) -> list[dict]:
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT turn_id, in_game_time, description FROM Timeline WHERE save_id = ? ORDER BY turn_id DESC;",
                (self.save_id,)
            ).fetchall()
            return [dict(r) for r in rows]


class DeleteEntityTask(BaseDbTask):
    """Permanently deletes an entity and its stats."""
    def __init__(self, db_path: str, entity_id: str):
        super().__init__(db_path)
        self.entity_id = entity_id

    def execute(self) -> bool:
        self.signals.status.emit(f"Deleting entity {self.entity_id}...")
        with get_connection(self.db_path) as conn:
            # Foreign keys ON ensures ON DELETE CASCADE for Entity_Stats
            conn.execute("DELETE FROM Entities WHERE entity_id = ?;", (self.entity_id,))
            conn.commit()
        self._sync_definition_source()
        self.signals.status.emit(f"Entity {self.entity_id} deleted.")
        return True

class LoadStatsAndInventoryTask(BaseDbTask):
    """Fetch both stats and inventory for all active entities."""
    def __init__(self, db_path: str, save_id: str):
        super().__init__(db_path)
        self.save_id = save_id

    def execute(self) -> tuple[list[dict], dict]:
        from axiom.db_helpers import get_inventory
        from axiom.modifiers import ModifierProcessor
        from axiom.events import EventSourcer
        from axiom.schema import get_connection

        # 1. Load Stats (with modifiers)
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT entity_id, name, entity_type FROM Entities WHERE is_active = 1;"
            ).fetchall()
        
        entities = [dict(r) for r in rows]
        sourcer = EventSourcer(self.db_path)
        processor = ModifierProcessor(self.db_path)
        
        stats_list = []
        inventory_map = {}
        
        for ent in entities:
            eid = ent["entity_id"]
            base_stats = sourcer.get_current_stats(self.save_id, eid)
            effective = processor.apply_modifiers(self.save_id, eid, base_stats)
            
            stats_list.append({
                "entity_id": eid,
                "name": ent["name"],
                "entity_type": ent["entity_type"],
                "stats": effective
            })
            
            # 2. Load Inventory
            inv = get_inventory(self.db_path, self.save_id, eid)
            if inv:
                inventory_map[eid] = inv
        
        return stats_list, inventory_map


class ValidateIntegrityTask(BaseDbTask):
    def __init__(self, db_path: str, save_id: str):
        super().__init__(db_path)
        self.save_id = save_id

    def execute(self) -> tuple[bool, dict[str, Any]]:
        self.signals.status.emit("Validating state integrity...")
        es = EventSourcer(self.db_path)
        return es.validate_integrity(self.save_id)


class LoadFullGameStateTask(BaseDbTask):
    """Fetch stats, inventory, and timeline in one go."""
    def __init__(self, db_path: str, save_id: str):
        super().__init__(db_path)
        self.save_id = save_id

    def execute(self) -> tuple[list[dict], dict, list[dict]]:
        from axiom.db_helpers import get_inventory
        from axiom.modifiers import ModifierProcessor
        from axiom.events import EventSourcer
        from axiom.schema import get_connection

        # 1. Load Entities and Stats
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT entity_id, name, entity_type FROM Entities WHERE is_active = 1;"
            ).fetchall()
        
        entities = [dict(r) for r in rows]
        sourcer = EventSourcer(self.db_path)
        processor = ModifierProcessor(self.db_path)
        
        stats_list = []
        inventory_map = {}
        
        for ent in entities:
            eid = ent["entity_id"]
            base_stats = sourcer.get_current_stats(self.save_id, eid)
            effective = processor.apply_modifiers(self.save_id, eid, base_stats)
            
            stats_list.append({
                "entity_id": eid,
                "name": ent["name"],
                "entity_type": ent["entity_type"],
                "stats": effective
            })
            
            inv = get_inventory(self.db_path, self.save_id, eid)
            if inv:
                inventory_map[eid] = inv
        
        # 2. Load Timeline
        timeline_list = []
        with get_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT turn_id, in_game_time, description FROM Timeline WHERE save_id = ? ORDER BY turn_id DESC;",
                (self.save_id,)
            ).fetchall()
            timeline_list = [dict(r) for r in rows]

        return stats_list, inventory_map, timeline_list


# ---------------------------------------------------------------------------
# Universe load/save tasks (extracted from DbWorker's inline "TempTask" pattern)
# ---------------------------------------------------------------------------

# App-M2: the universe-table migrations are idempotent but each opens its own
# connection; running them on every load was wasteful. The schema is stable
# within a process, so we run them once per (process, db_path).
_MIGRATED_DBS: set[str] = set()
_MIGRATE_LOCK = threading.Lock()


def ensure_universe_migrations(db_path: str) -> None:
    """Run the idempotent universe-table migrations once per db_path."""
    with _MIGRATE_LOCK:
        if db_path in _MIGRATED_DBS:
            return
        from axiom.schema import (
            migrate_lore_book_table,
            migrate_stat_definitions_table,
            migrate_entities_table,
            migrate_scheduled_events_table,
            migrate_location_tables,
            migrate_story_setup_table,
        )
        migrate_lore_book_table(db_path)
        migrate_stat_definitions_table(db_path)
        migrate_entities_table(db_path)
        migrate_scheduled_events_table(db_path)
        migrate_location_tables(db_path)
        migrate_story_setup_table(db_path)
        _MIGRATED_DBS.add(db_path)


def _read_stats_by_entity(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    """All Entity_Stats grouped by entity in ONE query (App-M1, was an N+1)."""
    out: dict[str, dict[str, str]] = {}
    for s in conn.execute("SELECT entity_id, stat_key, stat_value FROM Entity_Stats;").fetchall():
        out.setdefault(s["entity_id"], {})[s["stat_key"]] = s["stat_value"]
    return out


class LoadUniverseMetaTask(BaseDbTask):
    """Read all Universe_Meta rows as a dict."""

    def execute(self) -> dict:
        with get_connection(self.db_path) as conn:
            rows = conn.execute("SELECT key, value FROM Universe_Meta;").fetchall()
        return {row[0]: row[1] for row in rows}


class LoadEntitiesAndRulesTask(BaseDbTask):
    """Read entities (+stats), rules, lore book and stat definitions."""

    def execute(self) -> tuple:
        ensure_universe_migrations(self.db_path)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            stats_by_entity = _read_stats_by_entity(conn)
            e_rows = conn.execute("SELECT entity_id, entity_type, name, description FROM Entities WHERE is_active = 1;").fetchall()
            entities = []
            for r in e_rows:
                entities.append({
                    "entity_id": r["entity_id"],
                    "entity_type": r["entity_type"],
                    "name": r["name"],
                    "description": r["description"],
                    "stats": stats_by_entity.get(r["entity_id"], {}),
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


class SaveUniverseMetaTask(BaseDbTask):
    """Atomic update of multiple keys in Universe_Meta."""

    def __init__(self, db_path: str, meta: dict):
        super().__init__(db_path)
        self.meta = meta

    def execute(self) -> bool:
        with closing(sqlite3.connect(self.db_path)) as conn:
            for k, v in self.meta.items():
                conn.execute("INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES (?, ?);", (k, str(v)))
            conn.commit()
        # TICKET-027 : univers-dossier → l'arbo texte reste la vérité.
        self._sync_definition_source()
        return True


class SaveFullUniverseTask(BaseDbTask):
    """Replace the full universe definition (entities, rules, meta, …)."""

    def __init__(self, db_path: str, entities, rules, meta, lore_book,
                 stat_definitions=None, scheduled_events=None, story_setup=None,
                 locations=None, connections=None):
        super().__init__(db_path)
        self.entities = entities
        self.rules = rules
        self.meta = meta
        self.lore_book = lore_book
        self.stat_definitions = stat_definitions
        self.scheduled_events = scheduled_events
        self.story_setup = story_setup
        self.locations = locations
        self.connections = connections

    def execute(self) -> bool:
        ensure_universe_migrations(self.db_path)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute("DELETE FROM Entity_Stats;")
            conn.execute("DELETE FROM Entities;")
            for e in self.entities:
                eid = e.get("entity_id", "").strip()
                if not eid:
                    continue
                conn.execute("INSERT INTO Entities (entity_id, entity_type, name, description, is_active) VALUES (?, ?, ?, ?, 1);",
                           (eid, e.get("entity_type", "npc"), e.get("name", ""), e.get("description", "")))
                for sk, sv in e.get("stats", {}).items():
                    conn.execute("INSERT INTO Entity_Stats (entity_id, stat_key, stat_value) VALUES (?, ?, ?);", (eid, str(sk), str(sv)))

            conn.execute("DELETE FROM Rules;")
            for r in self.rules:
                conn.execute("INSERT INTO Rules (rule_id, priority, conditions, actions, target_entity) VALUES (?, ?, ?, ?, ?);",
                           (r["rule_id"], int(r.get("priority", 0)), json.dumps(r.get("conditions", {})), json.dumps(r.get("actions", [])), r.get("target_entity", "*")))

            conn.execute("DELETE FROM Stat_Definitions;")
            if self.stat_definitions:
                for s in self.stat_definitions:
                    conn.execute("INSERT INTO Stat_Definitions (stat_id, name, description, value_type, parameters) VALUES (?, ?, ?, ?, ?);",
                               (s["stat_id"], s["name"], s.get("description", ""), s["value_type"], json.dumps(s.get("parameters", {}))))

            for k, v in self.meta.items():
                conn.execute("INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES (?, ?);", (k, str(v)))

            conn.execute("DELETE FROM Lore_Book;")
            for l in self.lore_book:
                conn.execute("INSERT INTO Lore_Book (entry_id, category, name, content) VALUES (?, ?, ?, ?);", (l["entry_id"], l.get("category", ""), l.get("name", ""), l.get("content", "")))

            conn.execute("DELETE FROM Scheduled_Events;")
            if self.scheduled_events:
                for ev in self.scheduled_events:
                    conn.execute("INSERT INTO Scheduled_Events (event_id, trigger_minute, title, description) VALUES (?, ?, ?, ?);",
                               (ev["event_id"], int(ev["trigger_minute"]), ev["title"], ev["description"]))

            conn.execute("DELETE FROM Story_Setup;")
            if self.story_setup:
                for ss in self.story_setup:
                    conn.execute(
                        "INSERT INTO Story_Setup (setup_id, question, type, options, max_selections, priority) VALUES (?, ?, ?, ?, ?, ?);",
                        (ss["setup_id"], ss["question"], ss["type"], json.dumps(ss.get("options", [])), ss.get("max_selections", 1), ss.get("priority", 0))
                    )

            conn.execute("DELETE FROM Location_Connections;")
            conn.execute("DELETE FROM Locations;")
            if self.locations:
                for l in self.locations:
                    conn.execute(
                        "INSERT INTO Locations (location_id, name, scale, parent_id, description, x, y) VALUES (?, ?, ?, ?, ?, ?, ?);",
                        (l["location_id"], l["name"], l["scale"], l.get("parent_id"), l.get("description", ""), l.get("x", 0), l.get("y", 0))
                    )
            if self.connections:
                for c in self.connections:
                    conn.execute(
                        "INSERT INTO Location_Connections (source_id, target_id, distance_km) VALUES (?, ?, ?);",
                        (c["source_id"], c["target_id"], int(c["distance_km"]))
                    )
            conn.commit()
        # TICKET-027 : univers-dossier → l'arbo texte reste la vérité.
        self._sync_definition_source()
        return True


class LoadLibraryTask(BaseDbTask):
    """Discover universes in a library directory (flat .db + source folders)."""

    def __init__(self, db_path: str, library_dir: str):
        super().__init__(db_path)
        self.library_dir = library_dir

    def execute(self) -> list:
        from axiom.library import discover_universes
        return discover_universes(self.library_dir)


class LoadSavesTask(BaseDbTask):
    """List a universe's saves (§7.6 : separate saves + legacy embedded)."""

    def execute(self) -> list:
        from axiom.savestore import list_saves
        return list_saves(self.db_path)


class LoadFullUniverseTask(BaseDbTask):
    """Atomic load of entities, rules, lore, meta, stat defs, events, setup,
    history, locations and connections."""

    def __init__(self, db_path: str, save_id: str = ""):
        super().__init__(db_path)
        self.save_id = save_id

    def execute(self) -> tuple:
        ensure_universe_migrations(self.db_path)
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            # 1. Entities (+ stats grouped in one query — App-M1)
            stats_by_entity = _read_stats_by_entity(conn)
            e_rows = conn.execute("SELECT entity_id, entity_type, name, description FROM Entities WHERE is_active = 1;").fetchall()
            entities = []
            for r in e_rows:
                entities.append({
                    "entity_id": r["entity_id"],
                    "entity_type": r["entity_type"],
                    "name": r["name"],
                    "description": r["description"],
                    "stats": stats_by_entity.get(r["entity_id"], {}),
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
            if self.save_id:
                d_row = conn.execute("SELECT difficulty FROM Saves WHERE save_id = ?;", (self.save_id,)).fetchone()
                if d_row:
                    difficulty = d_row[0]

                h_rows = conn.execute("SELECT turn_id, event_type, payload FROM Event_Log WHERE save_id = ? AND event_type IN ('user_input', 'narrative_text', 'hero_intent') ORDER BY event_id ASC;", (self.save_id,)).fetchall()
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


class LoadGlobalPersonasTask(BaseDbTask):
    """Read the Global_Personas table."""

    def execute(self) -> list:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT persona_id, name, description FROM Global_Personas;").fetchall()
        return [dict(r) for r in rows]


class SaveGlobalPersonasTask(BaseDbTask):
    """Replace the Global_Personas table."""

    def __init__(self, db_path: str, personas: list[dict]):
        super().__init__(db_path)
        self.personas = personas

    def execute(self) -> bool:
        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.execute("DELETE FROM Global_Personas;")
            for p in self.personas:
                conn.execute("INSERT INTO Global_Personas (persona_id, name, description) VALUES (?, ?, ?);", (p["persona_id"], p["name"], p["description"]))
            conn.commit()
        return True
