"""mods/axiom.turn/main.py

Official mod: axiom.turn (Fabric API for turn pipeline & arbitration)
Orchestrates LLM inference, prompt assembly, output routing, filter chains, and arbitration.

This is the only orchestration of a turn (Session.take_turn and
ArbitratorEngine.process_turn both dispatch to the `axiom.kernel:execute_step` hook).

Fault policy inside the turn (§6.1): a contribution of another mod (prompt section,
output field handler, stream/final filter, `axiom.step:*` hook) that raises is ignored,
its mod is disabled and reported, and the turn goes on. Errors of the turn itself
(LLM unreachable, cancellation...) propagate unchanged to the caller.
"""

from __future__ import annotations

from typing import Any
import weakref

from axiom.arbitrator import ArbitratorEngine, ArbitratorResult, TurnContext
from axiom.backends.base import GenerationCancelled
from axiom.kernel.context import ModContext
from axiom.kernel.step_context import KernelStepContext

#: Extras key a caller uses to run the turn with its own engine (see process_turn).
ENGINE_EXTRA = "axiom.turn:engine"

# One engine per Session, kept across turns (lore embedding is done once per engine).
# The engine holds no game state: what must survive a turn (correction hints...) is
# save data, so a fresh engine after a reload or a rewind loses nothing.
_ENGINES: "weakref.WeakKeyDictionary[Any, ArbitratorEngine]" = weakref.WeakKeyDictionary()


def _get_engine(step_context: KernelStepContext, mod_ctx: ModContext) -> ArbitratorEngine:
    """Engine passed by the caller, else the one cached for this session."""
    engine = (step_context.extras or {}).get(ENGINE_EXTRA)
    session = step_context.session
    if engine is None and session is not None:
        try:
            engine = _ENGINES.get(session)
        except TypeError:  # unhashable / non weak-referenceable session object
            engine = None
        if engine is not None and getattr(engine, "_db_path", None) != step_context.db_path:
            engine = None
    if engine is None:
        engine = ArbitratorEngine(step_context.db_path)
        if session is not None:
            try:
                _ENGINES[session] = engine
            except TypeError:
                pass
    # Hooks and services are reached through this mod's context (public API).
    engine.kernel_registry = mod_ctx
    return engine


def _resolve_llm(step_context: KernelStepContext, mod_ctx: ModContext) -> Any:
    """step_context.llm wins if passed, otherwise the exclusive slot 'axiom.turn:llm_backend'."""
    if step_context.llm is not None:
        return step_context.llm
    backend_val = mod_ctx.get_slot("axiom.turn:llm_backend")
    if callable(backend_val):
        try:
            return backend_val(step_context)
        except TypeError:
            return backend_val()
    return backend_val


def _call_contribution(mod_ctx: ModContext, mod_id: str, where: str, func: Any, *args: Any) -> tuple[bool, Any]:
    """Call one mod contribution; on error disable that mod and go on (§6.1)."""
    try:
        return True, func(*args)
    except GenerationCancelled:
        raise
    except Exception as err:
        mod_ctx.report_fault(mod_id, where, err)
        return False, None


#: Positions of a prompt section (DOC §7.1.3, SillyTavern model):
#: - "system" / "after_system": appended to the system message; "before_system": prepended;
#: - "user": appended to the last message (the player's turn);
#: - "in_chat": a system message inserted ``depth`` messages before the end of the prompt;
#: - "rag" / "context": added to the retrieved-memories block.
SECTION_POSITIONS = ("system", "after_system", "before_system", "user", "in_chat", "rag", "context")


class PromptSectionError(ValueError):
    """A prompt section contribution does not follow the documented format."""


def _as_int(value: Any, what: str) -> int:
    if isinstance(value, bool):
        raise PromptSectionError(f"{what} must be an integer, got {value!r}")
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        raise PromptSectionError(f"{what} must be an integer, got {value!r}") from None


