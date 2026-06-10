"""axiom.regenerate — régénération d'une variante narrative (portage B4).

Logique extraite de `workers/regenerate_worker.py` : rejouer le tour `turn_id`
avec le même message joueur pour produire une **nouvelle variante** du texte
narratif (sans réévaluer les règles ni les stats), puis l'ajouter au payload
multiverse de l'`Event_Log` (`{"active": idx, "variants": [...]}`).

Zéro dépendance Qt. Le streaming remonte par callback `on_token`.
"""

from __future__ import annotations

import json
from typing import Callable

from axiom.backends.base import LLMBackend
from axiom.prompts import build_narrative_prompt
from axiom.schema import get_connection

# Mapping verbosité → plafond de tokens (aligné sur l'arbitrator).
_VERBOSITY_TO_TOKENS = {"short": 150, "balanced": 400, "talkative": 1024}


def history_to_messages(history: list[dict]) -> list[dict]:
    """Convertit l'historique event-sourcé (user_input / narrative_text) en
    messages LLM (la variante active fait foi pour le narratif)."""
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
    verbosity_level: str = "balanced",
    player_id: str = "player_1",
    on_token: Callable[[str], None] | None = None,
) -> str:
    """Génère une variante alternative du tour `turn_id` et l'enregistre.

    La nouvelle variante est ajoutée au payload `narrative_text` du tour et
    devient la variante **active**. Retourne le texte généré.
    """
    llm_history = history_to_messages(history)

    prompt = build_narrative_prompt(
        universe_system_prompt=system_prompt,
        entity_stats_block="",  # pas de stats : on ne réévalue pas les règles
        rag_chunks=[],
        history=llm_history,
        user_message=user_message,
        verbosity_level=verbosity_level,
        player_id=player_id,
    )

    # Pas de tool-call sur une régénération : on ne veut que du texte.
    for msg in prompt:
        if msg["role"] == "system":
            msg["content"] = msg["content"].replace(
                "You MUST end your response with a JSON block",
                "You are generating a new variant. Do NOT output any JSON tool calls.",
            )

    stops = ["\nUser:", "\nPlayer:", "\n[User]", "<|eot_id|>",
             f"\n{player_id}:", f"\n[{player_id}]"]
    max_tokens = _VERBOSITY_TO_TOKENS.get(verbosity_level.lower(), 400)

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

    append_variant(db_path, save_id, turn_id, narrative_text.strip())
    return narrative_text


def append_variant(db_path: str, save_id: str, turn_id: int, text: str) -> bool:
    """Ajoute `text` comme variante active du `narrative_text` d'un tour.

    Un payload historique non-multiverse est converti au passage. Retourne
    False si le tour n'a pas d'événement narratif (rien n'est écrit).
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
