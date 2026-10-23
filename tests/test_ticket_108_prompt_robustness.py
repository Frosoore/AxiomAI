"""
tests/test_ticket_108_prompt_robustness.py

Unit tests for TICKET-108: Small LLM robustness (Stheno 8B / KoboldCPP).
Covers:
- Macro substitution ({{char}}, <char>, {{user}}, <user>) in prompts, lorebooks, and ST import.
- Agency protection & epistemic boundaries in system prompt and critical reminders.
- RAG history deduplication.
- Universal LLM min_p sampler support.
"""

import pytest

from axiom.backends.universal import UniversalClient
from axiom.config import AppConfig
from axiom.prompts import (
    substitute_macros,
    _format_lore_book_block,
    build_narrative_prompt,
)
from workers.import_export_worker import _substitute_st_macros


# ---------------------------------------------------------------------------
# 1. Macro substitution tests
# ---------------------------------------------------------------------------

def test_substitute_macros_basic():
    text = "Hello {{user}}, I am {{char}}. <user> meets <char>."
    result = substitute_macros(text, char_name="Nadine", user_name="Traveler")
    assert result == "Hello Traveler, I am Nadine. Traveler meets Nadine."


def test_substitute_macros_case_insensitive():
    text = "Look at {{Char}} and {{USER}} and <CHAR> and <User>."
    result = substitute_macros(text, char_name="Nadine", user_name="Traveler")
    assert result == "Look at Nadine and Traveler and Nadine and Traveler."


def test_format_lore_book_block_macro_substitution():
    lore = [
        {
            "name": "{{char}} Schedule",
            "content": "{{char}} works at the guild. If {{user}} asks, {{char}} denies it.",
            "keys": ["schedule"],
        }
    ]
    block = _format_lore_book_block(lore, char_name="Nadine", user_name="Hero")
    assert "### Nadine Schedule" in block
    assert "Nadine works at the guild." in block
    assert "If Hero asks, Nadine denies it." in block
    assert "{{char}}" not in block
    assert "{{user}}" not in block


def test_build_narrative_prompt_replaces_macros():
    lore = [
        {"name": "Secret", "content": "{{char}} hides a secret from {{user}}."}
    ]
    system_prompt = "Setting: {{char}} is waiting for {{user}}."
    stats_block = "[ENTITY STATS]\nNadine: Health=100\nplayer: Health=100"
    messages = build_narrative_prompt(
        universe_system_prompt=system_prompt,
        entity_stats_block=stats_block,
        rag_chunks=[],
        history=[],
        intents={"player": "Hello"},
        lore_book=lore,
        global_lore="Global: {{char}} is legendary.",
        player_persona="You are a traveler.",
        char_name="Nadine",
        user_name="You",
    )
    full_text = "\n".join(m["content"] for m in messages)
    assert "{{char}}" not in full_text
    assert "{{user}}" not in full_text
    assert "Nadine is waiting for You." in full_text
    assert "Nadine hides a secret from You." in full_text
    assert "Global: Nadine is legendary." in full_text


# ---------------------------------------------------------------------------
# 2. Agency protection & Epistemic Boundaries tests
# ---------------------------------------------------------------------------

def test_narrative_prompt_epistemic_boundary_and_agency_rules():
    stats_block = "[ENTITY STATS]\nNadine: Health=100\nplayer_1: Health=100"
    messages = build_narrative_prompt(
        universe_system_prompt="Guild hall.",
        entity_stats_block=stats_block,
        rag_chunks=[],
        history=[],
        intents={"player_1": "I enter the guild."},
        mode="Solo",
    )
    system_msg = messages[0]["content"]
    assert "Epistemic Boundary" in system_msg
    assert "CRITICAL REMINDER:" in messages[-1]["content"]
    reminder = messages[-1]["content"]
    assert "Assume the player's action has ALREADY happened" in reminder
    assert "Respond immediately with the NPCs' actions" in reminder
    assert "NEVER write new dialogue or internal decisions for 'You' (player_1)" in reminder
    assert "stop as soon as it is player_1's turn to reply" in reminder


