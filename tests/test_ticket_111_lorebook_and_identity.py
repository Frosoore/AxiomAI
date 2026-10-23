"""
tests/test_ticket_111_lorebook_and_identity.py

Unit tests for TICKET-111:
1. Lorebook keyword filtering: only constant entries or entries whose keywords appear
   in the recent chat are injected. Unmentioned secondary NPCs (like Julie or Fred)
   are never injected into the prompt.
2. Main character identity & description (global_lore) is injected at the top of the
   system prompt as the foundational persona for the LLM.
3. CURRENT STATE includes the primary NPC even when they have no initial stats recorded,
   avoiding '(no entities)'.
4. Asterisk formatting rule: actions/descriptions inside *asterisks*, dialogue in "double quotes".
5. Timekeeper stop sequences do NOT contain '}' (preventing broken JSON under trim_stop=True).
"""

from unittest.mock import MagicMock
import pytest

from axiom.arbitrator import ArbitratorEngine, TurnContext
from axiom.prompts import build_narrative_prompt, format_entity_stats_block
from mods.axiom.time.main import _ask_timekeeper


def test_lorebook_keyword_filtering_ignores_unmentioned_secondary_npcs(tmp_path):
    """Test that Lorebook entries for secondary characters (Julie, Fred) are not retrieved
    unless their keywords appear in the chat text."""
    import sqlite3
    from axiom.schema import create_universe_db

    db_path = str(tmp_path / "test_lb.db")
    create_universe_db(db_path)

    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            "INSERT INTO Lore_Book (entry_id, category, name, keywords, content) VALUES (?, ?, ?, ?, ?);",
            [
                ("1", "SillyTavern", "Guilds", "Adventurers, Tavern, Guild", "Guilds are central."),
                ("2", "SillyTavern", "Julie", "Julie", "30 year old sister of Fred."),
                ("3", "SillyTavern", "Fred", "Fred", "Middle-aged leech adventurer."),
                ("4", "SillyTavern", "Manuscripts", "puissance, releguer, repentir", "Faded pages."),
                ("5", "Constant", "World Rules", "constant", "General world rules."),
            ]
        )
        conn.commit()

    arb = ArbitratorEngine(db_path, [])
    # History mentions the guild, but neither Julie nor Fred
    history = [
        {"role": "assistant", "content": "The guild hall buzzes with adventurers."}
    ]
    user_input = "Sure why not, but I have a secret to tell you..."

    results = arb._fetch_relevant_lore("save1", user_input, k=5, history=history)
    names = [r["name"] for r in results]

    # World Rules (Constant) and Guilds (matched 'guild', 'adventurers') must be present
    assert "World Rules" in names
    assert "Guilds" in names

    # Unmentioned secondary NPCs and secrets must NOT be injected
    assert "Julie" not in names
    assert "Fred" not in names
    assert "Manuscripts" not in names

    # When the player explicitly mentions Julie, Julie must now be triggered
    user_input_julie = "Do you know Julie?"
    results_julie = arb._fetch_relevant_lore("save1", user_input_julie, k=5, history=history)
    names_julie = [r["name"] for r in results_julie]
    assert "Julie" in names_julie


def test_main_character_description_injected_at_top_of_system_prompt():
    """Verify that global_lore (character description & personality) is placed at the top
    of the system prompt right under universe_system_prompt."""
    messages = build_narrative_prompt(
        universe_system_prompt="You are the Game Master.",
        entity_stats_block="[NPC] Aglae (id: aglae)",
        rag_chunks=[],
        history=[],
        intents={"player": "Hello!"},
        global_lore="### Description\nAglae has three distinct personas.\n### Personality\nShy novice.",
        char_name="Aglae",
    )
    system_content = messages[0]["content"]

    # 1. Main character identity header and description must be near the top
    assert "MAIN CHARACTER IDENTITY & LORE (Aglae):" in system_content
    assert "Aglae has three distinct personas." in system_content

    # Check order: Universe prompt -> Character Identity -> NARRATOR RULES
    idx_universe = system_content.find("You are the Game Master.")
    idx_identity = system_content.find("MAIN CHARACTER IDENTITY & LORE (Aglae):")
    idx_rules = system_content.find("NARRATOR RULES:")

    assert idx_universe != -1
    assert idx_identity != -1
    assert idx_rules != -1
    assert idx_universe < idx_identity < idx_rules

    # 2. Rules must specify portrayal of Aglae and asterisk formatting
    assert "primarily portraying Aglae" in system_content
    assert 'Format all narrative actions and descriptions inside *asterisks* and all spoken dialogue inside "double quotes".' in system_content


def test_current_state_does_not_display_no_entities_when_npc_present():
    """Verify that an NPC with no initial stats is included in format_entity_stats_block."""
    block = format_entity_stats_block([
        {
            "entity_id": "aglae",
            "name": "Aglae",
            "entity_type": "npc",
            "stats": {},
        }
    ])
    assert block != "(no entities)"
    assert "[NPC] Aglae (id: aglae)" in block


def test_timekeeper_does_not_send_closing_brace_in_stop_sequences():
    """Verify that _ask_timekeeper stops on <|eot_id|> and not '}', keeping JSON intact."""
    mock_llm = MagicMock()
    mock_llm.complete.return_value = '{"elapsed_minutes": 2, "major_event_description": null}'

    ctx = MagicMock()
    ctx.llm = mock_llm
    ctx.time_llm = None
    ctx.combined_intents_text = "Wait."
    ctx.narrative_text = "Time passes."

    elapsed = _ask_timekeeper(ctx)
    assert elapsed == 2

    call_kwargs = mock_llm.complete.call_args[1]
    assert "<|eot_id|>" in call_kwargs["stop_sequences"]
    assert "}" not in call_kwargs["stop_sequences"]
