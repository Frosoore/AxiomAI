"""mods/axiom.minimal_chat/main.py

Official mod: axiom.minimal_chat
Provides a minimal conversational turn pipeline ('turn_pipeline') for when tabletop
RPG mods (axiom.world, axiom.turn...) are disabled.
"""

from __future__ import annotations

from typing import Any

from axiom.arbitrator import ArbitratorResult
from axiom.backends.base import GenerationCancelled, LLMMessage
from axiom.kernel.context import ModContext
from axiom.kernel.step_context import KernelStepContext
from axiom.turn_batch import TurnWriteBatch


def _resolve_llm(step_context: KernelStepContext, mod_ctx: ModContext) -> Any:
    if step_context.llm is not None:
        return step_context.llm
    from axiom.session import resolve_llm_backend
    registry = getattr(mod_ctx, "registry", None) or getattr(mod_ctx, "_registry", None)
    return resolve_llm_backend(registry=registry)


def on_execute_step(step_context: KernelStepContext, mod_ctx: ModContext) -> None:
    from axiom.kernel.patcher import step_patch_freeze

    with step_patch_freeze():
        _execute_chat_step(step_context, mod_ctx)


def _execute_chat_step(step_context: KernelStepContext, mod_ctx: ModContext) -> None:
    llm = _resolve_llm(step_context, mod_ctx)
    user_text = step_context.input or " ".join((step_context.intents or {}).values())

    session = step_context.session
    history_messages = step_context.history
    if history_messages is None and session is not None and hasattr(session, "_load_history"):
        history_messages = session._load_history()
    history_messages = history_messages or []

    system_prompt = (
        step_context.system_prompt
        or getattr(session, "_system_prompt", None)
        or "You are a helpful, creative AI conversation partner."
    )

    messages: list[LLMMessage] = [{"role": "system", "content": system_prompt}]
    for msg in history_messages:
        if isinstance(msg, dict):
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
        else:
            role = getattr(msg, "role", "user")
            content = getattr(msg, "content", "")
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_text})

    stream_cb = step_context.stream_token_callback
    full_response_parts: list[str] = []

    if stream_cb is not None and hasattr(llm, "stream_tokens"):
        try:
            for chunk in llm.stream_tokens(messages, temperature=step_context.temperature, top_p=step_context.top_p):
                if chunk:
                    full_response_parts.append(chunk)
                    stream_cb(chunk)
        except GenerationCancelled:
            raise
        reply_text = "".join(full_response_parts)
    elif stream_cb is not None and hasattr(llm, "stream"):
        try:
            for chunk in llm.stream(messages):
                if chunk:
                    full_response_parts.append(chunk)
                    stream_cb(chunk)
        except GenerationCancelled:
            raise
        reply_text = "".join(full_response_parts)
    elif hasattr(llm, "complete"):
        resp = llm.complete(
            messages,
            temperature=step_context.temperature,
            top_p=step_context.top_p,
        )
        reply_text = getattr(resp, "narrative_text", None) or getattr(resp, "text", None) or str(resp)
        if stream_cb is not None and reply_text:
            stream_cb(reply_text)
    elif hasattr(llm, "generate"):
        resp = llm.generate(
            messages,
            temperature=step_context.temperature,
            top_p=step_context.top_p,
        )
        reply_text = getattr(resp, "text", None) or str(resp)
        if stream_cb is not None and reply_text:
            stream_cb(reply_text)
    else:
        resp = llm(messages)
        reply_text = str(resp)

    batch = TurnWriteBatch()
    batch.stage_event(
        event_type="user_input",
        payload={"text": user_text},
        target_entity="player",
    )
    batch.stage_event(
        event_type="narrative_text",
        payload={"variants": [reply_text], "active": 0},
        target_entity="system",
    )

    step_context.result = ArbitratorResult(
        narrative_text=reply_text,
        batch=batch,
        game_state_tag="dialogue",
        scene_pace="balanced",
    )
    if session is not None:
        session._last_game_state_tag = "dialogue"


def init(ctx: ModContext) -> None:
    """Entry point for axiom.minimal_chat mod."""
    ctx.register_hook("axiom.kernel:execute_step", lambda step_ctx: on_execute_step(step_ctx, ctx))