def normalize_prompt_section(item: Any) -> dict[str, Any] | None:
    """Validate one prompt section and return {position, depth, text, order} (None = nothing).

    Accepted forms (see ``axiom.kernel.api.PUBLIC_SLOTS``):
    - ``"text"`` (position "system");
    - ``{"position", "text" | "content", "depth", "order" | "priority"}``;
    - ``(position, text)``, ``(position, depth, text)``,
      ``(id, position, depth, text)``, ``(id, position, depth, text, order)``.
    Anything else raises :class:`PromptSectionError` with the reason.
    """
    if item is None:
        return None
    if isinstance(item, str):
        position, depth, text, order = "system", 0, item, 0
    elif isinstance(item, dict):
        position = item.get("position", "system")
        text = item.get("text", item.get("content", ""))
        depth = _as_int(item.get("depth", 0), "'depth'")
        order = _as_int(item.get("order", item.get("priority", 0)), "'order'")
    elif isinstance(item, (tuple, list)):
        n = len(item)
        if n == 2:
            position, text = item
            depth, order = 0, 0
        elif n == 3:
            position, depth, text = item[0], _as_int(item[1], "depth (2nd element)"), item[2]
            order = 0
        elif n == 4:
            position, depth, text = item[1], _as_int(item[2], "depth (3rd element)"), item[3]
            order = 0
        elif n == 5:
            position, depth, text = item[1], _as_int(item[2], "depth (3rd element)"), item[3]
            order = _as_int(item[4], "order (5th element)")
        else:
            raise PromptSectionError(
                f"a tuple section has 2 to 5 elements "
                f"((id, position, depth, text, order)), got {n}"
            )
    else:
        raise PromptSectionError(f"unsupported section type {type(item).__name__}")

    if position not in SECTION_POSITIONS:
        raise PromptSectionError(
            f"unknown position {position!r} (expected one of {', '.join(SECTION_POSITIONS)})"
        )
    if text is None:
        return None
    if not isinstance(text, str):
        raise PromptSectionError(f"section text must be a string, got {type(text).__name__}")
    if not text.strip():
        return None
    return {"position": position, "depth": depth, "text": text, "order": order}


def _resolve_prompt_section(raw_item: Any, ctx: TurnContext) -> dict[str, Any] | None:
    """Build (callables, ``builder`` dicts) then validate one contribution."""
    item = raw_item(ctx) if callable(raw_item) else raw_item
    if isinstance(item, dict) and callable(item.get("builder")):
        item = {**item, "text": item["builder"](ctx)}
        item.pop("builder", None)
    return normalize_prompt_section(item)


def _collect_prompt_sections(ctx: TurnContext, mod_ctx: ModContext) -> list[dict[str, Any]]:
    """Build and validate every contributed section (before the prompt is assembled);
    a contribution that raises or does not follow the format disables its mod
    (reported with the reason) and the turn goes on."""
    sections: list[dict[str, Any]] = []
    for mod_id, raw_item in mod_ctx.get_slot_entries("axiom.turn:prompt_sections"):
        ok, section = _call_contribution(
            mod_ctx, mod_id, "slot 'axiom.turn:prompt_sections'", _resolve_prompt_section, raw_item, ctx
        )
        if ok and section is not None:
            sections.append(section)
    # Stable sort: by order, then depth; equal keys keep the load order of the mods.
    sections.sort(key=lambda s: (s["order"], s["depth"]))
    return sections


def _add_memory_sections(ctx: TurnContext, sections: list[dict[str, Any]]) -> None:
    """``rag`` / ``context`` sections form the [MEMORY] block of the prompt (one line =
    one memory). Done before the prompt is built, which reads that block."""
    ctx.memory_lines = [
        line.strip()
        for sec in sections if sec["position"] in ("rag", "context")
        for line in sec["text"].splitlines() if line.strip()
    ]


def _apply_prompt_sections(ctx: TurnContext, sections: list[dict[str, Any]]) -> None:
    """Insert the other sections into the assembled messages."""
    for sec in sections:
        pos, text = sec["position"], sec["text"]
        messages = ctx.prompt_messages
        if pos in ("system", "after_system") and messages:
            messages[0]["content"] += f"\n\n{text}"
        elif pos == "before_system" and messages:
            messages[0]["content"] = f"{text}\n\n" + messages[0]["content"]
        elif pos == "user" and len(messages) > 1:
            messages[-1]["content"] += f"\n\n{text}"
        elif pos == "in_chat" and messages:
            # depth 0 = at the very end; never before the system message.
            index = max(1, len(messages) - max(0, sec["depth"]))
            messages.insert(index, {"role": "system", "content": text})


