"""axiom.regenerate — regenerating a narrative variant.

Replays turn `turn_id` with the same player message to produce a **new
variant** of the narrative text (without re-evaluating rules or stats), then
appends it to the turn's multiverse payload in the `Event_Log`
(`{"active": idx, "variants": [...]}`).

Zero Qt dependency. Streaming is surfaced through the `on_token` callback.
"""

from __future__ import annotations

import json
from typing import Callable

import re

from axiom.backends.base import LLMBackend
from axiom.prompts import (
    DEFAULT_VERBOSITY_LEVEL,
    NARRATIVE_TOOL_CALL_SCHEMA,
    build_narrative_prompt,
)
from axiom.schema import get_connection

# Replaces the state-change JSON instructions of the turn prompt: a variant is
# prose only (no rule or stat is re-evaluated).
_VARIANT_INSTRUCTION = (
    "You are writing an alternative version of this turn's narration. "
    "Write prose only: do NOT output any JSON block, code fence or tool call."
)

# A trailing JSON block, fenced (~~~json / ```json / ~~~ / ```, closed or not).
_TRAILING_FENCE = re.compile(r"\s*(?:~~~|```)(?:json)?\s*[\[{].*\Z", re.DOTALL | re.IGNORECASE)
# An unfenced trailing JSON object that looks like a tool call ({"key": ...).
_TRAILING_OBJECT = re.compile(r'\s*\{\s*"[^"\n]+"\s*:.*\Z', re.DOTALL)

# Mapping verbosité → plafond de tokens (aligné sur l'arbitrator).
_VERBOSITY_TO_TOKENS = {"short": 150, "balanced": 400, "talkative": 1024}


def history_to_messages(history: list[dict]) -> list[dict]:
    """Convert the event-sourced history (user_input / narrative_text) into LLM
    messages (the active variant is authoritative for the narrative).
    """
    messages: list[dict] = []
    for h in history:
        payload = h.get("payload", "")
        if h.get("event_type") == "user_input":
            text = payload.get("text", str(payload)) if isinstance(payload, dict) else str(payload)
            messages.append({"role": "user", "content": text})
        elif h.get("event_type") == "narrative_text":
            if isinstance(payload, dict) and "variants" in payload:
                text = payload["variants"][payload["active"]]
            else:
                text = str(payload)
            messages.append({"role": "assistant", "content": text})
    return messages


def regenerate_variant(
    llm: LLMBackend,
    db_path: str,
    save_id: str,
    turn_id: int,
    history: list[dict],
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    top_p: float = 1.0,
    verbosity_level: str = DEFAULT_VERBOSITY_LEVEL,
    player_id: str = "player_1",
    on_token: Callable[[str], None] | None = None,
) -> str:
    """Generate an alternative variant of turn `turn_id` and record it.

    The new variant is appended to the turn's `narrative_text` payload and
    becomes the **active** variant. Returns the generated text.
    """
    llm_history = history_to_messages(history)

    prompt = build_narrative_prompt(
        universe_system_prompt=system_prompt,
        entity_stats_block="",  # pas de stats : on ne réévalue pas les règles
        rag_chunks=[],
        history=llm_history,
        intents={player_id: user_message},
        verbosity_level=verbosity_level,
    )

    # Pas de tool-call sur une régénération : on ne veut que du texte. On retire
    # la vraie consigne JSON du prompt de tour (TICKET-104).
    for msg in prompt:
        if msg["role"] == "system" and NARRATIVE_TOOL_CALL_SCHEMA in msg["content"]:
            msg["content"] = msg["content"].replace(
                NARRATIVE_TOOL_CALL_SCHEMA, _VARIANT_INSTRUCTION
            )

    stops = ["\nUser:", "\nPlayer:", "\n[User]", "<|eot_id|>",
             f"\n{player_id}:", f"\n[{player_id}]"]
    max_tokens = _VERBOSITY_TO_TOKENS.get(
        verbosity_level.lower(),
        _VERBOSITY_TO_TOKENS[DEFAULT_VERBOSITY_LEVEL],
    )

    narrative_text = ""
    for token in llm.stream_tokens(
        prompt,
        temperature=temperature,
        top_p=top_p,
        stop_sequences=stops,
        max_tokens=max_tokens,
    ):
        narrative_text += token
        if on_token is not None:
            on_token(token)

    # Garde-fou : un modèle qui émet quand même un bloc JSON ne doit pas le
    # stocker dans la variante (il s'afficherait et repartirait dans l'historique).
    narrative_text = strip_json_block(narrative_text)
    append_variant(db_path, save_id, turn_id, narrative_text)
    return narrative_text


def strip_json_block(text: str) -> str:
    """Remove a trailing JSON tool-call block (fenced or bare) from narrative prose."""
    cleaned = _TRAILING_FENCE.sub("", text or "")
    cleaned = _TRAILING_OBJECT.sub("", cleaned)
    return cleaned.strip()


def append_variant(db_path: str, save_id: str, turn_id: int, text: str) -> bool:
    """Append `text` as the active variant of a turn's `narrative_text`.

    A historical non-multiverse payload is converted on the way. Returns False
    when the turn has no narrative event (nothing is written).
    """
    with get_connection(db_path) as conn:
        row = conn.execute(
            "SELECT payload FROM Event_Log WHERE save_id = ? AND turn_id = ? "
            "AND event_type = 'narrative_text';",
            (save_id, turn_id),
        ).fetchone()
        if not row:
            return False

        payload = json.loads(row[0])
        if not isinstance(payload, dict) or "variants" not in payload:
            old = payload.get("text", "") if isinstance(payload, dict) else str(payload)
            payload = {"active": 0, "variants": [old]}

        payload["variants"].append(text)
        payload["active"] = len(payload["variants"]) - 1

        conn.execute(
            "UPDATE Event_Log SET payload = ? WHERE save_id = ? AND turn_id = ? "
            "AND event_type = 'narrative_text';",
            (json.dumps(payload), save_id, turn_id),
        )
        conn.commit()
    return True
