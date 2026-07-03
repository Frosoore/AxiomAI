"""
axiom/session.py

High-level public API of the Axiom engine (headless, zero Qt).

A `Session` composes the engine building blocks (Arbitrator, EventSourcer,
CheckpointManager, VectorMemory) and exposes a synchronous game loop that any
application (GUI, CLI, server) can drive::

    from axiom.session import Session
    from axiom.config import load_config, build_llm_from_config

    llm = build_llm_from_config(load_config())
    sess = Session("universes/my_world.axiom", save_id, llm=llm)
    result = sess.take_turn("I open the door.", on_token=print)

Streaming happens through the `on_token` callback. The method is synchronous:
on the GUI side, the app wraps it in a QThread (see workers/narrative_worker.py).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from axiom.arbitrator import ArbitratorEngine, ArbitratorResult
from axiom.backends.base import LLMBackend, LLMMessage
from axiom.checkpoint import CheckpointManager
from axiom.events import EventSourcer
from axiom.logger import logger
from axiom.memory import VectorMemory
from axiom.prompts import HISTORY_TURN_CAP
from axiom.universe import Universe
from axiom.db_helpers import (
    load_rules_for_session,
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


def _emit(callback: Callable[[str], None] | None, message: str) -> None:
    """Invoke an optional progress callback, ignoring None."""
    if callback is not None:
        callback(message)


class Session:
    """High-level wrapper to play one save of a universe.

    Args:
        universe_path:  Path of the universe file (.axiom / SQLite .db).
        save_id:        Identifier of the active save.
        llm:            Pre-built LLM backend (see build_llm_from_config).
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
        llm: LLMBackend,
        vector_memory: VectorMemory | None = None,
        data_dir: str | Path | None = None,
        mode: str = "Normal",
        hero_llm: LLMBackend | None = None,
        time_llm: LLMBackend | None = None,
    ) -> None:
        self._db_path = str(universe_path)
        self._save_id = save_id
        self._llm = llm
        # Timekeeper backend: an explicit one wins; otherwise build it from the
        # configured "Time Model" (local model if Ollama, gemini_model if Gemini),
        # mirroring how the Companion hero backend is resolved. Falls back to the
        # main narration backend if config/backend construction fails (TICKET-016).
        self._time_llm = time_llm if time_llm else self._resolve_time_llm(llm)
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

        if vector_memory is None:
            # Optional cross-encoder reranker, opt-in via config (default OFF).
            # Self-disables to a no-op if its model can't load; config failure
            # must never break session construction.
            reranker = None
            try:
                from axiom.config import load_config
                if load_config().memory_reranker_enabled:
                    from axiom.retrieval import CrossEncoderReranker
                    reranker = CrossEncoderReranker()
            except Exception:
                reranker = None
            vector_memory = VectorMemory(
                persist_dir=str(vector_base / save_id), reranker=reranker
            )
        self._vector_memory = vector_memory

        rules = load_rules_for_session(self._db_path)
        self._arbitrator = ArbitratorEngine(self._db_path, rules)
        self._events = EventSourcer(self._db_path)
        self._checkpoints = CheckpointManager(self._db_path)
        self._turn_id = get_max_turn_id(self._db_path, save_id)
        self._intent_pool: dict[str, str] = {}
        self._entity_names: dict[str, str] | None = None

    @staticmethod
    def _resolve_time_llm(default_llm: LLMBackend) -> LLMBackend:
        """Construit le backend du Timekeeper depuis la config (réglage « Time
        Model »). Replie sur le backend principal en cas d'erreur (clé Gemini
        absente, config illisible…) pour ne jamais casser la construction."""
        try:
            from axiom.config import (
                load_config,
                build_llm_from_config,
                resolve_time_model,
            )
            cfg = load_config()
            return build_llm_from_config(cfg, model_override=resolve_time_model(cfg))
        except Exception:
            return default_llm

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    @property
    def turn_id(self) -> int:
        """Number of the last played turn (0 if the game has not started)."""
        return self._turn_id

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
        self._arbitrator.configure(self._llm, self._vector_memory, self._time_llm)
        _emit(on_status, "Generating narrative…")
        history = self._load_history()
        
        self._turn_id += 1
        
        # Capture the current pool and clear it for the next turn
        intents = dict(self._intent_pool)
        self._intent_pool.clear()

        result = self._arbitrator.process_turn(
            save_id=self._save_id,
            turn_id=self._turn_id,
            intents=intents,
            universe_system_prompt=self._system_prompt,
            history=history,
            stream_token_callback=on_token,
            temperature=temperature,
            top_p=top_p,
            verbosity_level=verbosity_level,
            mode=self._mode,
            hero_entity_id=hero_entity_id,
        )
        
        from axiom.db_helpers import get_current_time
        from axiom.config import load_config
        from axiom.chronicler import ChroniclerEngine
        cfg = load_config()

        current_time = get_current_time(self._db_path, self._save_id)
        previous_time = max(0, current_time - result.elapsed_minutes)
        chronicler = ChroniclerEngine(
            llm=self._llm,
            event_sourcer=self._events,
            db_path=self._db_path,
            trigger_interval=cfg.chronicler_minutes_interval,
        )
        if chronicler.should_trigger(current_time, previous_time):
            _emit(on_status, "Simulating off-screen world...")
            chronicler.run(self._save_id, self._turn_id)
            # Le Chronicler appose des events `chronicler_update` ; on rematérialise
            # State_Cache pour que ses changements de monde prennent effet (TICKET-006).
            self._events.rebuild_state_cache(self._save_id)
            self._arbitrator.invalidate_stats_cache()

        # Periodic snapshot so rebuild_state_cache / rewind start from a recent
        # state instead of replaying from turn 0 (no per-turn snapshot existed
        # before — take_snapshot_async was never wired). Best-effort: a failed
        # snapshot must never break a turn.
        if self._turn_id > 0 and self._turn_id % _SNAPSHOT_INTERVAL_TURNS == 0:
            try:
                self._events.take_snapshot(self._save_id, self._turn_id)
            except Exception as snap_err:
                from axiom import logger
                logger.warning(f"Periodic snapshot failed at turn {self._turn_id}: {snap_err}")

        # Contextual image generation
        if cfg.image_generation_enabled:
            _emit(on_status, IMAGE_GEN_STATUS)
            try:
                from axiom.image_generator import ImageGenerator
                img_gen = ImageGenerator(cfg, llm=self._llm)
                
                # Retrieve player location and contextual descriptions.
                # The real player entity id is name-derived (TICKET-043): resolve
                # it from this tick's intents like the Arbitrator does, never
                # assume a literal "player" id.
                player_entity_id = next(
                    (aid for aid in intents if aid != hero_entity_id), "player"
                )
                entities = self._get_entities()
                all_stats = self._read_state_cache()
                player_loc = all_stats.get(player_entity_id, {}).get("Location", "")
                
                spatial_ctx = None
                if player_loc:
                    from axiom.db_helpers import get_spatial_context
                    spatial_ctx = get_spatial_context(self._db_path, player_loc)
                
                location_desc = ""
                if player_loc and spatial_ctx:
                    location_desc = spatial_ctx.get("description", "")
                    
                character_desc_list = []
                for e in entities:
                    eid = e["entity_id"]
                    if eid == player_entity_id:
                        continue
                    entity_loc = all_stats.get(eid, {}).get("Location", "")
                    if entity_loc and entity_loc.lower() == player_loc.lower():
                        name = e.get("name", eid)
                        desc = e.get("description", "")
                        if desc:
                            character_desc_list.append(f"{name}: {desc}")
                character_desc = "\n".join(character_desc_list)
                
                # Generate visual prompt from context
                visual_prompt = img_gen.generate_prompt(
                    narrative_text=result.narrative_text,
                    location_desc=location_desc,
                    character_desc=character_desc,
                    game_state_tag=result.game_state_tag,
                )
                
                # Generate and save the image
                assets_dir = self._data_root / "assets" / self._save_id
                filename = f"turn_{self._turn_id}.png"
                image_path = img_gen.generate_image(visual_prompt, assets_dir, filename)
                result.image_path = image_path
            except Exception as img_err:
                from axiom import logger
                logger.warning(f"Contextual image generation failed: {img_err}")

        # Update last_updated in Saves table to current UTC time
        try:
            from datetime import datetime, timezone
            from axiom.schema import get_connection
            now_utc = datetime.now(timezone.utc).isoformat()
            with get_connection(self._db_path) as conn:
                conn.execute(
                    "UPDATE Saves SET last_updated = ? WHERE save_id = ?;",
                    (now_utc, self._save_id)
                )
                conn.commit()
        except Exception as db_err:
            logger.warning(f"Failed to update last_updated for save {self._save_id}: {db_err}")

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

        Invalidates the Arbitrator's stats cache and resynchronises `turn_id`.
        Returns the summary provided by `CheckpointManager.rewind`.
        """
        summary = self._checkpoints.rewind(self._save_id, target_turn_id)
        self._arbitrator.invalidate_stats_cache()
        self._entity_names = None
        self._turn_id = get_max_turn_id(self._db_path, self._save_id)
        # Les illustrations des tours annulés ne doivent pas réapparaître si on
        # rejoue jusqu'au même numéro de tour (TICKET-048).
        from axiom.savestore import truncate_assets_in
        truncate_assets_in(self._data_root / "assets" / self._save_id, self._turn_id)

        # Update last_updated in Saves table to current UTC time
        try:
            from datetime import datetime, timezone
            from axiom.schema import get_connection
            now_utc = datetime.now(timezone.utc).isoformat()
            with get_connection(self._db_path) as conn:
                conn.execute(
                    "UPDATE Saves SET last_updated = ? WHERE save_id = ?;",
                    (now_utc, self._save_id)
                )
                conn.commit()
        except Exception as db_err:
            logger.warning(f"Failed to update last_updated on rewind for save {self._save_id}: {db_err}")

        return summary

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
        from axiom.config import load_config, build_llm_from_config, resolve_extraction_model
        from axiom.prompts import build_hero_decision_prompt, format_entity_stats_block
        from axiom.schema import get_connection

        hero_llm = self._hero_llm
        if hero_llm is None:
            cfg = load_config()
            # Modèle auxiliaire pour le héros (local si Ollama, gemini_model si Gemini).
            hero_llm = build_llm_from_config(cfg, model_override=resolve_extraction_model(cfg))

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