def build_dynamic_tool_call_schema(mod_ctx: ModContext) -> str:
    """Build the JSON tool call schema instructions dynamically based on registered output fields (M5).

    If an output field is not registered (e.g. inventory_changes when axiom.inventory is disabled),
    it is not requested in the prompt, saving tokens and keeping turns hermetic.
    """
    import re
    entries = mod_ctx.get_slot_entries("axiom.turn:output_fields")
    contributed_fields: dict[str, Any] = {}
    extra_rules: list[str] = []

    for mod_id, contrib in entries:
        if isinstance(contrib, tuple) and len(contrib) == 2:
            contributed_fields[contrib[0]] = 0
        elif isinstance(contrib, dict):
            if "name" in contrib:
                fname = contrib["name"]
                schema = contrib.get("schema", 0)
                instr = contrib.get("instruction")
                contributed_fields[fname] = schema
                if instr and instr not in extra_rules:
                    extra_rules.append(f"{fname.upper()}: {instr}")
            else:
                for fname in contrib:
                    contributed_fields[fname] = 0

    rules = [
        "1. FACTIONS: Adjust dialogue based on entity 'Reputation' or 'Alliance'.",
    ]
    rule_idx = 2
    for r in extra_rules:
        clean_r = re.sub(r"^\d+\.\s*", "", r)
        rules.append(f"{rule_idx}. {clean_r}")
        rule_idx += 1
    rules.append(f"{rule_idx}. CONTINUITY: Advance the scene based on the actors' intents. Do not repeat their exact words.")

    json_obj: dict[str, Any] = {
        "state_changes": [{"entity_id": "...", "stat_key": "...", "delta": 0, "value": "..."}],
    }
    for k, v in contributed_fields.items():
        if k not in json_obj:
            json_obj[k] = v

    json_obj["narrative_events"] = ["event_id"]
    json_obj["scene_pace"] = "deliberate"
    json_obj["game_state_tag"] = "exploration"

    rules_str = "\n".join(rules)
    import json as _json
    json_str = _json.dumps(json_obj, indent=2)

    return (
        "At the end of your response, append exactly one fenced JSON block using ~~~json.\n"
        "Allowed game_state_tag values: 'exploration', 'combat', 'dialogue', 'tension'.\n\n"
        f"CRITICAL RULES:\n{rules_str}\n\n"
        f"~~~json\n{json_str}\n~~~\n"
    )


def _route_output_fields(ctx: TurnContext, mod_ctx: ModContext) -> None:
    where = "slot 'axiom.turn:output_fields'"
    for mod_id, contrib in mod_ctx.get_slot_entries("axiom.turn:output_fields"):
        if isinstance(contrib, tuple) and len(contrib) == 2:
            pairs = [contrib]
        elif isinstance(contrib, dict):
            if "name" in contrib and "handler" in contrib:
                pairs = [(contrib["name"], contrib["handler"])]
            else:
                pairs = list(contrib.items())
        else:
            continue
        for field_name, handler in pairs:
            if field_name in ctx.parsed_tool_call and callable(handler):
                ok, _ = _call_contribution(
                    mod_ctx, mod_id, where, handler, ctx.parsed_tool_call[field_name], ctx
                )
                if not ok:
                    break  # the mod is disabled: skip its other fields


def on_execute_step(step_context: KernelStepContext, mod_ctx: ModContext) -> None:
    """Hook: axiom.kernel:execute_step.

    Main entry point for turn orchestration called by Session.
    """
    from axiom.kernel.patcher import step_patch_freeze

    with step_patch_freeze():
        _execute_step_locked(step_context, mod_ctx)