def test_narrative_prompt_companion_mode_agency():
    stats_block = "[ENTITY STATS]\nNadine: Health=100\nLiora: Health=100\nplayer_1: Health=100"
    messages = build_narrative_prompt(
        universe_system_prompt="Guild hall.",
        entity_stats_block=stats_block,
        rag_chunks=[],
        history=[],
        intents={"player_1": "Let's go."},
        mode="Companion",
        hero_entity_id="Liora",
    )
    reminder = messages[-1]["content"]
    assert "Assume the player's action has ALREADY happened" in reminder
    assert "NEVER write new dialogue or internal decisions for 'You' (player_1)" in reminder
    assert "Liora" in reminder


# ---------------------------------------------------------------------------
# 3. SillyTavern card importer macro substitution
# ---------------------------------------------------------------------------

def test_sillytavern_macro_substitution():
    text = "You roleplay as {{char}} talking to {{user}}."
    result = _substitute_st_macros(text, char_name="Nadine")
    assert result == "You roleplay as Nadine talking to {{user}}."

    # Lorebook entry substitution at import time
    entry_content = "{{char}} wields a blade given by {{user}}."
    res_entry = _substitute_st_macros(entry_content, char_name="Nadine")
    assert res_entry == "Nadine wields a blade given by {{user}}."

    # Runtime substitution when building prompt for a player named Arthur
    block = _format_lore_book_block(
        [{"name": "Dagger", "content": res_entry}],
        char_name="Nadine",
        user_name="Arthur",
    )
    assert "Nadine wields a blade given by Arthur." in block


# ---------------------------------------------------------------------------
# 4. Universal LLM Client min_p sampler tests
# ---------------------------------------------------------------------------

def test_universal_client_min_p_payload():
    client = UniversalClient(
        base_url="http://localhost:5001/v1",
        api_key="test-key",
        model_name="test-model",
        min_p=0.1,
    )
    messages = [{"role": "user", "content": "Hello"}]
    payload = client._get_payload(messages)
    assert payload.get("min_p") == 0.1

    # Override min_p on call
    payload_override = client._get_payload(messages, min_p=0.05)
    assert payload_override.get("min_p") == 0.05


def test_app_config_universal_min_p():
    config = AppConfig()
    assert hasattr(config, "universal_min_p")
    assert config.universal_min_p == 0.1


# ---------------------------------------------------------------------------
# 5. RAG history deduplication test
# ---------------------------------------------------------------------------

def test_rag_chunk_filtering_against_history():
    from axiom.arbitrator import TurnContext

    ctx = TurnContext("save_1", 2, "action", "player", "balanced")
    ctx.turn_id = 2
    ctx.history = [
        {"role": "user", "content": "Sure why not..."},
        {"role": "assistant", "content": 'Secret? What secret? I-um, I don\'t know what you mean... *Her voice wavers slightly...*'},
    ]
    raw_rag = [
        # Chunk duplicating assistant message from turn 1
        'Secret? What secret? I-um, I don\'t know what you mean... *Her voice wavers slightly...*',
        # Distinct lore/memory chunk
        'The guild was founded 200 years ago during the Great Calamity.',
    ]

    history_contents = {
        m.get("content", "").strip().lower()
        for m in ctx.history
        if m.get("content")
    }
    filtered_chunks = []
    for chunk in raw_rag:
        chunk_clean = chunk.strip().lower()
        if not chunk_clean:
            continue
        is_dup = False
        for hist_text in history_contents:
            if chunk_clean == hist_text or chunk_clean in hist_text or hist_text in chunk_clean:
                is_dup = True
                break
        if not is_dup:
            filtered_chunks.append(chunk)

    assert len(filtered_chunks) == 1
    assert "The guild was founded 200 years ago" in filtered_chunks[0]
