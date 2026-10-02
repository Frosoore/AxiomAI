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


def _apply_prompt_sections(ctx: TurnContext, mod_ctx: ModContext) -> None:
    entries = mod_ctx.get_slot_entries("axiom.turn:prompt_sections")

    def _depth(entry: tuple[str, Any]) -> Any:
        item = entry[1]
        return item.get("depth", 0) if isinstance(item, dict) else 0

    for mod_id, raw_item in sorted(entries, key=_depth):
        item = raw_item
        if callable(raw_item):
            ok, item = _call_contribution(
                mod_ctx, mod_id, "slot 'axiom.turn:prompt_sections'", raw_item, ctx
            )
            if not ok:
                continue
        elif isinstance(raw_item, dict) and callable(raw_item.get("builder")):
            ok, text = _call_contribution(
                mod_ctx, mod_id, "slot 'axiom.turn:prompt_sections'", raw_item["builder"], ctx
            )
            if not ok:
                continue
            item = dict(raw_item)
            item["text"] = text

        if isinstance(item, dict):
            pos = item.get("position", "system")
            text = item.get("text") or item.get("content", "")
        elif isinstance(item, str):
            pos = "system"
            text = item
        else:
            continue
        if not text:
            continue
        if pos in ("system", "after_system") and ctx.prompt_messages:
            ctx.prompt_messages[0]["content"] += f"\n\n{text}"
        elif pos == "before_system" and ctx.prompt_messages:
            ctx.prompt_messages[0]["content"] = f"{text}\n\n" + ctx.prompt_messages[0]["content"]
        elif pos == "user" and len(ctx.prompt_messages) > 1:
            ctx.prompt_messages[-1]["content"] += f"\n\n{text}"
        else:
            ctx.rag_chunks.append(text)


def _route_output_fields(ctx: TurnContext, mod_ctx: ModContext) -> None:
    where = "slot 'axiom.turn:output_fields'"
    for mod_id, contrib in mod_ctx.get_slot_entries("axiom.turn:output_fields"):
        if isinstance(contrib, tuple) and len(contrib) == 2:
            pairs = [contrib]
        elif isinstance(contrib, dict):
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
        llm=llm,
        epoch=step_context.epoch,
        epoch_checker=(lambda: session.epoch) if session is not None and hasattr(session, "epoch") else None,
    )
    faulted_before = set(mod_ctx.get_faulted_mods())

    # Step 1: Context Gathering (fires axiom.step:gather_context once)
    engine.step_1_gather_context(ctx)

    # Step 2: Prompt Building & Slot Injection
    engine.step_2_build_prompt(ctx)
    _apply_prompt_sections(ctx, mod_ctx)

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