def _execute_step_locked(step_context: KernelStepContext, mod_ctx: ModContext) -> None:
    db_path = step_context.db_path
    engine = _get_engine(step_context, mod_ctx)
    llm = _resolve_llm(step_context, mod_ctx)
    engine.configure(llm, step_context.vector_memory, step_context.time_llm)

    intents = dict(step_context.intents or ({"player": step_context.input} if step_context.input else {}))
    hero_entity_id = step_context.hero_entity_id
    player_entity_id = next((aid for aid in intents if aid != hero_entity_id), "player") if intents else "player"
    combined_text = " ".join(intents.values()) if intents else ""

    session = step_context.session
    history = step_context.history
    if history is None:
        history = session._load_history() if session is not None else []
    system_prompt = step_context.system_prompt
    if system_prompt is None:
        system_prompt = getattr(session, "_system_prompt", "")

    ctx = TurnContext(
        save_id=step_context.save_id,
        step_id=step_context.step,
        user_input=combined_text,
        player_entity_id=player_entity_id,
        verbosity=step_context.verbosity_level,
        intents=intents,
        history=list(history),
        universe_system_prompt=system_prompt,
        mode=step_context.mode,
        hero_entity_id=hero_entity_id,
        temperature=step_context.temperature,
        top_p=step_context.top_p,
        auto_commit=step_context.auto_commit,
        db_path=db_path,
        data_root=getattr(session, "_data_root", None),
        llm=llm,
        time_llm=step_context.time_llm or llm,
        epoch=step_context.epoch,
        epoch_checker=(lambda: session.epoch) if session is not None and hasattr(session, "epoch") else None,
    )
    faulted_before = set(mod_ctx.get_faulted_mods())

    # Step 1: Context Gathering (fires axiom.step:gather_context once)
    engine.step_1_gather_context(ctx)

    # Step 2: Prompt Building & Slot Injection
    ctx.tool_call_schema = build_dynamic_tool_call_schema(mod_ctx)
    sections = _collect_prompt_sections(ctx, mod_ctx)
    _add_memory_sections(ctx, sections)
    engine.step_2_build_prompt(ctx)
    _apply_prompt_sections(ctx, sections)

    # Step 3: Inference Execution with stream_filter chain (faulty filters isolated by the kernel)
    base_stream_cb = step_context.stream_token_callback

    def filtered_stream_cb(token: str) -> None:
        tok = mod_ctx.apply_slot_chain("axiom.turn:stream_filter", token)
        if tok is not None and base_stream_cb is not None:
            base_stream_cb(tok)

    engine.step_3_execute_inference(ctx, stream_cb=filtered_stream_cb if base_stream_cb else None)

    # Step 4: Parse Response & final_text_filter chain & output_fields routing
    engine.step_4_parse_response(ctx)
    ctx.narrative_text = mod_ctx.apply_slot_chain("axiom.turn:final_text_filter", ctx.narrative_text)
    _route_output_fields(ctx, mod_ctx)
    # The answer is read and routed: mods derive from it what arbitration needs
    # (e.g. axiom.time: elapsed minutes, Timekeeper fallback).
    mod_ctx.invoke_hook("axiom.step:response_parsed", ctx)

    # Step 5: Rules & Stats Arbitration
    engine.step_5_arbitrate_rules(ctx)

    # Step 6: Mutation Staging
    engine.step_6_stage_mutations(ctx)

    faulted = {
        mod_id: reason
        for mod_id, reason in mod_ctx.get_faulted_mods().items()
        if mod_id not in faulted_before
    }

    # Populate final step result
    step_context.result = ArbitratorResult(
        narrative_text=ctx.narrative_text,
        applied_changes=ctx.applied_changes,
        rejected_changes=ctx.rejected_changes_detailed,
        inventory_changes=ctx.inventory_changes,
        applied_modifiers=ctx.applied_modifiers,
        triggered_rules=ctx.triggered_rules,
        rule_chain_warning=ctx.rule_chain_warning,
        game_state_tag=ctx.game_state_tag,
        player_entity_id=ctx.player_entity_id,
        elapsed_minutes=ctx.elapsed_minutes,
        scene_pace=ctx.scene_pace,
        in_game_time=ctx.new_time,
        lore_hits=ctx.lore_book_subset,
        image_path=getattr(ctx, "image_path", None),
        batch=ctx.write_batch,
        faulted_mods=faulted,
    )
    ctx.result = step_context.result


def init(ctx: ModContext) -> None:
    """Entry point for axiom.turn mod."""
    # Register the main turn execution hook (critical: its errors reach the caller).
    ctx.register_hook("axiom.kernel:execute_step", lambda step_ctx: on_execute_step(step_ctx, ctx))
