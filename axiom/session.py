"""
axiom/session.py

High-level public API of the Axiom engine (headless, zero Qt).

A `Session` composes the engine building blocks (Arbitrator, EventSourcer,
CheckpointManager, VectorMemory) and exposes a synchronous game loop that any
application (GUI, CLI, server) can drive::

    from axiom.session import Session

    # LLM backend: the modpack's (axiom.providers), or pass llm=... explicitly.
    sess = Session("universes/my_world.axiom", save_id)
    result = sess.take_turn("I open the door.", on_token=print)

Streaming happens through the `on_token` callback. The method is synchronous:
on the GUI side, the app wraps it in a QThread (see workers/narrative_worker.py).
"""

from __future__ import annotations

from pathlib import Path
import threading
from typing import Any, Callable

from axiom.arbitrator import ArbitratorResult
from axiom.backends.base import LLMBackend, LLMMessage
from axiom.checkpoint import CheckpointManager
from axiom.events import EventSourcer
from axiom.logger import logger
from axiom.prompts import HISTORY_TURN_CAP
from axiom.universe import Universe
from axiom.db_helpers import (
    get_max_turn_id,
    load_active_entities,
)
from axiom import paths

_DEFAULT_SYSTEM_PROMPT = "You are the narrator of this world."

#: Extra turns loaded beyond HISTORY_TURN_CAP so the prompt's cap always has
#: enough genuine conversation turns to choose from (some turns carry no
#: narrative). Older context is covered by RAG, so there is no need to replay
#: the entire Event_Log every turn.
_HISTORY_LOAD_BUFFER = 5

#: Take a State_Cache snapshot every N turns. Snapshots only speed up
#: rebuild_state_cache / rewind (the rewind UI lists Event_Log turns, not
#: snapshots — see CheckpointManager.list_checkpoints), so this is purely an
#: internal performance bound with no gameplay-visible effect.
_SNAPSHOT_INTERVAL_TURNS = 25

#: Status string emitted right before contextual image generation starts.
#: Exposed as a constant so the GUI can react (e.g. show a placeholder) without
#: matching a hard-coded English message.
IMAGE_GEN_STATUS = "Generating scene illustration..."


def get_auto_canonize(cfg: Any) -> bool:
    """« Canon auto » setting: after each turn, the story is canonized into the save.

    Stored in the existing config, section `mod_settings["axiom.turn"]["auto_canonize"]`
    (AppConfig has no dedicated field yet). Off by default.
    """
    section = (getattr(cfg, "mod_settings", None) or {}).get("axiom.turn")
    return bool(section.get("auto_canonize", False)) if isinstance(section, dict) else False


def set_auto_canonize(cfg: Any, enabled: bool) -> None:
    """Set the « Canon auto » setting on `cfg` (the caller saves the config)."""
    cfg.mod_settings.setdefault("axiom.turn", {})["auto_canonize"] = bool(enabled)


def resolve_llm_backend(
    cfg: Any | None = None,
    *,
    model_override: str | None = None,
    registry: Any | None = None,
) -> LLMBackend:
    """The narration backend of the modpack (single entry point for Session and UIs).

    The narration backend comes exclusively from the `axiom.providers` mod via the
    exclusive slot `axiom.turn:llm_backend` (or the `providers` service for
    auxiliary models). If no provider is available, raises a clear error.
    """
    if registry is None:
        try:
            from axiom.kernel.loader import get_kernel_registry
            registry = get_kernel_registry()
        except Exception:
            registry = None

    if registry is not None:
        try:
            if model_override is None:
                backend = registry.get_slot("axiom.turn:llm_backend")
                if callable(backend):
                    backend = backend()
                if backend:
                    return backend
            providers = registry.get_service("providers")
            if providers is not None and hasattr(providers, "get_backend"):
                return providers.get_backend(cfg, model_override=model_override)
        except Exception as exc:
            logger.warning("LLM provider resolution failed: %s", exc, exc_info=True)

    raise RuntimeError(
        "No AI provider available: the mod 'axiom.providers' is required for narration. "
        "Please enable 'axiom.providers' in the mod settings."
    )


# One auto-canonize job at a time per save (a slow one is not stacked, the turn is skipped).
_CANON_BUSY: set[tuple[str, str]] = set()
_CANON_LOCK = threading.Lock()


def _emit(callback: Callable[[str], None] | None, message: str) -> None:
    """Invoke an optional progress callback, ignoring None."""
    if callback is not None:
        callback(message)


def is_player_death_triggered(result: Any) -> bool:
    """Scan an ArbitratorResult's triggered rules for a Player_Death event."""
    triggered = getattr(result, "triggered_rules", None) or []
    for item in triggered:
        if isinstance(item, dict):
            if item.get("type") == "trigger_event" and "player_death" in str(item.get("event", "")).lower():
                return True
            if item.get("action_type") == "player_death":
                return True
            for action in item.get("actions", []):
                if isinstance(action, dict):
                    if action.get("type") == "trigger_event" and "player_death" in str(action.get("event", "")).lower():
                        return True
                    if action.get("action_type") == "player_death":
                        return True
    return False


