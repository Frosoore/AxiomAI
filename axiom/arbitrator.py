"""
core/arbitrator.py

The ArbitratorEngine — Axiom AI's deterministic firewall between LLM creativity and
the game's mathematical state.

The engine provides the six steps of a turn (gather context, build prompt,
inference, parse, arbitrate, stage mutations). The turn is orchestrated by the
`axiom.turn` mod (hook `axiom.kernel:execute_step`), which is the only
orchestration: `process_turn` dispatches to it. Stat validation and creator rules
live in `axiom.world`, inventory in `axiom.inventory`, time in `axiom.time`.

The Correction Loop (spec §4-B)
---------------------------------
A rejected change queues a hint on the turn (`TurnContext.queue_correction`).
The hint is staged as a `correction_hint` event of that turn in the Event_Log, so
it is save data: it is read back by the VERY NEXT turn only (turn N+1 reads the
hints of turn N) and is undone by a rewind like any other event.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
import json
import re
import sqlite3
from typing import Any
import uuid

from axiom.logger import logger
from axiom.turn_batch import TurnWriteBatch
from axiom.backends.base import LLMBackend, LLMMessage, LLMResponse
from axiom.db_helpers import (
    get_current_time,
    get_spatial_context,
    get_time_of_day_context,
)
from axiom.events import EventSourcer, resolve_stat_key
from axiom.modifiers import ModifierProcessor
from axiom.prompts import (
    HISTORY_TURN_CAP,
    build_narrative_prompt,
    build_timekeeper_prompt,
    format_entity_stats_block,
)
from axiom.schema import get_connection

#: Event_Log type of the narrator hint staged by a turn whose changes were rejected.
CORRECTION_EVENT = "correction_hint"


# Common words ignored when matching a turn's input against Lore_Book keywords
# and entry names — otherwise articles/prepositions (notably the leading "The"
# in most entry names) match nearly every entry and drown the ranking in noise.
_LORE_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "of", "and", "or", "to", "in", "on", "at", "for", "with",
    "is", "are", "was", "were", "be", "by", "as", "it", "its", "this", "that",
    "these", "those", "i", "me", "my", "you", "your", "we", "our", "they",
    "them", "he", "she", "his", "her", "about", "tell", "what", "who", "where",
    "from", "into", "do", "does", "did", "go", "get", "us",
})

# How many *linked* lore entries (same category / shared keywords as a semantic
# seed) are appended after the semantic hits — the Hindsight-inspired link
# expansion for the Lore Book (TICKET-072). Kept small so the prompt's lore
# section stays lean: at most k semantic seeds + this many associative entries.
_LORE_LINK_BUDGET: int = 2

# Upper bound on how many on-scene character names are added to the retrieval
# focus terms (TICKET-073). The location term is always kept; this only caps the
# character names so a crowded location can't bloat the focus set (each term is a
# soft additive boost in VectorMemory.query, so a few names are plenty).
_FOCUS_SCENE_CHARACTER_CAP: int = 5


# ---------------------------------------------------------------------------
# Result & Context types
# ---------------------------------------------------------------------------

@dataclass
class TurnContext:
    """Carries intermediate execution state across the 6 modular turn steps."""

    save_id: str
    step_id: int
    user_input: str
    player_entity_id: str
    verbosity: str

    # Données enrichies au fil des étapes
    spatial_context: dict[str, Any] = field(default_factory=dict)
    retrieved_memory: list[dict[str, Any]] = field(default_factory=list)
    relevant_stats: dict[str, Any] = field(default_factory=dict)
    prompt_messages: list[dict[str, str]] = field(default_factory=list)
    raw_llm_response: str = ""
    parsed_tool_call: dict[str, Any] = field(default_factory=dict)

    # Staging des mutations (cf. TurnWriteBatch de la phase 0d)
    write_batch: TurnWriteBatch = field(default_factory=TurnWriteBatch)
    rejected_changes: list[str] = field(default_factory=list)
    triggered_rules: list[dict[str, Any]] = field(default_factory=list)

    # Paramètres d'exécution & contexte de tour
    intents: dict[str, str] = field(default_factory=dict)
    history: list[LLMMessage] = field(default_factory=list)
    universe_system_prompt: str = ""
    mode: str = "Normal"
    hero_entity_id: str | None = None
    temperature: float = 0.7
    top_p: float = 1.0
    auto_commit: bool = True

    # État intermédiaire transporté entre les étapes
    combined_intents_text: str = ""
    all_stats: dict[str, dict[str, str]] = field(default_factory=dict)
    id_to_name: dict[str, str] = field(default_factory=dict)
    id_to_type: dict[str, str] = field(default_factory=dict)
    player_persona: str = ""
    rag_chunks: list[str] = field(default_factory=list)
    lore_book_subset: list[dict[str, Any]] = field(default_factory=list)
    triggered_events: list[dict[str, Any]] = field(default_factory=list)
    time_ctx: str = ""
    total_mins: int = 0
    local_character_names: list[str] = field(default_factory=list)
    narrative_text: str = ""
    game_state_tag: str = "exploration"
    scene_pace: str = "deliberate"
    elapsed_minutes: int = 1
    new_time: int = 0
    travel_note: str | None = None
    applied_changes: list[dict[str, Any]] = field(default_factory=list)
    rejected_changes_detailed: list[dict[str, Any]] = field(default_factory=list)
    inventory_changes: list[dict[str, Any]] = field(default_factory=list)
    applied_modifiers: list[dict[str, Any]] = field(default_factory=list)
    rule_chain_warning: bool = False
    stat_events: list[dict[str, Any]] = field(default_factory=list)
    session_lore_changes: list[dict[str, Any]] = field(default_factory=list)
    raw_state_changes: list[dict[str, Any]] = field(default_factory=list)
    raw_inventory_changes: list[dict[str, Any]] = field(default_factory=list)
    raw_modifier_changes: list[dict[str, Any]] = field(default_factory=list)
    db_path: str = ""
    #: Narrator hints queued by validators (rejected changes); staged as save data.
    correction_hints: list[str] = field(default_factory=list)
    #: Narration backend, session epoch and epoch reader, for post-commit jobs of mods.
    llm: Any = None
    epoch: int | None = None
    epoch_checker: Callable[[], int] | None = None

    def queue_correction(self, reason: str) -> None:
        """Queue a narrator hint for the next turn (correction loop, spec §4-B)."""
        reason = str(reason or "").strip()
        if reason:
            self.correction_hints.append(
                f"[NARRATOR HINT: The previous action failed because {reason}. "
                "Describe this failure naturally in the story. Do not mention this hint.]"
            )

    @property
    def turn_id(self) -> int:
        return self.step_id

    @turn_id.setter
    def turn_id(self, val: int) -> None:
        self.step_id = val

    @property
    def in_game_minutes_elapsed(self) -> int:
        return self.elapsed_minutes


@dataclass
class ArbitratorResult:
    """The complete output of one ArbitratorEngine turn.

    Attributes:
        narrative_text:   The prose to display to the player.  Always present.
        applied_changes:  State changes that passed validation and were persisted.
        rejected_changes: State changes that failed validation, each augmented
                          with a "reason" key explaining the failure.
        triggered_rules:  Rule actions fired as a consequence of applied changes.
        rule_chain_warning: True if the rules engine reached its iteration limit,
                            indicating a possible infinite loop in creator rules.
        game_state_tag:   The ambiance tag returned by the LLM (e.g. 'exploration').
        player_entity_id: The ID of the player who sent the message for this turn.
        image_path:       The file path of the generated image for this turn.

    """

    narrative_text: str
    applied_changes: list[dict[str, Any]] = field(default_factory=list)
    rejected_changes: list[dict[str, Any]] = field(default_factory=list)
    inventory_changes: list[dict[str, Any]] = field(default_factory=list)
    applied_modifiers: list[dict[str, Any]] = field(default_factory=list)
    triggered_rules: list[dict[str, Any]] = field(default_factory=list)
    rule_chain_warning: bool = False
    game_state_tag: str = "exploration"
    player_entity_id: str = "player"
    elapsed_minutes: int = 1
    scene_pace: str = "deliberate"
    lore_hits: list[dict[str, Any]] = field(default_factory=list)
    image_path: str | None = None
    #: Absolute in-game time (minutes) after this turn — i.e. the value written
    #: to the Timeline. Lets the GUI refresh its clock without a main-thread DB
    #: read (see ui/tabletop_view._on_turn_complete).
    in_game_time: int = 0
    batch: Any = None
    #: Mods disabled during this turn because one of their contributions raised
    #: (mod_id -> reason); the turn went on without them.
    faulted_mods: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ArbitratorEngine
# ---------------------------------------------------------------------------

class ArbitratorEngine:
    """Validates and applies LLM-proposed state changes for one narrative turn.

    Args:
        db_path:            Path to the universe .db for direct entity queries.
        rules_list:         Ignored, kept for API compatibility: creator rules are
                            loaded and evaluated by the `axiom.world` mod.
        kernel_registry:    Registry (or a mod's ModContext) used to fire the turn
                            hooks and read mod services. Required to run a turn.

    """

    def __init__(
        self,
        db_path: str,
        rules_list: list[dict] | None = None,
        kernel_registry: Any | None = None,
    ) -> None:
        self._db_path = db_path
        self._event_sourcer = EventSourcer(db_path)
        self._modifier_processor = ModifierProcessor(db_path)
        self.kernel_registry = kernel_registry

        # Dependencies to be injected via configure()
        self._llm: LLMBackend | None = None
        self._vector_memory: Any | None = None
        self._mode: str = "Normal"
        self._hero_entity_id: str | None = None
        # Saves whose Lore Book has been embedded this session (TICKET-072). Lore
        # is re-embedded once per session (and after a hot reload, which builds a
        # fresh engine) so semantic lore retrieval stays in sync with the source.
        self._lore_synced: set[str] = set()

    def configure(self, llm: LLMBackend, vector_memory: Any | None = None, time_llm: LLMBackend | None = None) -> None:
        """Inject runtime dependencies before process_turn."""
        self._llm = llm
        self._vector_memory = vector_memory
        self._time_llm = time_llm if time_llm is not None else llm

    def invalidate_stats_cache(self) -> None:
        """No-op kept for API compatibility.

        Effective stats (base + modifier overlay) are now re-read from
        State_Cache + Active_Modifiers on every turn (see
        `_fetch_effective_stats`), so there is no stale cross-turn cache to
        clear. Previously this dropped an in-memory snapshot that could keep an
        *expired* modifier's delta baked in until the next chronicler/rewind —
        callers (rewind, post-chronicler) still call this harmlessly.
        """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_turn(
        self,
        save_id: str,
        turn_id: int,
        intents: dict[str, str],
        universe_system_prompt: str,
        history: list[LLMMessage],
        stream_token_callback: Callable[[str], None] | None = None,
        temperature: float = 0.7,
        top_p: float = 1.0,
        verbosity_level: str = "balanced",
        mode: str = "Normal",
        hero_entity_id: str | None = None,
        auto_commit: bool = True,
    ) -> ArbitratorResult:
        """Run one turn with this engine through the installed turn pipeline.

        There is a single orchestration of the turn: the `axiom.kernel:execute_step`
        hook of the `axiom.turn` mod. This method only builds the step context
        (with this engine, its LLM and vector memory) and dispatches it; errors
        (LLM unreachable...) propagate unchanged. Uses `self.kernel_registry`, or the
        process-wide modpack when the engine has none.
        """
        from axiom.kernel import KernelStepContext, NoTurnPipelineInstalledError

        registry = self.kernel_registry
        if registry is None or not hasattr(registry, "invoke_hook_unguarded"):
            from axiom.kernel.loader import get_kernel_registry
            registry = get_kernel_registry()
        if not registry.has_hook("axiom.kernel:execute_step"):
            raise NoTurnPipelineInstalledError(
                "No turn pipeline installed. Ensure 'axiom.turn' mod is loaded."
            )
        step_context = KernelStepContext(
            save_id=save_id,
            step=turn_id,
            input=" ".join(intents.values()) if intents else "",
            db_path=self._db_path,
            llm=self._llm,
            time_llm=getattr(self, "_time_llm", None),
            vector_memory=self._vector_memory,
            stream_token_callback=stream_token_callback,
            temperature=temperature,
            top_p=top_p,
            verbosity_level=verbosity_level,
            mode=mode,
            hero_entity_id=hero_entity_id,
            intents=dict(intents or {}),
            auto_commit=auto_commit,
            history=list(history or []),
            system_prompt=universe_system_prompt,
            extras={"axiom.turn:engine": self},
        )
        registry.invoke_hook_unguarded("axiom.kernel:execute_step", step_context)
        if step_context.result is None:
            raise RuntimeError(
                "The turn pipeline ran but produced no result "
                "(see the mod statuses: `axiom mods list`)."
            )
        return step_context.result

    def step_1_gather_context(self, ctx: TurnContext) -> None:
        """Step 1: Récupération des stats, RAG/mémoire vectorielle, voisins spatiaux et entités pertinentes."""
        self._mode = ctx.mode
        self._hero_entity_id = ctx.hero_entity_id

        player_entity_id = next((aid for aid in ctx.intents if aid != ctx.hero_entity_id), "player") if ctx.intents else "player"
        self._player_entity_id = player_entity_id
        ctx.player_entity_id = player_entity_id
        self._active_actor_ids = list(ctx.intents.keys()) if ctx.intents else [player_entity_id]

        _pending_events = ctx.write_batch.events
        for actor_id, intent_text in ctx.intents.items():
            event_type = "hero_intent" if actor_id == ctx.hero_entity_id else "user_input"
            _pending_events.append((
                ctx.save_id, ctx.turn_id, event_type, actor_id,
                {"text": intent_text}
            ))

        ctx.combined_intents_text = " ".join(ctx.intents.values()) if ctx.intents else ctx.user_input
        ctx.all_stats = self._fetch_effective_stats(ctx.save_id)

        from axiom.config import load_config
        cfg = load_config()

        max_turn_id = max(0, ctx.turn_id - HISTORY_TURN_CAP)

        player_persona = ""
        with get_connection(self._db_path) as conn:
            name_rows = conn.execute("SELECT entity_id, name, entity_type FROM Entities").fetchall()
            id_to_name = {r["entity_id"]: r["name"] for r in name_rows}
            id_to_type = {r["entity_id"]: r["entity_type"] for r in name_rows}
            if "player" not in id_to_name:
                id_to_name["player"] = "Player"
            try:
                row = conn.execute(
                    "SELECT player_persona FROM Saves WHERE save_id = ?;",
                    (ctx.save_id,),
                ).fetchone()
                if row and row["player_persona"]:
                    player_persona = row["player_persona"]
            except sqlite3.Error:
                pass

        ctx.id_to_name = id_to_name
        ctx.id_to_type = id_to_type
        ctx.player_persona = player_persona

        player_loc = ctx.all_stats.get(player_entity_id, {}).get("Location", "")
        focus_terms: list[str] | None = None
        if player_loc:
            terms = [player_loc]
            loc_lower = str(player_loc).lower()
            for eid, stats in ctx.all_stats.items():
                if len(terms) > _FOCUS_SCENE_CHARACTER_CAP:
                    break
                if eid == player_entity_id:
                    continue
                if str(stats.get("Location", "")).lower() != loc_lower:
                    continue
                name = id_to_name.get(eid)
                if name and name.lower() != "player":
                    terms.append(name)
            focus_terms = terms

        rag_results = []
        if self._vector_memory is not None:
            try:
                rag_results = self._vector_memory.query(
                    ctx.save_id,
                    ctx.combined_intents_text,
                    k=cfg.rag_chunk_count,
                    current_turn_id=ctx.turn_id,
                    max_turn_id=max_turn_id,
                    focus_terms=focus_terms,
                    exclude_chunk_type="lore",
                )
            except Exception as exc:
                logger.debug("vector_memory query failed: %s", exc)
                rag_results = []
        elif self.kernel_registry is not None:
            rag_svc = self.kernel_registry.get_service("rag")
            if rag_svc is not None:
                try:
                    rag_results = rag_svc.query(
                        ctx.save_id,
                        ctx.combined_intents_text,
                        k=cfg.rag_chunk_count,
                        current_turn_id=ctx.turn_id,
                        max_turn_id=max_turn_id,
                        focus_terms=focus_terms,
                        exclude_chunk_type="lore",
                    )
                except TypeError:
                    try:
                        rag_results = rag_svc.query(ctx.save_id, ctx.combined_intents_text, k=cfg.rag_chunk_count)
                    except Exception:
                        rag_results = []
                except Exception as exc:
                    logger.debug("Kernel rag service query error: %s", exc)
                    rag_results = []

        ctx.rag_chunks = [
            r["text"] if isinstance(r, dict) and "text" in r else str(r)
            for r in rag_results
            if not (isinstance(r, dict) and r.get("chunk_type") == "lore")
        ]
        ctx.retrieved_memory = rag_results

        relevant_entity_ids = self._identify_relevant_entities(
            ctx.save_id, ctx.combined_intents_text, ctx.history, ctx.rag_chunks, ctx.all_stats
        )
        logger.debug(f"[ARBITRATOR] Identified {len(relevant_entity_ids)} relevant entities: {sorted(list(relevant_entity_ids))}")

        for actor_id in ctx.intents:
            relevant_entity_ids.add(actor_id)
        if not ctx.intents:
            relevant_entity_ids.add("player")

        ctx.relevant_stats = {
            eid: stats for eid, stats in ctx.all_stats.items()
            if eid in relevant_entity_ids
        }

        ctx.total_mins = get_current_time(self._db_path, ctx.save_id)
        ctx.time_ctx = get_time_of_day_context(ctx.total_mins)

        player_loc_id = ctx.relevant_stats.get(player_entity_id, {}).get("Location")
        if player_loc_id:
            ctx.spatial_context = get_spatial_context(self._db_path, player_loc_id) or {}

        ctx.triggered_events = self._fetch_triggered_events(ctx.save_id, ctx.total_mins)

        ctx.local_character_names = []
        if player_loc:
            for eid, stats in ctx.relevant_stats.items():
                loc = stats.get("Location")
                if loc and str(loc).lower() == str(player_loc).lower():
                    name = id_to_name.get(eid, eid)
                    if name.lower() == "player":
                        name = "Player"
                    ctx.local_character_names.append(name)

        ctx.lore_book_subset = self._fetch_relevant_lore(ctx.save_id, ctx.combined_intents_text)

        from axiom.config import memory_beliefs_active, memory_mental_models_active, memory_mode_is_living
        has_living_memory = self._has_service("living_memory")
        if memory_mode_is_living(cfg) and has_living_memory:
            fact_lines = self._fetch_relevant_facts(
                ctx.save_id,
                max_turn_id=ctx.turn_id,
                on_scene=ctx.local_character_names,
                limit=cfg.rag_chunk_count,
            )
            prefix: list[str] = []
            if memory_mental_models_active(cfg):
                model_lines = self._fetch_relevant_mental_models(
                    ctx.save_id,
                    max_turn_id=ctx.turn_id,
                    on_scene=ctx.local_character_names,
                    limit=min(cfg.rag_chunk_count, 4),
                )
                prefix += [f"Profile: {s}" for s in model_lines]
            if memory_beliefs_active(cfg):
                belief_lines = self._fetch_relevant_beliefs(
                    ctx.save_id,
                    max_turn_id=ctx.turn_id,
                    on_scene=ctx.local_character_names,
                    limit=cfg.rag_chunk_count,
                )
                prefix += [f"Belief: {s}" for s in belief_lines]
            prefix += [f"Known fact: {s}" for s in fact_lines]
            if prefix:
                ctx.rag_chunks = prefix + ctx.rag_chunks

        # Fired once per turn, here (the axiom.turn orchestrator does not fire it again).
        self._fire("axiom.step:gather_context", ctx)

    def step_2_build_prompt(self, ctx: TurnContext) -> None:
        """Step 2: Assemblage des sections de prompt (lore, persona, consignes, état du monde)."""
        active_modifiers = self._load_active_modifiers(ctx.save_id)
        dyn_table = {}
        dyn_prompt = ""
        has_stat_dyn = self._has_hook("axiom.turn:arbitrate_stats")
        if has_stat_dyn:
            try:
                from axiom.stat_dynamics import (
                    dynamics_by_key,
                    format_dynamics_prompt,
                    lookup_dynamics,
                    peak_hold_note,
                )
                dyn_table = dynamics_by_key(self._db_path)
                dyn_prompt = format_dynamics_prompt(self._db_path)
            except Exception:
                pass

        now_minutes = ctx.total_mins
        entity_block = format_entity_stats_block(
            [
                {
                    "entity_id": eid,
                    "name": ctx.id_to_name.get(eid, eid),
                    "entity_type": ctx.id_to_type.get(eid, "unknown"),
                    "stats": stats,
                    "modifiers": active_modifiers.get(eid, []),
                    "dyn_notes": {
                        k: peak_hold_note(stats, k, dyn, now_minutes)
                        for k, dyn in (
                            (key, lookup_dynamics(key, dyn_table))
                            for key in stats
                        )
                        if dyn and "peak_hold_note" in locals() and peak_hold_note(stats, k, dyn, now_minutes)
                    } if dyn_table else {},
                }
                for eid, stats in ctx.relevant_stats.items()
            ]
        )
        if dyn_prompt:
            entity_block = f"{entity_block}\n\n{dyn_prompt}"

        named_intents = {ctx.id_to_name.get(eid, eid): intent for eid, intent in (ctx.intents or {}).items()}
        hero_name_str = ctx.id_to_name.get(ctx.hero_entity_id, ctx.hero_entity_id) if ctx.hero_entity_id else None

        from axiom.config import load_config
        cfg = load_config()

        ctx.prompt_messages = build_narrative_prompt(
            universe_system_prompt=ctx.universe_system_prompt,
            entity_stats_block=entity_block,
            # Memories are rendered by the prompt sections of the memory mods.
            rag_chunks=[],
            history=ctx.history,
            intents=named_intents,
            pending_correction=self._load_pending_correction(ctx.save_id, ctx.turn_id),
            player_persona=ctx.player_persona,
            lore_book=ctx.lore_book_subset,
            verbosity_level=ctx.verbosity,
            current_time_str=ctx.time_ctx,
            scheduled_events=ctx.triggered_events,
            spatial_context=ctx.spatial_context if ctx.spatial_context else None,
            mode=self._mode,
            hero_entity_id=hero_name_str,
            local_character_names=ctx.local_character_names,
            basic_prompt=getattr(cfg, "basic_prompt", ""),
            negative_prompt=getattr(cfg, "negative_prompt", ""),
        )

    def step_3_execute_inference(
        self,
        ctx: TurnContext,
        stream_cb: Callable[[str], None] | None = None,
        cancel_event: Any = None,
    ) -> None:
        """Step 3: Appel LLM avec support du streaming token par token et interception de l'annulation."""
        stops = ["\nUser:", "\nPlayer:", "\n[User]", "<|eot_id|>"]
        for actor_id in ctx.intents:
            stops.extend([f"\n{actor_id}:", f"\n[{actor_id}]"])

        verbosity_to_tokens = {
            "short": 150,
            "balanced": 400,
            "talkative": 1024,
        }
        max_tokens = verbosity_to_tokens.get(ctx.verbosity.lower(), 1024)

        if cancel_event is not None and getattr(self._llm, "cancel_event", None) is None:
            self._llm.cancel_event = cancel_event

        llm_response = self._call_llm(
            ctx.prompt_messages,
            stream_cb,
            ctx.temperature,
            ctx.top_p,
            stop_sequences=stops,
            max_tokens=max_tokens,
        )
        ctx.raw_llm_response = llm_response.narrative_text
        ctx.narrative_text = llm_response.narrative_text
        ctx.parsed_tool_call = llm_response.tool_call if isinstance(llm_response.tool_call, dict) else {}

    def step_4_parse_response(self, ctx: TurnContext) -> None:
        """Step 4: Extraction de la narration et parsing résilient du JSON."""
        tool_call = ctx.parsed_tool_call or {}
        if isinstance(tool_call, dict):
            ctx.raw_state_changes = tool_call.get("state_changes", []) or []
            ctx.raw_inventory_changes = tool_call.get("inventory_changes", []) or []
            ctx.raw_modifier_changes = tool_call.get("modifiers", []) or []
            ctx.stat_events = tool_call.get("stat_events", []) or []
            ctx.session_lore_changes = (
                tool_call.get("session_lore")
                or tool_call.get("lore")
                or []
            )
            if not isinstance(ctx.raw_state_changes, list):
                ctx.raw_state_changes = []
            if not isinstance(ctx.raw_inventory_changes, list):
                ctx.raw_inventory_changes = []
            if not isinstance(ctx.raw_modifier_changes, list):
                ctx.raw_modifier_changes = []
            if not isinstance(ctx.stat_events, list):
                ctx.stat_events = []
            if not isinstance(ctx.session_lore_changes, list):
                ctx.session_lore_changes = []
            ctx.game_state_tag = str(tool_call.get("game_state_tag", "exploration")).strip().lower()
            ctx.scene_pace = str(tool_call.get("scene_pace", "deliberate")).strip().lower()

        from axiom.config import load_config
        cfg = load_config()

        has_time_mod = self._has_service("time")

        if not has_time_mod:
            ctx.elapsed_minutes = 0
            ctx.new_time = ctx.total_mins
        else:
            elapsed_minutes: int | None = None
            raw_elapsed = tool_call.get("elapsed_minutes") if "elapsed_minutes" in tool_call else tool_call.get("time_elapsed_minutes")
            if raw_elapsed is not None:
                try:
                    elapsed_minutes = int(raw_elapsed)
                except (ValueError, TypeError):
                    elapsed_minutes = None

            if elapsed_minutes is None and cfg.timekeeper_enabled:
                prompt = build_timekeeper_prompt(ctx.combined_intents_text, ctx.narrative_text)
                try:
                    time_llm = getattr(self, "_time_llm", self._llm)
                    tk_resp = time_llm.complete(prompt, max_tokens=150, temperature=0.1)
                    tk_data = getattr(tk_resp, "tool_call", {}) or {}
                    if not tk_data:
                        tk_text = getattr(tk_resp, "narrative_text", str(tk_resp))
                        match = re.search(r'\{.*\}', tk_text, re.DOTALL)
                        if match:
                            try:
                                tk_data = json.loads(match.group(0))
                            except json.JSONDecodeError:
                                pass
                    if tk_data and "elapsed_minutes" in tk_data:
                        elapsed_minutes = int(tk_data["elapsed_minutes"])
                except Exception as e:
                    logger.error(f"[ARBITRATOR] Timekeeper failed: {e}")

            if elapsed_minutes is None:
                pace_defaults = {
                    "combat": 2,
                    "dialogue": 5,
                    "conversation": 5,
                    "exploration": 15,
                    "travel": 60,
                    "deliberate": 15,
                    "montage": 60,
                    "tension": 10,
                }
                elapsed_minutes = pace_defaults.get(ctx.scene_pace, 15)

            ctx.elapsed_minutes = elapsed_minutes
            ctx.new_time = ctx.total_mins + ctx.elapsed_minutes

    def step_5_arbitrate_rules(self, ctx: TurnContext) -> None:
        """Step 5: arbitrage (hooks des mods monde/stats), modificateurs et lore de session."""
        defined_stats = self._load_defined_stats() if ctx.raw_modifier_changes else set()
        entity_meta = self._load_entity_meta()

        # Stat validation, travel and creator rules: axiom.world (rejections queue
        # their own correction hints on ctx).
        self._fire("axiom.step:arbitrate_mutations", ctx)
        self._fire("axiom.turn:arbitrate_stats", ctx)

        for mod in ctx.raw_modifier_changes:
            if not isinstance(mod, dict):
                continue
            entity_id = self._resolve_entity_id(
                mod.get("entity_id", ""), ctx.all_stats, entity_meta
            )
            stat_key = self._resolve_stat_key(
                str(mod.get("stat_key", "")), ctx.all_stats.get(entity_id, {})
            )
            clear = bool(mod.get("clear"))
            if clear:
                if not entity_id or not stat_key:
                    ctx.queue_correction("Modifier clear missing entity_id or stat_key")
                    continue
                ctx.write_batch.modifier_mutations.append({
                    "type": "clear",
                    "entity_id": entity_id,
                    "stat_key": stat_key,
                })
                ctx.applied_modifiers.append({
                    "entity_id": entity_id,
                    "stat_key": stat_key,
                    "clear": True,
                })
                continue
            try:
                delta = float(mod.get("delta"))
            except (TypeError, ValueError):
                ctx.queue_correction(f"Modifier {entity_id}.{stat_key}: delta must be a number")
                continue
            minutes_raw = mod.get("minutes", mod.get("minutes_remaining", 0))
            try:
                minutes = int(minutes_raw)
            except (TypeError, ValueError):
                minutes = 0
            if minutes < 1:
                ctx.queue_correction(f"Modifier {entity_id}.{stat_key}: minutes must be >= 1")
                continue
            if defined_stats and stat_key.lower() not in defined_stats:
                ctx.queue_correction(f"Modifier {entity_id}.{stat_key}: unknown stat")
                continue
            ctx.write_batch.modifier_mutations.append({
                "type": "add",
                "entity_id": entity_id,
                "stat_key": stat_key,
                "delta": delta,
                "minutes": minutes,
            })
            ctx.applied_modifiers.append({
                "entity_id": entity_id,
                "stat_key": stat_key,
                "delta": delta,
                "minutes": minutes,
            })

        if ctx.session_lore_changes:
            for entry in ctx.session_lore_changes:
                if not isinstance(entry, dict):
                    continue
                name = str(entry.get("name", "")).strip()
                if not name:
                    continue
                entry_id = str(uuid.uuid4())
                category = str(entry.get("category", "General")) or "General"
                keywords = str(entry.get("keywords", "")).strip()
                content = str(entry.get("content", "")).strip()
                ctx.write_batch.lore_entries.append((
                    entry_id, ctx.save_id, category, name, keywords, content, ctx.turn_id
                ))

    def step_6_stage_mutations(self, ctx: TurnContext) -> None:
        """Step 6: Remplissage de ctx.write_batch avec les événements narratifs, les snapshots et les modificateurs."""
        _pending_events = ctx.write_batch.events
        # Timeline (axiom.time), modifier tick (core.stat_dynamics), memory indexing
        # (axiom.rag / axiom.living_memory)...
        self._fire("axiom.step:after_step", ctx)

        # Correction loop: the hint is save data of this turn (rewound with it).
        if ctx.correction_hints:
            _pending_events.append((
                ctx.save_id, ctx.turn_id, CORRECTION_EVENT, "system",
                {"hint": " ".join(ctx.correction_hints)},
            ))

        text_to_log = ctx.combined_intents_text if not ctx.narrative_text.strip() else ctx.narrative_text
        _pending_events.append((
            ctx.save_id, ctx.turn_id, "narrative_text", "system",
            {"active": 0, "variants": [text_to_log]},
        ))

        ctx.write_batch.fired_scheduled_events.extend([ev["event_id"] for ev in ctx.triggered_events])

        if ctx.auto_commit:
            with get_connection(self._db_path) as conn:
                ctx.write_batch.commit_all(conn, ctx.save_id, ctx.turn_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _call_llm(
        self,
        messages: list[LLMMessage],
        stream_token_callback: Callable[[str], None] | None,
        temperature: float = 0.7,
        top_p: float = 1.0,
        stop_sequences: list[str] | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Call the LLM, optionally streaming tokens via a callback.

        When stream_token_callback is None: uses llm.complete() — identical
        to Phase 2 behaviour, all existing tests pass unchanged.

        When stream_token_callback is provided: uses llm.stream_tokens() to
        yield tokens one by one.  Each token is passed to the callback
        (e.g. NarrativeWorker.token_received.emit) for real-time UI updates.
        Tokens are accumulated and assembled into a full string, then
        parse_tool_call() is applied to extract narrative and tool_call JSON.

        Args:
            messages:              The fully built prompt message list.
            stream_token_callback: Optional token handler; None = non-streaming.
            temperature:           Sampling temperature (0.0 to 1.0).
            top_p:                 Nucleus sampling parameter (0.0 to 1.0).
            stop_sequences:        Custom strings to trigger generation stop.
            max_tokens:            Optional limit on the number of tokens to generate.

        Returns:
            LLMResponse with narrative_text, optional tool_call, finish_reason.

        Raises:
            LLMConnectionError: If the LLM is unreachable during streaming.

        """
        if stream_token_callback is None:
            resp = self._llm.complete(
                messages,
                temperature=temperature,
                top_p=top_p,
                stop_sequences=stop_sequences,
                max_tokens=max_tokens
            )
        else:
            # Streaming path
            raw_tokens: list[str] = []
            is_json_block = False
            buffer = ""
            for token in self._llm.stream_tokens(
                messages,
                temperature=temperature,
                top_p=top_p,
                stop_sequences=stop_sequences,
                max_tokens=max_tokens
            ):
                raw_tokens.append(token)
                if not is_json_block:
                    buffer += token
                    match = re.search(r'(~~+json|~~~|```json|```)', buffer)
                    if match:
                        is_json_block = True
                        idx = match.start()
                        if idx > 0:
                            stream_token_callback(buffer[:idx])
                    elif len(buffer) > 15:
                        stream_token_callback(buffer[:-15])
                        buffer = buffer[-15:]

            if not is_json_block and buffer:
                stream_token_callback(buffer)

            full_raw = "".join(raw_tokens)
            narrative, tool_call = self._llm.parse_tool_call(full_raw)
            resp = LLMResponse(
                narrative_text=narrative,
                tool_call=tool_call,
                finish_reason=self._llm.last_finish_reason,
            )

        # Apply narrator-specific "Trim Sentences" post-processing
        from axiom.config import load_config
        try:
            config = load_config()
            if getattr(config, "trim_sentences", True):
                # Trim if finish_reason is length OR if the narrative text does not end with a sentence terminator
                is_incomplete = not re.search(r'[.!?。！？]+["\'”»\s\)]*$', resp.narrative_text.strip())
                if resp.finish_reason == "length" or is_incomplete:
                    resp.narrative_text = LLMResponse._trim_incomplete_sentence(resp.narrative_text)
        except Exception:
            pass

        return resp

    def _fetch_effective_stats(self, save_id: str) -> dict[str, dict[str, str]]:
        """Fetch all active entity stats and apply modifier overlays.

        Uses two global queries (one for all stats, one for all modifiers) in a
        single connection instead of per-entity round-trips.

        Args:
            save_id: The active save identifier.

        Returns:
            Dict mapping entity_id -> effective stats dict.

        """
        from axiom.textfmt import fmt_num
        with get_connection(self._db_path) as conn:
            stat_rows = conn.execute(
                "SELECT entity_id, stat_key, stat_value FROM State_Cache WHERE save_id = ?;",
                (save_id,),
            ).fetchall()
            mod_rows = conn.execute(
                """
                SELECT entity_id, stat_key, delta
                FROM Active_Modifiers
                WHERE save_id = ?;
                """,
                (save_id,),
            ).fetchall()

        from axiom.db_helpers import load_definition_stats
        base: dict[str, dict[str, str]] = {
            eid: dict(stats) for eid, stats in load_definition_stats(self._db_path).items()
        }
        for r in stat_rows:
            base.setdefault(r["entity_id"], {})[r["stat_key"]] = r["stat_value"]

        effective = {eid: dict(stats) for eid, stats in base.items()}
        for r in mod_rows:
            if r["entity_id"] in effective:
                stat_key = resolve_stat_key(r["stat_key"], effective[r["entity_id"]])
                current_raw = effective[r["entity_id"]].get(stat_key, "0")
                try:
                    current = float(current_raw)
                    effective[r["entity_id"]][stat_key] = fmt_num(current + r["delta"])
                except ValueError:
                    pass
        return effective

    def _load_active_modifiers(self, save_id: str) -> dict[str, list[dict[str, Any]]]:
        """Active temporary modifiers grouped by entity_id (for the turn prompt)."""
        try:
            with get_connection(self._db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT entity_id, stat_key, delta, minutes_remaining
                    FROM Active_Modifiers WHERE save_id = ?;
                    """,
                    (save_id,),
                ).fetchall()
        except sqlite3.Error:
            return {}
        out: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            out.setdefault(r["entity_id"], []).append({
                "stat_key": r["stat_key"],
                "delta": r["delta"],
                "minutes_remaining": r["minutes_remaining"],
            })
        return out

    def _identify_relevant_entities(
        self,
        save_id: str,
        user_message: str,
        history: list[LLMMessage],
        rag_chunks: list[str],
        all_stats: dict[str, dict[str, str]],
    ) -> set[str]:
        """Identify relevant entities based on mentions, type, and location.

        Always includes:
        - Entities explicitly mentioned in the recent context.
        - Entities of type 'world' or 'faction' (global context).
        - NPCs that share the same 'Location' stat as ANY active player (in
          multiplayer the players may be split across several locations).
        """
        # 1. Mentions-based detection
        text_to_scan = user_message.lower()
        for msg in history[-3:]:
            text_to_scan += " " + msg["content"].lower()
        for chunk in rag_chunks:
            text_to_scan += " " + chunk.lower()

        words_in_text = set(re.findall(r"\b\w+\b", text_to_scan))

        with get_connection(self._db_path) as conn:
            rows = conn.execute("SELECT entity_id, entity_type FROM Entities;").fetchall()
            # Map lowercase ID -> Original ID
            original_case_map = {row[0].lower(): row[0] for row in rows}
            id_to_type = {row[0]: row[1] for row in rows}
            all_ids_lower = set(original_case_map.keys())

        matched_ids = {original_case_map[ml] for ml in words_in_text.intersection(all_ids_lower)}

        # 2. Location-based and Type-based inclusion
        relevant = set(matched_ids)

        # Collect every active player's location (multiplayer: players may be
        # split across the map). Falls back to the single primary player.
        actor_ids = getattr(self, "_active_actor_ids", None) or [
            getattr(self, "_player_entity_id", "player")
        ]
        player_locs = {
            loc
            for aid in actor_ids
            if (loc := all_stats.get(aid, {}).get("Location", "").lower())
        }

        # Cap NPCs PER location so a crowded scene can't bloat context, while
        # still covering each player's surroundings.
        npc_count_per_loc: dict[str, int] = {}
        for eid, etype in id_to_type.items():
            # Include all global entities
            if etype in ("world", "faction"):
                relevant.add(eid)
                continue

            # Include NPCs at the same location as any active player (Limit 3/loc)
            if etype == "npc" and player_locs:
                entity_loc = all_stats.get(eid, {}).get("Location", "").lower()
                if entity_loc in player_locs and npc_count_per_loc.get(entity_loc, 0) < 3:
                    relevant.add(eid)
                    npc_count_per_loc[entity_loc] = npc_count_per_loc.get(entity_loc, 0) + 1

        return relevant

    def _fetch_triggered_events(self, save_id: str, current_minute: int) -> list[dict]:
        """Fetch global scheduled events that have triggered but not yet fired for this save."""
        events = []
        try:
            with get_connection(self._db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT e.event_id, e.title, e.description
                    FROM Scheduled_Events e
                    LEFT JOIN Fired_Scheduled_Events f ON e.event_id = f.event_id AND f.save_id = ?
                    WHERE e.trigger_minute <= ? AND f.event_id IS NULL;
                    """,
                    (save_id, current_minute)
                ).fetchall()
                events = [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"[ARBITRATOR] Error fetching scheduled events: {e}")
        return events

    def _fetch_relevant_facts(
        self,
        save_id: str,
        max_turn_id: int,
        on_scene: list[str],
        limit: int,
    ) -> list[str]:
        """Return up to `limit` fact statements for the living-mode prompt.

        Prioritises facts that mention an on-scene character (what we *know*
        about who's here), then fills the remainder with the most recent facts.
        Bounded by `max_turn_id` so a rewound turn never resurfaces a future
        fact. Degrades to an empty list on any error (never breaks a turn).
        """
        if limit <= 0:
            return []
        try:
            from axiom import facts as facts_mod

            # One fetch (most-recent-first), then prioritise in memory — instead
            # of one full-table query per on-scene name (TICKET-079).
            all_facts = facts_mod.get_facts(
                self._db_path, save_id, max_turn_id=max_turn_id
            )
            names = {n.strip().lower() for n in (on_scene or []) if n}

            seen: set[str] = set()
            ordered: list[str] = []

            def _add_if(predicate) -> None:
                for f in all_facts:
                    if len(ordered) >= limit:
                        break
                    if not f.statement or f.statement in seen or not predicate(f):
                        continue
                    seen.add(f.statement)
                    ordered.append(f.statement)

            # Pass 1: facts mentioning a character on scene (what we *know* about
            # who's here). Pass 2: fill the remainder with the most recent.
            if names:
                _add_if(lambda f: any(e.strip().lower() in names for e in f.entities))
            _add_if(lambda f: True)

            return ordered[:limit]
        except Exception as e:
            logger.error(f"[ARBITRATOR] Error fetching living-mode facts: {e}")
            return []

    def _fetch_relevant_beliefs(
        self,
        save_id: str,
        max_turn_id: int,
        on_scene: list[str],
        limit: int,
    ) -> list[str]:
        """Return up to `limit` belief statements for the living-mode prompt.

        Prioritises beliefs about an on-scene character (what this scene's people
        *think/remember*), then fills with the most recently updated beliefs.
        Bounded by `max_turn_id` (a rewound turn never resurfaces a future
        belief). Each statement is tagged with its trend when it carries a signal
        (e.g. "… (strengthening)"), so the narrator can tell an intensifying
        belief from a fading one (TICKET-081). Degrades to an empty list on any
        error (never breaks a turn).
        """
        if limit <= 0:
            return []
        try:
            from axiom import observations as obs_mod

            # One fetch (most-recently-updated first), then prioritise in memory
            # instead of one full-table query per on-scene name (TICKET-079).
            all_obs = obs_mod.get_observations(
                self._db_path, save_id, max_turn_id=max_turn_id
            )
            names = {n.strip().lower() for n in (on_scene or []) if n}

            # Annotate only the directional trends — strengthening/weakening/stale
            # carry narrative signal; stable/new are the quiet default, left plain
            # to keep the prompt lean.
            _SIGNAL_TRENDS = (
                obs_mod.TREND_STRENGTHENING,
                obs_mod.TREND_WEAKENING,
                obs_mod.TREND_STALE,
            )

            def _format(o) -> str:
                trend = o.trend(max_turn_id)
                return f"{o.statement} ({trend})" if trend in _SIGNAL_TRENDS else o.statement

            seen: set[str] = set()
            ordered: list[str] = []

            def _add_if(predicate) -> None:
                for o in all_obs:
                    if len(ordered) >= limit:
                        break
                    if not o.statement or o.statement in seen or not predicate(o):
                        continue
                    seen.add(o.statement)
                    ordered.append(_format(o))

            # Pass 1: beliefs about a character on scene. Pass 2: most recent.
            if names:
                _add_if(lambda o: o.subject.strip().lower() in names)
            _add_if(lambda o: True)

            return ordered[:limit]
        except Exception as e:
            logger.error(f"[ARBITRATOR] Error fetching living-mode beliefs: {e}")
            return []

    def _fetch_relevant_mental_models(
        self,
        save_id: str,
        max_turn_id: int,
        on_scene: list[str],
        limit: int,
    ) -> list[str]:
        """Return up to `limit` mental-model summaries for the living-mode prompt.

        Mental models are the most synthetic recall layer (§7.8): one curated
        profile per subject. Prioritises models about an on-scene character (whose
        profile the scene most needs), then fills with the most recently refreshed.
        Bounded by `max_turn_id` (a rewound turn never resurfaces a future model).
        Degrades to an empty list on any error (never breaks a turn).
        """
        if limit <= 0:
            return []
        try:
            from axiom import mental_models as mm_mod

            all_models = mm_mod.get_mental_models(
                self._db_path, save_id, max_turn_id=max_turn_id
            )
            names = {n.strip().lower() for n in (on_scene or []) if n}

            seen: set[str] = set()
            ordered: list[str] = []

            def _add_if(predicate) -> None:
                for m in all_models:
                    if len(ordered) >= limit:
                        break
                    summary = (m.summary or "").strip()
                    if not summary or summary in seen or not predicate(m):
                        continue
                    seen.add(summary)
                    label = m.subject.strip()
                    ordered.append(f"{label}: {summary}" if label else summary)

            # Pass 1: profiles of a character on scene. Pass 2: most recent.
            if names:
                _add_if(lambda m: m.subject.strip().lower() in names)
            _add_if(lambda m: True)

            return ordered[:limit]
        except Exception as e:
            logger.error(f"[ARBITRATOR] Error fetching living-mode mental models: {e}")
            return []

    def _fetch_relevant_lore(self, save_id: str, user_message: str, k: int = 5) -> list[dict]:
        """Fetch Lore Book entries relevant to the current turn.

        Semantic retrieval (TICKET-072): the Lore Book is embedded into the
        per-save vector store and matched by *meaning*, so "betrayal" can surface
        a lore entry about a "coup" even without the exact word. The semantic
        seeds are then **link-expanded** (Hindsight-inspired) to a few related
        entries — same category or shared keywords — for associative recall.

        Falls back to a deterministic keyword overlap on the structured table
        when the embedding runtime is unavailable (e.g. Windows without torch) or
        nothing was embedded. Returns `{category, name, content}` dicts (the shape
        the prompt builder expects), or an empty list.
        """
        text = (user_message or "").strip()
        if not text:
            return []

        vm = self._vector_memory
        # Embed the lore once per session (cheap: small, universe-level table).
        # A hot reload builds a fresh engine, so this also resyncs after edits.
        if vm is not None and save_id not in self._lore_synced:
            try:
                self._sync_lore_embeddings(save_id)
            except Exception as e:
                logger.error(f"[ARBITRATOR] Lore embedding sync failed: {e}")
            self._lore_synced.add(save_id)

        # Semantic path + link expansion. Skipped when the embedding runtime is
        # off (degrades to the keyword overlap below).
        if vm is not None and not getattr(vm, "_disabled", False):
            try:
                hits = vm.query(save_id, text, k=k, chunk_type="lore")
            except Exception as e:
                logger.error(f"[ARBITRATOR] Semantic lore query failed: {e}")
                hits = []
            seed_ids = [h["entry_id"] for h in hits if h.get("entry_id")]
            if seed_ids:
                return self._expand_lore(seed_ids, k, save_id=save_id, why="semantic")

        return self._fetch_lore_by_keywords(text.lower(), k, save_id=save_id)

    def _load_lore_rows(self, save_id: str | None = None) -> list[dict]:
        """Read world Lore_Book plus this save's Session_Lore."""
        out: list[dict] = []
        try:
            with get_connection(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT entry_id, category, name, keywords, content FROM Lore_Book;"
                ).fetchall()
                for r in rows:
                    out.append({
                        "entry_id": r["entry_id"],
                        "category": r["category"] or "",
                        "name": (r["name"] or "").strip(),
                        "keywords": r["keywords"] or "",
                        "content": r["content"] or "",
                        "source": "world",
                    })
                if save_id:
                    try:
                        srows = conn.execute(
                            "SELECT entry_id, category, name, keywords, content "
                            "FROM Session_Lore WHERE save_id = ?;",
                            (save_id,),
                        ).fetchall()
                    except sqlite3.Error:
                        srows = []
                    for r in srows:
                        out.append({
                            "entry_id": r["entry_id"],
                            "category": r["category"] or "",
                            "name": (r["name"] or "").strip(),
                            "keywords": r["keywords"] or "",
                            "content": r["content"] or "",
                            "source": "session",
                        })
        except sqlite3.Error as e:
            logger.error(f"[ARBITRATOR] Error fetching lore book: {e}")
            return out
        return out

    def _sync_lore_embeddings(self, save_id: str) -> None:
        """Embed (idempotently) this save's Lore Book into the vector store."""
        if self._vector_memory is None:
            return
        entries = []
        for r in self._load_lore_rows(save_id):
            text = f"{r['name']}\n{r['content']}".strip()
            if text:
                entries.append({"entry_id": r["entry_id"], "text": text})
        self._vector_memory.sync_lore(save_id, entries)

    @staticmethod
    def _lore_tokens(keywords: str, name: str, content: str = "") -> set[str]:
        """Content tokens of a lore entry (keywords + name + excerpt), minus stopwords."""
        toks = set(re.findall(r"\b\w+\b", (keywords or "").lower())) | set(
            re.findall(r"\b\w+\b", (name or "").lower())
        )
        if content:
            body = set(re.findall(r"\b\w+\b", content.lower()))
            # Cap so a long article does not drown keyword ranking.
            toks |= set(list(body)[:80])
        return {t for t in toks if t not in _LORE_STOPWORDS}

    @staticmethod
    def _shape_lore(r: dict, why: str) -> dict:
        return {
            "entry_id": r.get("entry_id") or "",
            "category": r["category"],
            "name": r["name"],
            "content": r["content"],
            "keywords": r.get("keywords") or "",
            "source": r.get("source") or "world",
            "why": why,
        }

    def _expand_lore(self, seed_ids: list[str], k: int, *, save_id: str | None = None,
                     why: str = "semantic") -> list[dict]:
        """Link-expand semantic seeds with a few related lore entries.

        Keeps the semantic seeds (up to `k`) first, then appends up to
        `_LORE_LINK_BUDGET` entries that link to them by **shared category** or
        **shared keywords** — the cheap, query-time form of Hindsight's link
        expansion (no precomputed graph needed for our small lore tables).
        """
        rows = self._load_lore_rows(save_id)
        by_id = {r["entry_id"]: r for r in rows}
        seeds = [by_id[sid] for sid in seed_ids if sid in by_id][:k]

        result = [self._shape_lore(r, why) for r in seeds]
        if not seeds or _LORE_LINK_BUDGET <= 0:
            return result

        seed_id_set = {r["entry_id"] for r in seeds}
        seed_cats = {r["category"].lower() for r in seeds if r["category"]}
        seed_kw: set[str] = set()
        for r in seeds:
            seed_kw |= self._lore_tokens(r["keywords"], r["name"], r.get("content") or "")

        linked: list[tuple[int, dict]] = []
        for r in rows:
            if r["entry_id"] in seed_id_set:
                continue
            score = 0
            if r["category"] and r["category"].lower() in seed_cats:
                score += 2  # same category is a strong link
            score += len(self._lore_tokens(r["keywords"], r["name"], r.get("content") or "") & seed_kw)
            if score > 0:
                linked.append((score, r))

        linked.sort(key=lambda s: s[0], reverse=True)
        result.extend(self._shape_lore(r, "link") for _score, r in linked[:_LORE_LINK_BUDGET])
        return result

    def _fetch_lore_by_keywords(self, text_lower: str, k: int, *, save_id: str | None = None) -> list[dict]:
        """Deterministic fallback: rank lore by keyword / name / excerpt overlap."""
        words = {w for w in re.findall(r"\b\w+\b", text_lower) if w not in _LORE_STOPWORDS}
        if not words:
            return []
        scored: list[tuple[int, dict]] = []
        for r in self._load_lore_rows(save_id):
            tokens = self._lore_tokens(r["keywords"], r["name"], r.get("content") or "")
            score = len(words & tokens)
            if score > 0:
                scored.append((score, self._shape_lore(r, "keyword")))
        scored.sort(key=lambda s: s[0], reverse=True)
        return [entry for _score, entry in scored[:k]]

    def _load_entity_meta(self) -> dict[str, dict[str, str]]:
        """entity_id → {name, entity_type, entity_role} for alias resolution."""
        try:
            with get_connection(self._db_path) as conn:
                cols = {c[1] for c in conn.execute("PRAGMA table_info(Entities);")}
                role_sel = "entity_role" if "entity_role" in cols else "entity_type"
                rows = conn.execute(
                    f"SELECT entity_id, name, entity_type, {role_sel} AS entity_role "
                    "FROM Entities WHERE is_active = 1;"
                ).fetchall()
            return {
                r["entity_id"]: {
                    "name": r["name"] or "",
                    "entity_type": r["entity_type"] or "",
                    "entity_role": r["entity_role"] or r["entity_type"] or "",
                }
                for r in rows
            }
        except sqlite3.Error:
            return {}

    @staticmethod
    def _resolve_entity_id(
        raw: str,
        all_stats: dict[str, dict[str, str]],
        meta: dict[str, dict[str, str]],
    ) -> str:
        """Map LLM aliases (name, 'player') onto the real entity_id."""
        if not raw:
            return raw
        if raw in all_stats or raw in meta:
            return raw
        lower = raw.lower()
        for eid in list(all_stats) + [k for k in meta if k not in all_stats]:
            if eid.lower() == lower:
                return eid
        for eid, info in meta.items():
            if (info.get("name") or "").lower() == lower:
                return eid
        if lower == "player":
            players = [
                eid for eid, info in meta.items()
                if info.get("entity_role") == "player" or info.get("entity_type") == "player"
            ]
            if len(players) == 1:
                return players[0]
            if "player" in all_stats or "player" in meta:
                return "player"
        return raw

    @staticmethod
    def _resolve_stat_key(raw: str, entity_stats: dict[str, str]) -> str:
        """Prefer the entity's authored key (Sample) over a definition id (sample)."""
        return resolve_stat_key(raw, entity_stats)

    def _load_defined_stats(self) -> set[str]:
        """Return the set of defined stat names (lowercased) for this universe.

        Read once per turn and passed to `_validate_change` so the stat-restriction
        rule no longer issues one query per proposed change (former N+1).
        """
        try:
            with get_connection(self._db_path) as conn:
                rows = conn.execute("SELECT name, stat_id FROM Stat_Definitions;").fetchall()
            names = {str(r[0]).lower() for r in rows if r[0]}
            ids = {str(r[1]).lower() for r in rows if r[1]}
            return names | ids
        except sqlite3.Error:
            return set()

    def _load_pending_correction(self, save_id: str, turn_id: int) -> str | None:
        """Narrator hint staged by the previous turn (correction loop), if any.

        Read from the Event_Log, so a rewind before that turn removes it."""
        try:
            with get_connection(self._db_path) as conn:
                rows = conn.execute(
                    "SELECT payload FROM Event_Log WHERE save_id = ? AND turn_id = ? "
                    "AND event_type = ? ORDER BY event_id;",
                    (save_id, turn_id - 1, CORRECTION_EVENT),
                ).fetchall()
        except sqlite3.Error:
            logger.debug("Correction hint lookup failed", exc_info=True)
            return None
        hints: list[str] = []
        for row in rows:
            try:
                payload = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            except (TypeError, ValueError):
                continue
            hint = payload.get("hint") if isinstance(payload, dict) else None
            if hint:
                hints.append(str(hint))
        return " ".join(hints) or None

    def _fire(self, hook_name: str, ctx: TurnContext) -> None:
        """Fire a turn hook; faulty mod callbacks are isolated by the kernel (§6.1)."""
        reg = self.kernel_registry
        if reg is not None:
            reg.invoke_hook(hook_name, ctx)

    def _has_hook(self, hook_name: str) -> bool:
        reg = self.kernel_registry
        return bool(reg is not None and reg.has_hook(hook_name))

    def _has_service(self, service_name: str) -> bool:
        reg = self.kernel_registry
        return bool(reg is not None and reg.get_service(service_name) is not None)
