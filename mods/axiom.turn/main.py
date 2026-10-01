"""mods/axiom.turn/main.py

Official mod: axiom.turn (Fabric API for turn pipeline & arbitration)
Orchestrates LLM inference, prompt assembly, output routing, filter chains, and arbitration.
"""

from __future__ import annotations

from typing import Any

from axiom.arbitrator import ArbitratorEngine, ArbitratorResult, TurnContext
from axiom.kernel.context import ModContext
from axiom.kernel.step_context import KernelStepContext


_ENGINE_CACHE: dict[str, ArbitratorEngine] = {}


def _get_engine(db_path: str, registry: Any) -> ArbitratorEngine:
    """Get or create cached ArbitratorEngine instance for a universe DB."""
    from axiom.db_helpers import load_rules_for_session
    rules = load_rules_for_session(db_path) if db_path else []
    engine = ArbitratorEngine(db_path, rules, kernel_registry=registry)
    return engine


def on_execute_step(step_context: KernelStepContext, registry: Any) -> None:
    """Hook: axiom.kernel:execute_step.

    Main entry point for turn orchestration called by Session.
    """
    from axiom.kernel.patcher import step_patch_freeze

    with step_patch_freeze():
        _execute_step_locked(step_context, registry)


def _execute_step_locked(step_context: KernelStepContext, registry: Any) -> None:
    db_path = step_context.db_path
    engine = _get_engine(db_path, registry)

    # Resolve LLM backend: step_context.llm wins if explicitly passed, otherwise slot 'axiom.turn:llm_backend'
    llm = step_context.llm
    if llm is None:
        backend_val = registry.get_slot("axiom.turn:llm_backend")
        if callable(backend_val):
            try:
                llm = backend_val(step_context)
            except TypeError:
                llm = backend_val()
        elif backend_val is not None:
            llm = backend_val
    engine.configure(llm, step_context.vector_memory, step_context.time_llm)

    intents = dict(step_context.intents or ({"player": step_context.input} if step_context.input else {}))
    hero_entity_id = step_context.hero_entity_id
    player_entity_id = next((aid for aid in intents if aid != hero_entity_id), "player") if intents else "player"
    combined_text = " ".join(intents.values()) if intents else ""

    history = step_context.session._load_history() if step_context.session else []
    system_prompt = getattr(step_context.session, "_system_prompt", "")

    ctx = TurnContext(
        save_id=step_context.save_id,
        step_id=step_context.step,
        user_input=combined_text,
        player_entity_id=player_entity_id,
        verbosity=step_context.verbosity_level,
        intents=intents,
        history=history,
        universe_system_prompt=system_prompt,
        mode=step_context.mode,
        hero_entity_id=hero_entity_id,
        temperature=step_context.temperature,
        top_p=step_context.top_p,
        auto_commit=step_context.auto_commit,
        db_path=db_path,
    )

    # Step 1: Context Gathering
    engine.step_1_gather_context(ctx)
    registry.execute_hook("axiom.step:gather_context", ctx)

    # Step 2: Prompt Building & Slot Injection
    engine.step_2_build_prompt(ctx)
    prompt_sections = registry.get_slot_contributions("axiom.turn:prompt_sections")
    if prompt_sections:
        for raw_item in sorted(prompt_sections, key=lambda s: s.get("depth", 0) if isinstance(s, dict) else 0):
            item = raw_item
            if callable(raw_item):
                try:
                    item = raw_item(ctx)
                except Exception:
                    continue
            elif isinstance(raw_item, dict) and callable(raw_item.get("builder")):
                try:
                    item = dict(raw_item)
                    item["text"] = raw_item["builder"](ctx)
                except Exception:
                    continue

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

    # Step 3: Inference Execution with stream_filter chain
    base_stream_cb = step_context.stream_token_callback

    def filtered_stream_cb(token: str) -> None:
        tok = registry.apply_slot_chain("axiom.turn:stream_filter", token)
        if tok is not None and base_stream_cb is not None:
            base_stream_cb(tok)

    engine.step_3_execute_inference(ctx, stream_cb=filtered_stream_cb if base_stream_cb else None)

    # Step 4: Parse Response & final_text_filter chain & output_fields routing
    engine.step_4_parse_response(ctx)
    ctx.narrative_text = registry.apply_slot_chain("axiom.turn:final_text_filter", ctx.narrative_text)

    for contrib in registry.get_slot_contributions("axiom.turn:output_fields"):
        if isinstance(contrib, tuple) and len(contrib) == 2:
            field_name, handler = contrib
            if field_name in ctx.parsed_tool_call and callable(handler):
                handler(ctx.parsed_tool_call[field_name], ctx)
        elif isinstance(contrib, dict):
            for field_name, handler in contrib.items():
                if field_name in ctx.parsed_tool_call and callable(handler):
                    handler(ctx.parsed_tool_call[field_name], ctx)

    # Step 5: Rules & Stats Arbitration
    engine.step_5_arbitrate_rules(ctx)

    # Step 6: Mutation Staging
    engine.step_6_stage_mutations(ctx)

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
    )
    ctx.result = step_context.result



def init(ctx: ModContext) -> None:
    """Entry point for axiom.turn mod."""
    reg = ctx._registry
    # Register the main turn execution hook
    ctx.register_hook("axiom.kernel:execute_step", lambda step_ctx: on_execute_step(step_ctx, reg))
