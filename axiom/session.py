"""
axiom/session.py

API publique de haut niveau du moteur Axiom (headless, zéro Qt).

Une `Session` compose les briques du moteur (Arbitrator, EventSourcer,
CheckpointManager, VectorMemory) et expose une boucle de jeu synchrone qu'une
app (GUI, CLI, serveur) peut piloter :

    from axiom.session import Session
    from axiom.config import load_config, build_llm_from_config

    llm = build_llm_from_config(load_config())
    sess = Session("universes/my_world.axiom", save_id, llm=llm)
    result = sess.take_turn("J'ouvre la porte.", on_token=print)

Le streaming se fait via le callback `on_token`. La méthode est synchrone :
côté GUI, l'app l'enveloppe dans un QThread (cf. workers/narrative_worker.py).
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from axiom.arbitrator import ArbitratorEngine, ArbitratorResult
from axiom.backends.base import LLMBackend, LLMMessage
from axiom.checkpoint import CheckpointManager
from axiom.events import EventSourcer
from axiom.memory import VectorMemory
from axiom.universe import Universe
from axiom.db_helpers import (
    load_rules_for_session,
    get_max_turn_id,
    load_active_entities,
)
from axiom import paths

_DEFAULT_SYSTEM_PROMPT = "You are the narrator of this world."


def _emit(callback: Callable[[str], None] | None, message: str) -> None:
    """Invoke an optional progress callback, ignoring None."""
    if callback is not None:
        callback(message)


class Session:
    """Wrapper de haut niveau pour jouer une sauvegarde d'un univers.

    Args:
        universe_path:  Chemin du fichier univers (.axiom / .db SQLite).
        save_id:        Identifiant de la sauvegarde active.
        llm:            Backend LLM déjà construit (cf. build_llm_from_config).
        vector_memory:  Mémoire vectorielle. Si None, une `VectorMemory` est
                        créée sous `<data_dir>/vector/<save_id>` (ou le dossier
                        vector par défaut de l'app si data_dir est None).
        data_dir:       Racine de données optionnelle pour l'injection de chemins
                        (utilisée seulement pour la VectorMemory par défaut).
        mode:           Mode de jeu ('Normal', 'Hardcore', 'Companion').
        hero_llm:       Backend optionnel pour la décision du héros (mode
                        Companion). Si None, construit paresseusement depuis la
                        config (modèle local `extraction_model`), comme le worker.
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
            vector_memory = VectorMemory(persist_dir=str(vector_base / save_id))
        self._vector_memory = vector_memory

        rules = load_rules_for_session(self._db_path)
        self._arbitrator = ArbitratorEngine(self._db_path, rules)
        self._events = EventSourcer(self._db_path)
        self._checkpoints = CheckpointManager(self._db_path)
        self._turn_id = get_max_turn_id(self._db_path, save_id)
        self._intent_pool: dict[str, str] = {}

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
        """Numéro du dernier tour joué (0 si la partie n'a pas commencé)."""
        return self._turn_id

    def submit_intent(self, entity_id: str, intent_text: str) -> None:
        """Soumet une intention d'action au Pool pour le tour courant."""
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
        """Résout toutes les intentions actuellement dans le Pool en un seul Tick."""
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

        # Contextual image generation
        if cfg.image_generation_enabled:
            _emit(on_status, "Generating scene illustration...")
            try:
                from axiom.image_generator import ImageGenerator
                img_gen = ImageGenerator(cfg, llm=self._llm)
                
                # Retrieve player location and contextual descriptions
                entities = self._get_entities()
                all_stats = self.current_stats()
                player_loc = all_stats.get("player", {}).get("Location", "")
                
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
                    if eid == "player":
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
        """Exécute un tour complet (synchrone) et retourne le résultat.
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

    def rewind(self, target_turn_id: int) -> dict[str, int]:
        """Ramène la sauvegarde à son état au tour `target_turn_id`.

        Invalide le cache de stats de l'Arbitrator et resynchronise `turn_id`.
        Retourne le résumé fourni par `CheckpointManager.rewind`.
        """
        summary = self._checkpoints.rewind(self._save_id, target_turn_id)
        self._arbitrator.invalidate_stats_cache()
        self._turn_id = get_max_turn_id(self._db_path, self._save_id)
        return summary

    def list_checkpoints(self) -> list[int]:
        """Liste les tours pour lesquels un checkpoint (snapshot) existe."""
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
        """Régénère une variante du texte narratif du tour `turn_id` (B4).

        Rejoue le même message joueur pour produire un texte alternatif (sans
        réévaluer règles ni stats) ; la variante est ajoutée au payload
        multiverse du tour et devient active. Délègue à `axiom.regenerate`.

        Args:
            history: historique event-sourcé (`user_input`/`narrative_text`)
                     jusqu'au tour précédent.
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

    def current_stats(self) -> dict[str, dict[str, str]]:
        """Stats matérialisées courantes par entité (reconstruit le State_Cache).

        Returns:
            dict `entity_id -> {stat_key: stat_value}`.
        """
        from axiom.schema import get_connection

        self._events.rebuild_state_cache(self._save_id)
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
        
        # Load entity name mappings to resolve IDs to names in history
        id_to_name = {}
        try:
            with get_connection(self._db_path) as conn:
                rows = conn.execute("SELECT entity_id, name FROM Entities;").fetchall()
                id_to_name = {r["entity_id"]: r["name"] for r in rows}
        except Exception:
            pass

        events = self._events.get_events(self._save_id, start_turn_id=-1)
        
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
                if len(user_parts) == 1 and ("Player" in user_parts[0] or "[player]" in user_parts[0].lower()):
                    # Find the exact original text of this single event
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
            pass

        # Get active entities and their stats
        entities = self._get_entities()
        all_stats = self.current_stats()
        
        # We always want the hero and the player
        relevant_entity_ids = {hero_ent["entity_id"], "player"}
        
        # And any other NPCs that share the same location (Limit to 3 to prevent bloat)
        player_loc = all_stats.get("player", {}).get("Location", "")
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
        if "player" not in id_to_name:
            id_to_name["player"] = player_name
            id_to_type["player"] = "player"

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
            rag_chunks = [r["text"] for r in rag_res if r.get("metadata", {}).get("type") != "lore"]

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