class Session:
    """High-level wrapper to play one save of a universe.

    Args:
        universe_path:  Path of the universe file (.axiom / SQLite .db).
        save_id:        Identifier of the active save.
        llm:            Pre-built LLM backend. If None, the modpack's backend
                        (see `resolve_llm_backend`).
        vector_memory:  Vector memory. If None, a `VectorMemory` is created
                        under `<data_dir>/vector/<save_id>` (or the app's
                        default vector folder when data_dir is None).
        data_dir:       Optional data root for path injection (only used for
                        the default VectorMemory).
        mode:           Game mode ('Normal', 'Hardcore', 'Companion').
        hero_llm:       Optional backend for the hero's decision (Companion
                        mode). If None, lazily built from the config (local
                        `extraction_model`), like the worker does.
    """

    def __init__(
        self,
        universe_path: str | Path,
        save_id: str,
        *,
        llm: LLMBackend | None = None,
        vector_memory: Any | None = None,
        data_dir: str | Path | None = None,
        mode: str = "Normal",
        hero_llm: LLMBackend | None = None,
        time_llm: LLMBackend | None = None,
        kernel_registry: Any | None = None,
        cfg: Any | None = None,
    ) -> None:
        self._db_path = str(universe_path)
        self._save_id = save_id
        try:
            from axiom.schema import migrate_schema
            migrate_schema(self._db_path)
        except Exception:
            logger.exception(
                "Schema migrate failed opening %s; session continues", self._db_path
            )
        try:
            from axiom.storage_registry import apply_registered_mod_migrations
            apply_registered_mod_migrations(self._db_path)
        except Exception:
            logger.exception(
                "Mod migrations failed opening %s; session continues", self._db_path
            )
        self._llm = llm
        # Timekeeper backend: an explicit one wins; otherwise build it from the
        # configured "Time Model" (local model if Ollama, gemini_model if Gemini),
        # mirroring how the Companion hero backend is resolved. Falls back to the
        # main narration backend if config/backend construction fails (TICKET-016).
        # (resolved below, once the mod registry is known)
        self._time_llm = time_llm or None
        self._mode = mode
        self._hero_llm = hero_llm
        self._entities: list[dict] | None = None

        self.universe = Universe.load(self._db_path)
        self._system_prompt = self.universe.system_prompt or _DEFAULT_SYSTEM_PROMPT

        # Path injection (Étape 5): an explicit data_dir sandboxes this session's
        # per-game data (vector store + logs) under it. Logs are process-global
        # (singleton logger) so we re-point the file handler here. Without
        # data_dir, fall back to the lazily-resolved roots (which honour the
        # AXIOM_DATA_DIR env var). Cross-cutting config stays machine-global.
        if data_dir is not None:
            data_root = Path(data_dir)
            vector_base = data_root / "vector"
            from axiom import logger as _logger
            _logger.reconfigure(log_dir=data_root / "logs")
        else:
            vector_base = paths.get_vector_dir()
            data_root = paths._data_root()
        self._data_root = data_root
        # Only an injected data_dir scopes the external stores' paths (rewind/fork).
        self._injected_data_root: Path | None = data_root if data_dir is not None else None

        from axiom.config import load_config
        _active_cfg = cfg or load_config()

        if kernel_registry is None:
            if cfg is not None:
                # An explicit config means a dedicated modpack (embedders, tests).
                from axiom.kernel.loader import bootstrap_all_mods
                kernel_registry = bootstrap_all_mods(config=cfg)
            else:
                # One modpack per process (D-4): bootstrapped once, shared by every session.
                from axiom.kernel.loader import get_kernel_registry
                kernel_registry = get_kernel_registry(_active_cfg)
        self._kernel_registry = kernel_registry

        # The save records its modpack; opening it with another one warns (DOC §10.3, D15).
        self.modpack_compatibility: dict[str, Any] = {"compatible": True}
        self.modpack_warning: str = ""
        try:
            from axiom.kernel.loader import get_active_modpack
            from axiom.savestore import check_save_modpack_compatibility, describe_modpack_differences
            compat = check_save_modpack_compatibility(
                self._db_path, get_active_modpack(self._kernel_registry)
            )
            self.modpack_compatibility = compat
            if not compat["compatible"]:
                self.modpack_warning = describe_modpack_differences(compat)
                logger.warning(
                    "Save '%s' was created with a different modpack:\n%s",
                    self._save_id, self.modpack_warning,
                )
        except Exception:
            logger.exception("Modpack check failed for save '%s'; session continues", self._save_id)

        if self._llm is None:
            # Backend of the modpack (axiom.providers -> slot axiom.turn:llm_backend).
            try:
                self._llm = resolve_llm_backend(_active_cfg, registry=self._kernel_registry)
            except Exception:
                logger.warning("No LLM backend could be resolved for this session.", exc_info=True)
                self._llm = None

        if self._time_llm is None and self._llm is not None:
            self._time_llm = self._resolve_time_llm(self._llm)

        if vector_memory is None:
            rag_svc = self._kernel_registry.get_service("rag")
            if rag_svc is not None and hasattr(rag_svc, "get_vector_memory"):
                try:
                    vector_memory = rag_svc.get_vector_memory(save_id, base_dir=vector_base)
                except TypeError:
                    try:
                        vector_memory = rag_svc.get_vector_memory(save_id)
                    except Exception:
                        vector_memory = None
                except Exception:
                    vector_memory = None
        self._vector_memory = vector_memory

        try:
            stat_svc = self._kernel_registry.get_service("stat_dynamics") if self._kernel_registry else None
            if stat_svc and hasattr(stat_svc, "ensure_stat_dynamics"):
                stat_svc.ensure_stat_dynamics(self._db_path, llm)
        except Exception:
            logger.debug("stat dynamics classify-on-start skipped", exc_info=True)
        self._events = EventSourcer(self._db_path)
        self._checkpoints = CheckpointManager(self._db_path)
        self._turn_id = get_max_turn_id(self._db_path, save_id)
        self._intent_pool: dict[str, str] = {}
        self._entity_names: dict[str, str] | None = None
        self._last_lore_hits: list[dict] = []
        self._last_game_state_tag: str = "exploration"
        #: Outcome of the last background « Canon auto » job (info dict or {"error": ...}).
        self.last_auto_canonize: dict | None = None
        from axiom.epoch import get_session_epoch_manager
        self._epoch_manager = get_session_epoch_manager(save_id)

    def _resolve_time_llm(self, default_llm: LLMBackend) -> LLMBackend:
        """Construit le backend du Timekeeper depuis la config (réglage « Time
        Model »). Replie sur le backend principal en cas d'erreur (clé Gemini
        absente, config illisible…) pour ne jamais casser la construction."""
        try:
            from axiom.config import load_config, resolve_time_model
            cfg = load_config()
            return resolve_llm_backend(
                cfg,
                model_override=resolve_time_model(cfg),
                registry=getattr(self, "_kernel_registry", None),
            )
        except Exception:
            return default_llm

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    @property
    def epoch(self) -> int:
        """Current epoch number for the session."""
        return self._epoch_manager.current

    @epoch.setter
    def epoch(self, val: int) -> None:
        self._epoch_manager.set_epoch(val)

    @property
    def turn_id(self) -> int:
        """Number of the last played turn (0 if the game has not started)."""
        return self._turn_id

    @property
    def kernel_registry(self) -> Any | None:
        """Central registry for mod hooks and slots."""
        return self._kernel_registry

    @kernel_registry.setter
    def kernel_registry(self, reg: Any | None) -> None:
        self._kernel_registry = reg

    def submit_intent(self, entity_id: str, intent_text: str) -> None:
        """Submit an action intent to the pool for the current turn."""
        self._intent_pool[entity_id] = intent_text

    def resolve_tick(
        self,
        *,
        on_token: Callable[[str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        temperature: float = 0.7,
        top_p: float = 1.0,
        verbosity_level: str = "balanced",
        hero_entity_id: str | None = None,
    ) -> ArbitratorResult:
        """Resolve every intent currently in the pool as a single tick."""
        _emit(on_status, "Generating narrative…")

        # Capture current pool and step turn_id
        old_turn_id = self._turn_id
        intents = dict(self._intent_pool)
        self._intent_pool.clear()
        self._turn_id += 1

        try:
            if not self.kernel_registry or not self.kernel_registry.has_hook("axiom.kernel:execute_step"):
                from axiom.kernel import NoTurnPipelineInstalledError
                raise NoTurnPipelineInstalledError(
                    "No turn pipeline installed. Ensure 'axiom.turn' mod is loaded."
                )
            history = self._load_history()

            from axiom.kernel import KernelStepContext
            step_context = KernelStepContext(
                save_id=self._save_id,
                step=self._turn_id,
                input=" ".join(intents.values()),
                db_path=self._db_path,
                epoch=self.epoch,
                llm=self._llm,
                time_llm=self._time_llm,
                vector_memory=self._vector_memory,
                stream_token_callback=on_token,
                temperature=temperature,
                top_p=top_p,
                verbosity_level=verbosity_level,
                mode=self._mode,
                hero_entity_id=hero_entity_id,
                intents=intents,
                auto_commit=False,
                session=self,
                history=history,
                system_prompt=self._system_prompt,
            )
            # Unguarded: the real error of the turn (LLM unreachable, cancellation...)
            # reaches the caller unchanged; contributions of other mods are isolated
            # inside the pipeline itself.
            self.kernel_registry.invoke_hook_unguarded("axiom.kernel:execute_step", step_context)
            result = step_context.result
            if result is None:
                raise RuntimeError(
                    "The turn pipeline ran but produced no result for this turn "
                    "(a mod it depends on may have been disabled: see `axiom mods list`)."
                )
        except Exception:
            self._turn_id = old_turn_id
            self._intent_pool.update(intents)
            raise

        # Atomic commit of all turn mutations in a single SQLite transaction
        if getattr(result, "batch", None) is not None:
            from axiom.schema import get_connection
            with get_connection(self._db_path) as conn:
                result.batch.commit_all(conn, self._save_id, self._turn_id)


        # Periodic snapshot
        if self._turn_id > 0 and self._turn_id % _SNAPSHOT_INTERVAL_TURNS == 0:
            try:
                self._events.take_snapshot(self._save_id, self._turn_id)
            except Exception as snap_err:
                from axiom import logger
                logger.warning(f"Periodic snapshot failed at turn {self._turn_id}: {snap_err}")

        # Centralized post-turn pipeline (metadata, living memory, ambiance)
        self._post_turn_pipeline(result)

        _emit(on_status, "Ready.")
        return result

    def take_turn(
        self,
        player_input: str,
        *,
        player_id: str = "player",
        on_token: Callable[[str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        on_hero_decision: Callable[[str], None] | None = None,
        temperature: float = 0.7,
        top_p: float = 1.0,
        verbosity_level: str = "balanced",
        hero_action: str | None = None,
        hero_entity_id: str | None = None,
    ) -> ArbitratorResult:
        """Run a full turn (synchronously) and return the result.

        Wraps `submit_intent` and `resolve_tick` for backward compatibility.
        """
        self._intent_pool.clear()
        self.submit_intent(player_id, player_input)

        if self._mode == "Companion" and hero_action is None:
            _emit(on_status, "Consulting Hero IA…")
            hero_id = self._get_hero_id_from_metadata()
            hero_ent = self._find_hero_entity(hero_id)
            if hero_ent:
                hero_entity_id = hero_ent["entity_id"]
                history = self._load_history()
                hero_action = self._get_hero_decision(hero_ent, history, self._intent_pool)
                _emit(on_hero_decision, hero_action)
                _emit(on_status, f"Hero decides: {hero_action[:30]}…")
                self.submit_intent(hero_entity_id, hero_action)
        elif hero_action and hero_entity_id:
            self.submit_intent(hero_entity_id, hero_action)

        return self.resolve_tick(
            on_token=on_token,
            on_status=on_status,
            temperature=temperature,
            top_p=top_p,
            verbosity_level=verbosity_level,
            hero_entity_id=hero_entity_id,
        )

    def take_turn_multiplayer(
        self,
        intents: dict[str, str],
        *,
        on_token: Callable[[str], None] | None = None,
        on_status: Callable[[str], None] | None = None,
        temperature: float = 0.7,
        top_p: float = 1.0,
        verbosity_level: str = "balanced",
    ) -> ArbitratorResult:
        """Resolve a multiplayer turn: every player intent in a single tick.

        Unlike `take_turn` (solo/Companion), there is no AI hero decision — all
        actors are human players whose intents are submitted together and resolved
        simultaneously by the Arbitrator (narrated in the third person, cf. `mode
        == "Multiplayer"` in `build_narrative_prompt`).
        """
        self._intent_pool.clear()
        for pid, text in intents.items():
            self.submit_intent(pid, text)

        return self.resolve_tick(
            on_token=on_token,
            on_status=on_status,
            temperature=temperature,
            top_p=top_p,
            verbosity_level=verbosity_level,
        )

    def rewind(self, target_turn_id: int) -> dict[str, int]:
        """Bring the save back to its state at turn `target_turn_id`.

        Resynchronises `turn_id`. Returns the summary provided by
        `CheckpointManager.rewind` (which also bumps the save's epoch).
        """
        with paths.session_data_root(self._injected_data_root):
            summary = self._checkpoints.rewind(self._save_id, target_turn_id)
        self._entity_names = None
        self._turn_id = get_max_turn_id(self._db_path, self._save_id)
        return summary

    def load(self, save_id: str) -> None:
        """Switch session to a different save, incrementing session epoch."""
        self._epoch_manager.bump()
        self._save_id = save_id
        from axiom.epoch import get_session_epoch_manager
        self._epoch_manager = get_session_epoch_manager(self._save_id)
        self._epoch_manager.bump()
        self._turn_id = get_max_turn_id(self._db_path, save_id)
        self._entity_names = None
        self._intent_pool.clear()

    def fork(self, player_name: str | None = None, at_turn: int | None = None, **kwargs) -> str:
        """Fork save at current or specified turn into a new save.

        The source save is only read: its epoch is not bumped (a background job of
        the source stays valid). The new save starts with its own epoch."""
        from axiom.saves import fork_save
        target_turn = at_turn if at_turn is not None else self._turn_id
        name = player_name or kwargs.pop("new_save_name", None)
        with paths.session_data_root(self._injected_data_root):
            return fork_save(
                self._db_path,
                self._save_id,
                at_turn=target_turn,
                player_name=name,
                **kwargs,
            )

    def list_checkpoints(self) -> list[int]:
        """List the turns for which a checkpoint (snapshot) exists."""
        return self._checkpoints.list_checkpoints(self._save_id)

    def regenerate_variant(
        self,
        turn_id: int,
        history: list[dict],
        user_message: str,
        temperature: float = 0.7,
        top_p: float = 1.0,
        verbosity_level: str = "balanced",
        player_id: str = "player_1",
        on_token: Callable[[str], None] | None = None,
    ) -> str:
        """Regenerate a variant of turn `turn_id`'s narrative text.

        Replays the same player message to produce an alternative text
        (without re-evaluating rules or stats); the variant is appended to the
        turn's multiverse payload and becomes active. Delegates to
        `axiom.regenerate`.

        Args:
            history: event-sourced history (`user_input`/`narrative_text`)
                     up to the previous turn.
        """
        from axiom.regenerate import regenerate_variant

        return regenerate_variant(
            self._llm,
            self._db_path,
            self._save_id,
            turn_id,
            history,
            system_prompt=self._system_prompt,
            user_message=user_message,
            temperature=temperature,
            top_p=top_p,
            verbosity_level=verbosity_level,
            player_id=player_id,
            on_token=on_token,
        )

    def _read_state_cache(self) -> dict[str, dict[str, str]]:
        """Read materialised stats straight from State_Cache (no rebuild).

        The Arbitrator's `update_state_cache` keeps State_Cache fresh after every
        turn, and the post-chronicler / post-rewind paths rebuild it explicitly,
        so on the hot path (image generation, hero decision) a plain read is
        correct and avoids replaying the Event_Log each turn.

        Fallback: if the cache comes back empty, materialise it once from the
        Event_Log and re-read. In normal play the cache is already populated
        (save genesis / per-turn updates), so this only fires before the very
        first materialisation (e.g. a freshly seeded save).
        """
        from axiom.schema import get_connection

        def _read() -> dict[str, dict[str, str]]:
            with get_connection(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT entity_id, stat_key, stat_value FROM State_Cache "
                    "WHERE save_id = ?;",
                    (self._save_id,),
                ).fetchall()
            out: dict[str, dict[str, str]] = {}
            for entity_id, key, value in rows:
                out.setdefault(entity_id, {})[key] = value
            return out

        stats = _read()
        if not stats:
            self._events.rebuild_state_cache(self._save_id)
            stats = _read()
        return stats

    def current_stats(self) -> dict[str, dict[str, str]]:
        """Current materialised stats per entity (rebuilds the State_Cache).

        Public API: rebuilds the cache from the Event_Log first, so external
        callers always get a guaranteed-consistent snapshot. In-engine hot paths
        use `_read_state_cache()` instead (the cache is already kept fresh).

        Returns:
            Mapping of entity_id to a dict of stat_key to stat_value strings.
        """
        self._events.rebuild_state_cache(self._save_id)
        return self._read_state_cache()

    def _post_turn_pipeline(self, result: ArbitratorResult) -> None:
        """Centralized post-turn pipeline for all frontends (GUI, Web, CLI).

        1. Mise à jour de l'historique et des métadonnées (last_updated, last_lore_hits, game_state_tag).
        2. Déclenchement conditionnel de la living memory (si activée dans AppConfig).
        3. Émission des métadonnées d'ambiance et de tag.
        """
        # 1. Mise à jour de l'historique et des métadonnées
        self._last_lore_hits = getattr(result, "lore_hits", None) or []
        self._last_game_state_tag = getattr(result, "game_state_tag", None) or "exploration"

        try:
            from datetime import datetime, timezone
            from axiom.schema import get_connection
            now_utc = datetime.now(timezone.utc).isoformat()
            with get_connection(self._db_path) as conn:
                conn.execute(
                    "UPDATE Saves SET last_updated = ? WHERE save_id = ?;",
                    (now_utc, self._save_id),
                )
                conn.commit()
        except Exception as db_err:
            logger.warning(f"Failed to update last_updated for save {self._save_id}: {db_err}")

        # 2. Living memory: recorded by the axiom.living_memory mod (after_step hook,
        #    post-commit), nothing to do here.

        # 3. Émission des métadonnées d'ambiance et de tag
        if hasattr(result, "game_state_tag") and not result.game_state_tag:
            result.game_state_tag = self._last_game_state_tag

        # 4. « Canon auto » (single place for Qt, web and CLI).
        self._maybe_auto_canonize(result)

    def _maybe_auto_canonize(self, result: ArbitratorResult) -> bool:
        """Post-commit: canonize this turn's story into the save, in the background,
        when the « Canon auto » setting is on. Skipped on a Hardcore death, on an
        empty narrative, or while a previous canonization of this save still runs.
        Returns True when a job was started."""
        try:
            from axiom.config import load_config
            if not get_auto_canonize(load_config()):
                return False
        except Exception:
            return False
        narrative = (getattr(result, "narrative_text", "") or "").strip()
        if not narrative:
            return False
        if self._mode == "Hardcore" and is_player_death_triggered(result):
            return False
        key = (self._db_path, self._save_id)
        with _CANON_LOCK:
            if key in _CANON_BUSY:
                return False
            _CANON_BUSY.add(key)
        epoch = self.epoch
        db_path = self._db_path

        def _job() -> None:
            try:
                if self.epoch != epoch:  # rewound / reloaded meanwhile
                    return
                from axiom.canonize import canonize_story
                info = canonize_story(db_path, narrative, preview=False)
                self.last_auto_canonize = info
            except Exception as err:
                # A save not linked to a universe folder cannot be canonized: just log.
                logger.info("Auto-canonize skipped: %s", err)
                self.last_auto_canonize = {"error": str(err)}
            finally:
                with _CANON_LOCK:
                    _CANON_BUSY.discard(key)

        threading.Thread(target=_job, name="axiom-auto-canonize", daemon=True).start()
        return True

    def start_living_memory_catchup(self) -> bool:
        """Start a background distillation when the save is several turns past its
        last extracted fact (e.g. after a restart). Returns True if a job started.

        Living memory belongs to the `axiom.living_memory` mod: without it, nothing."""
        lm_svc = self._kernel_registry.get_service("living_memory") if self._kernel_registry else None
        accumulator = getattr(lm_svc, "accumulator", None)
        if accumulator is None or not hasattr(accumulator, "spawn_distillation"):
            return False
        from axiom.config import load_config, memory_mode_is_living
        cfg = load_config()
        if not memory_mode_is_living(cfg):
            return False
        interval = int(getattr(cfg, "memory_fact_interval", 0) or 0)
        facts = lm_svc.get_facts(self._db_path, self._save_id) or []
        last_fact_turn = max((int(getattr(f, "turn_id", 0) or 0) for f in facts), default=0)
        if interval <= 0 or (self._turn_id - last_fact_turn) < interval:
            return False
        accumulator.spawn_distillation(
            self._db_path, self._save_id, self._turn_id,
            cfg=cfg, llm=self._llm, force_catchup=True,
        )
        return True

    def resolve_player_entity_id(self) -> str:
        """Resolve the primary player entity ID for this session."""
        try:
            from axiom.schema import get_connection
            with get_connection(self._db_path) as conn:
                row = conn.execute(
                    "SELECT entity_id FROM Entities "
                    "WHERE COALESCE(entity_role, entity_type) = 'player' AND is_active = 1 LIMIT 1;"
                ).fetchone()
                if row and row[0]:
                    return str(row[0])
        except Exception:
            logger.warning("Could not resolve player entity id", exc_info=True)
        return "player"

    def resolve_verbosity(self) -> str:
        """Narrator verbosity for this session: universe meta if set, else Settings."""
        from axiom.config import get_default_verbosity
        cfg_default = get_default_verbosity()
        try:
            from axiom.schema import get_connection
            with get_connection(self._db_path) as conn:
                row = conn.execute(
                    "SELECT value FROM Universe_Meta WHERE key = 'llm_verbosity';"
                ).fetchone()
                if row and row[0]:
                    val = str(row[0]).strip().lower()
                    if val in ("short", "balanced", "talkative"):
                        return val
        except Exception:
            pass
        return cfg_default

    def get_state_snapshot(
        self,
        include_history: bool = True,
        last_result: ArbitratorResult | None = None,
    ) -> dict[str, Any]:
        """Serialize full session state for presentation layers (Web, GUI, CLI)."""
        import json
        from axiom.db_helpers import load_active_entities, load_definition_stats, get_current_time
        from axiom.schema import get_connection
        from axiom.events import resolve_stat_key
        from axiom.textfmt import fmt_num

        stats = self.current_stats()
        base = load_definition_stats(self._db_path)
        for eid, base_stats in base.items():
            merged = dict(base_stats)
            merged.update(stats.get(eid, {}))
            stats[eid] = merged

        modifiers: list[dict] = []
        has_stats_mod = (
            self._kernel_registry is not None
            and (
                self._kernel_registry.has_hook("axiom.turn:arbitrate_stats")
                or self._kernel_registry.get_service("stat_dynamics") is not None
            )
        )
        if has_stats_mod:
            try:
                stat_svc = self._kernel_registry.get_service("stat_dynamics")
                if stat_svc is not None:
                    modifiers = stat_svc.get_active_modifiers(self._db_path, self._save_id)
                for mod in modifiers:
                    eid = mod["entity_id"]
                    if eid not in stats:
                        continue
                    key = resolve_stat_key(mod["stat_key"], stats[eid])
                    try:
                        current = float(stats[eid].get(key, "0"))
                        stats[eid][key] = fmt_num(current + float(mod["delta"]))
                    except (TypeError, ValueError):
                        continue
            except Exception:
                modifiers = []

        player_entity_id = self.resolve_player_entity_id()
        player_stats = stats.get(player_entity_id) or stats.get("player") or {}
        player_loc = player_stats.get("Location", "")

        entities_meta = {e["entity_id"]: e for e in load_active_entities(self._db_path)}
        entity_list = []
        for eid, estats in stats.items():
            meta = entities_meta.get(eid, {})
            entity_list.append({
                "entity_id": eid,
                "name": meta.get("name") or eid,
                "entity_type": meta.get("entity_type") or "",
                "stats": estats,
            })
        entity_list.sort(key=lambda e: (0 if e["entity_id"] == player_entity_id else 1, e["name"]))

        neighbors = []
        if player_loc:
            from axiom.db_helpers import get_spatial_context
            spatial = get_spatial_context(self._db_path, player_loc)
            if spatial and "connections" in spatial:
                for n in spatial["connections"]:
                    neighbors.append({
                        "location_id": n["location_id"],
                        "name": n["name"],
                        "distance_km": n["distance_km"],
                    })

        time_service = self.kernel_registry.get_service("time") if self.kernel_registry else None
        if time_service and hasattr(time_service, "format_time"):
            time_val = getattr(time_service, "get_current_time", lambda db, s: 0)(self._db_path, self._save_id)
            time_formatted = time_service.format_time(self._db_path, time_val)
        else:
            from axiom.db_helpers import get_current_time
            time_val = get_current_time(self._db_path, self._save_id)
            time_formatted = str(time_val)

        snapshot: dict[str, Any] = {
            "turn_id": self._turn_id,
            "current_stats": stats,
            "entities": entity_list,
            "player_entity_id": player_entity_id,
            "verbosity": self.resolve_verbosity(),
            "current_location": player_loc,
            "spatial_neighbors": neighbors,
            "time_formatted": time_formatted,
            "lore_hits": getattr(self, "_last_lore_hits", []) or [],
            "modifiers": modifiers,
        }

        if last_result is not None:
            snapshot["narrative_text"] = getattr(last_result, "narrative_text", "")
            snapshot["image_path"] = last_result.image_path.name if getattr(last_result, "image_path", None) else None
            snapshot["game_state_tag"] = getattr(last_result, "game_state_tag", "exploration")
            snapshot["hardcore_death"] = (
                self._mode == "Hardcore" and is_player_death_triggered(last_result)
            )
            snapshot["rejected_changes"] = getattr(last_result, "rejected_changes", None) or []
            snapshot["inventory_changes"] = getattr(last_result, "inventory_changes", None) or []
            snapshot["lore_hits"] = getattr(last_result, "lore_hits", None) or []

        if include_history:
            with get_connection(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT turn_id, event_type, payload FROM Event_Log "
                    "WHERE save_id = ? AND event_type IN ('user_input', 'narrative_text', 'hero_intent') "
                    "ORDER BY event_id ASC;",
                    (self._save_id,),
                ).fetchall()
            snapshot["history"] = [
                {
                    "turn_id": r["turn_id"],
                    "event_type": r["event_type"],
                    "payload": json.loads(r["payload"]) if isinstance(r["payload"], str) else r["payload"],
                }
                for r in rows
            ]
            snapshot["universe_name"] = self.universe.name
            player_name = ""
            with get_connection(self._db_path) as conn:
                row = conn.execute("SELECT player_name FROM Saves WHERE save_id = ?;", (self._save_id,)).fetchone()
                if row:
                    player_name = row[0]
            snapshot["player_name"] = player_name
            snapshot["difficulty"] = self._mode
            snapshot["save_id"] = self._save_id
            if self._mode == "Multiplayer":
                try:
                    with get_connection(self._db_path) as conn:
                        player_rows = conn.execute(
                            "SELECT entity_id, name FROM Entities WHERE COALESCE(entity_role, entity_type) = 'player';"
                        ).fetchall()
                    snapshot["players"] = [{"entity_id": r["entity_id"], "name": r["name"]} for r in player_rows]
                except Exception:
                    snapshot["players"] = [{"entity_id": "player", "name": player_name}]

        return snapshot

    def get_memory_snapshot(self) -> dict[str, Any]:
        """Facts + beliefs + mental models for this session."""
        lm_svc = self._kernel_registry.get_service("living_memory") if self._kernel_registry else None
        if lm_svc is None:
            return {
                "disabled": True,
                "turn_id": self._turn_id,
                "facts": [],
                "beliefs": [],
                "mental_models": [],
            }
        facts = lm_svc.get_facts(self._db_path, self._save_id, max_turn_id=self._turn_id)
        beliefs = lm_svc.get_observations(self._db_path, self._save_id, max_turn_id=self._turn_id)
        models = lm_svc.get_models(self._db_path, self._save_id, max_turn_id=self._turn_id)

        return {
            "turn_id": self._turn_id,
            "facts": [
                {
                    "fact_id": f.fact_id,
                    "turn_id": f.turn_id,
                    "fact_type": f.fact_type,
                    "statement": f.statement,
                    "entities": list(f.entities or []),
                    "who": f.who or "",
                }
                for f in facts
            ],
            "beliefs": [
                {
                    "observation_id": o.observation_id,
                    "subject": o.subject or "",
                    "statement": o.statement,
                    "proof_count": o.proof_count,
                    "updated_turn_id": o.updated_turn_id,
                    "trend": o.trend(self._turn_id) if hasattr(o, "trend") else "stable",
                }
                for o in beliefs
            ],
            "mental_models": [
                {
                    "model_id": m.model_id,
                    "subject": m.subject or "",
                    "summary": m.summary,
                    "updated_turn_id": m.updated_turn_id,
                    "stale": getattr(m, "stale", 0),
                }
                for m in models
            ],
        }

    def run_living_memory_extract_now(self, *, force_catchup: bool = False) -> dict[str, Any]:
        """Run synchronous living memory extraction for this session."""
        lm_svc = self._kernel_registry.get_service("living_memory") if self._kernel_registry else None
        if lm_svc is not None:
            res = lm_svc.extract_now(
                self._db_path,
                self._save_id,
                self._turn_id,
                llm=self._llm,
                force_catchup=force_catchup,
            )
            res["memory"] = self.get_memory_snapshot()
            return res
        return {
            "status": "disabled",
            "disabled": True,
            "facts_stored": 0,
            "memory": self.get_memory_snapshot(),
        }

    # ------------------------------------------------------------------
    # Interne
    # ------------------------------------------------------------------

    def _load_history(self) -> list[LLMMessage]:
        """Reconstruit l'historique conversationnel depuis l'Event_Log.

        Group events by turn_id, then build clean user/assistant messages.
        For each turn:
        - All 'user_input' and 'hero_intent' events form the 'user' message.
        - 'narrative_text' forms the 'assistant' message.
        """
        from axiom.schema import get_connection
        
        # Load entity name mappings to resolve IDs to names in history.
        # Cache on the Session object — entities rarely change mid-session.
        if self._entity_names is None:
            try:
                with get_connection(self._db_path) as conn:
                    rows = conn.execute("SELECT entity_id, name FROM Entities;").fetchall()
                    self._entity_names = {r["entity_id"]: r["name"] for r in rows}
            except Exception:
                logger.debug("Entity id→name map load failed; using raw IDs.", exc_info=True)
                self._entity_names = {}
        id_to_name = self._entity_names

        # Only load the recent turns the prompt can actually use (it caps at the
        # newest HISTORY_TURN_CAP turns). Loading the ENTIRE Event_Log every turn
        # was O(turns) per turn → O(turns²) over a long game, for context the
        # prompt then threw away. Older turns are still recalled via RAG.
        # get_events uses turn_id > start, so subtract one extra to be inclusive.
        start_turn = self._turn_id - HISTORY_TURN_CAP - _HISTORY_LOAD_BUFFER - 1
        if start_turn < 0:
            start_turn = -1  # early game: load everything (incl. turn 0 genesis)
        events = self._events.get_events(self._save_id, start_turn_id=start_turn)

        # Group events by turn_id
        turns_map = {}
        for ev in events:
            t_id = ev["turn_id"]
            turns_map.setdefault(t_id, []).append(ev)
            
        history: list[LLMMessage] = []
        for t_id in sorted(turns_map.keys()):
            turn_events = turns_map[t_id]
            
            user_parts = []
            assistant_content = ""
            
            for ev in turn_events:
                etype = ev["event_type"]
                payload = ev["payload"]
                actor_id = ev["target_entity"]
                
                if etype in ("user_input", "hero_intent"):
                    text = payload.get("text", "") if isinstance(payload, dict) else str(payload)
                    if text:
                        # Translate entity ID to name if available
                        actor_name = id_to_name.get(actor_id, actor_id)
                        if actor_name.lower() == "player":
                            actor_name = "Player"
                        user_parts.append(f"[{actor_name}] INTENT: {text}")
                elif etype == "narrative_text":
                    if isinstance(payload, dict):
                        if "variants" in payload:
                            variants = payload.get("variants") or [""]
                            assistant_content = variants[payload.get("active", 0)]
                        else:
                            assistant_content = payload.get("text", "")
                    else:
                        assistant_content = str(payload)
            
            if user_parts:
                if len(user_parts) == 1:
                    # Solo action (whatever the actor's name): keep the raw text,
                    # the grouped format is only for genuinely simultaneous ticks.
                    single_ev = next(e for e in turn_events if e["event_type"] in ("user_input", "hero_intent"))
                    raw_text = single_ev["payload"].get("text", "") if isinstance(single_ev["payload"], dict) else str(single_ev["payload"])
                    user_content = raw_text
                else:
                    user_content = "[SIMULTANEOUS ACTIONS FOR THIS TICK]\n" + "\n".join(user_parts)
                
                history.append({"role": "user", "content": user_content})
                
            if assistant_content:
                history.append({"role": "assistant", "content": assistant_content})
                
        return history


    # ------------------------------------------------------------------
    # Décision du héros (mode Companion) — porté depuis NarrativeWorker
    # ------------------------------------------------------------------

    def _get_entities(self) -> list[dict]:
        """Charge (et met en cache) les entités actives de l'univers."""
        if self._entities is None:
            self._entities = load_active_entities(self._db_path)
        return self._entities

    def _get_hero_id_from_metadata(self) -> str | None:
        """Lit l'ID du héros configuré dans `Universe_Meta` (clé companion_hero_id)."""
        from axiom.schema import get_connection

        try:
            with get_connection(self._db_path) as conn:
                row = conn.execute(
                    "SELECT value FROM Universe_Meta WHERE key = 'companion_hero_id';"
                ).fetchone()
                return row[0] if row and row[0] else None
        except Exception:
            return None

    def _find_hero_entity(self, target_id: str | None = None) -> dict | None:
        """Localise l'entité Héros principale (par ID, puis heuristiques de repli)."""
        entities = self._get_entities()
        if target_id:
            for e in entities:
                if e["entity_id"] == target_id:
                    return e
        # Repli 1 : ID explicite 'hero'
        for e in entities:
            if e["entity_id"].lower() == "hero":
                return e
        # Repli 2 : nom contenant 'hero'
        for e in entities:
            if "hero" in e.get("name", "").lower():
                return e
        # Repli 3 : premier NPC
        for e in entities:
            if e.get("entity_type") == "npc":
                return e
        return None

    def _get_hero_decision(
        self, hero_ent: dict, history: list[LLMMessage], current_intents: dict[str, str]
    ) -> str:
        """Appelle le LLM héros pour décider de son action (modèle local par défaut)."""
        from axiom.config import load_config, resolve_extraction_model
        from axiom.prompts import build_hero_decision_prompt, format_entity_stats_block
        from axiom.schema import get_connection

        hero_llm = self._hero_llm
        if hero_llm is None:
            cfg = load_config()
            # Modèle auxiliaire pour le héros (local si Ollama, gemini_model si Gemini).
            hero_llm = resolve_llm_backend(
                cfg, model_override=resolve_extraction_model(cfg), registry=self._kernel_registry
            )

        player_name = "Player"
        player_persona = ""
        try:
            with get_connection(self._db_path) as conn:
                row = conn.execute(
                    "SELECT player_name, player_persona FROM Saves WHERE save_id = ?;",
                    (self._save_id,),
                ).fetchone()
                if row:
                    player_name = row["player_name"]
                    player_persona = row["player_persona"]
        except Exception:
            # Non-fatal: prompt falls back to default player name/persona. Trace
            # it so a real DB read error is still diagnosable.
            logger.debug("Player name/persona load failed; using defaults.", exc_info=True)

        # Get active entities and their stats
        entities = self._get_entities()
        all_stats = self._read_state_cache()

        # The real player entity id is name-derived (TICKET-043): resolve it
        # from the current intents (first non-hero actor), never assume "player".
        hero_id = hero_ent["entity_id"]
        player_id = next((eid for eid in (current_intents or {}) if eid != hero_id), "player")

        # We always want the hero and the player
        relevant_entity_ids = {hero_id, player_id}

        # And any other NPCs that share the same location (Limit to 3 to prevent bloat)
        player_loc = all_stats.get(player_id, {}).get("Location", "")
        if player_loc:
            npc_count = 0
            for e in entities:
                eid = e["entity_id"]
                etype = e.get("entity_type")
                if etype == "npc" and eid != hero_ent["entity_id"]:
                    entity_loc = all_stats.get(eid, {}).get("Location", "")
                    if entity_loc.lower() == player_loc.lower():
                        if npc_count < 3:
                            relevant_entity_ids.add(eid)
                            npc_count += 1

        # Map entity IDs to names & types
        id_to_name = {}
        id_to_type = {}
        for e in entities:
            id_to_name[e["entity_id"]] = e.get("name", e["entity_id"])
            id_to_type[e["entity_id"]] = e.get("entity_type", "unknown")
        if player_id not in id_to_name:
            id_to_name[player_id] = player_name
            id_to_type[player_id] = "player"

        snapshots = []
        for eid in relevant_entity_ids:
            snapshots.append({
                "entity_id": eid,
                "name": id_to_name.get(eid, eid),
                "entity_type": id_to_type.get(eid, "unknown"),
                "stats": all_stats.get(eid, {})
            })

        hero_stats = format_entity_stats_block(snapshots)
        
        # Enrichissement contextuel pour le héros (RAG + Spatial)
        spatial_ctx = None
        if player_loc:
            from axiom.db_helpers import get_spatial_context
            spatial_ctx = get_spatial_context(self._db_path, player_loc)
            
        rag_chunks = []
        if self._vector_memory:
            rag_res = self._vector_memory.query(self._save_id, hero_ent.get("name", "Hero"), k=2)
            rag_chunks = [r["text"] for r in rag_res if r.get("chunk_type") != "lore"]
        elif self._kernel_registry:
            rag_svc = self._kernel_registry.get_service("rag")
            if rag_svc is not None:
                try:
                    rag_res = rag_svc.query(self._save_id, hero_ent.get("name", "Hero"), k=2)
                    rag_chunks = [r["text"] for r in rag_res if r.get("chunk_type") != "lore"]
                except Exception:
                    pass

        # Map intents to names for readability in the hero prompt
        named_intents = {}
        for eid, intent in (current_intents or {}).items():
            name = id_to_name.get(eid, eid)
            if name.lower() == "player":
                name = player_name
            named_intents[name] = intent

        prompt = build_hero_decision_prompt(
            hero_name=hero_ent.get("name", "Hero"),
            hero_persona=hero_ent.get("description", ""),
            hero_stats=hero_stats,
            history=history,
            rag_chunks=rag_chunks,
            spatial_context=spatial_ctx,
            current_intents=named_intents,
            player_name=player_name,
            player_persona=player_persona,
        )
        resp = hero_llm.complete(prompt, max_tokens=300)
        return resp.narrative_text.strip()

