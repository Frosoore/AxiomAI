"""
tests/test_prompt_builder.py

Unit tests for llm_engine/prompt_builder.py.
All functions are pure; no mocking required.
"""

import json

import pytest

from axiom.prompts import (
    HISTORY_TURN_CAP,
    MINI_DICO_SYSTEM_PROMPT,
    NARRATIVE_TOOL_CALL_SCHEMA,
    build_chronicler_prompt,
    build_mini_dico_prompt,
    build_narrative_prompt,
    build_populate_prompt,
    format_entity_stats_block,
    _extract_conversation_turns,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_history(n_turns: int) -> list[dict]:
    """Build n_turns of (user, assistant) message pairs."""
    msgs = []
    for i in range(n_turns):
        msgs.append({"role": "user", "content": f"user turn {i}"})
        msgs.append({"role": "assistant", "content": f"assistant turn {i}"})
    return msgs


def _roles(messages: list[dict]) -> list[str]:
    return [m["role"] for m in messages]


# ---------------------------------------------------------------------------
# build_narrative_prompt
# ---------------------------------------------------------------------------

class TestBuildNarrativePrompt:
    def test_first_message_is_system(self) -> None:
        """The narrative prompt always opens with a system message."""
        result = build_narrative_prompt("SYS", "stats", [], [], {"player": "Hello"})
        assert result[0]["role"] == "system"

    def test_basic_prompt_injection(self) -> None:
        """The narrative prompt appends basic_prompt instructions to the system message if provided."""
        result_without = build_narrative_prompt("SYS_PROMPT", "stats", [], [], {"player": "Hello"})
        result_with = build_narrative_prompt("SYS_PROMPT", "stats", [], [], {"player": "Hello"}, basic_prompt="CUSTOM_INSTRUCTION")
        assert "CUSTOM_INSTRUCTION" not in result_without[0]["content"]
        assert "SYS_PROMPT" in result_with[0]["content"]
        assert "CUSTOM_INSTRUCTION" in result_with[0]["content"]
        assert "SYS_PROMPT\n\nCUSTOM_INSTRUCTION" in result_with[0]["content"]


    def test_system_contains_universe_prompt(self) -> None:
        """The universe's system prompt is embedded in the system message."""
        result = build_narrative_prompt("MY_UNIVERSE_PROMPT", "stats", [], [], {"player": "hi"})
        assert "MY_UNIVERSE_PROMPT" in result[0]["content"]

    def test_system_contains_entity_stats(self) -> None:
        """The entity stats block is embedded in the system message."""
        result = build_narrative_prompt("sys", "ENTITY_STATS_HERE", [], [], {"player": "hi"})
        assert "ENTITY_STATS_HERE" in result[0]["content"]

    def test_system_contains_tool_call_schema(self) -> None:
        """The system message documents the ~~~json tool-call schema."""
        result = build_narrative_prompt("sys", "stats", [], [], {"player": "hi"})
        assert "~~~json" in result[0]["content"]

    def test_last_message_is_user(self) -> None:
        """The player's input is carried in the user message near the end."""
        result = build_narrative_prompt("sys", "stats", [], [], {"player": "Player input"})
        assert result[-2]["role"] == "user"
        assert "Player input" in result[-2]["content"]

    def test_history_turns_appear_between_system_and_user(self) -> None:
        """Prior turns sit between the opening system message and the final
        user/system messages."""
        history = _make_history(2)
        result = build_narrative_prompt("sys", "stats", [], history, {"player": "current"})
        roles = _roles(result)
        # system first, user last, and both user/assistant in between
        assert roles[0] == "system"
        assert roles[-2] == "user"
        assert roles[-1] == "system"
        assert "user" in roles[1:-2]
        assert "assistant" in roles[1:-2]

    def test_history_capped_at_history_turn_cap(self) -> None:
        """History is truncated to at most HISTORY_TURN_CAP turns."""
        history = _make_history(HISTORY_TURN_CAP + 10)
        result = build_narrative_prompt("sys", "stats", [], history, {"player": "now"})
        # Count user+assistant messages (exclude first system and last user)
        middle = result[1:-2]
        history_messages = [m for m in middle if m["role"] != "system"]
        # At most HISTORY_TURN_CAP pairs = 2*HISTORY_TURN_CAP messages
        assert len(history_messages) <= 2 * HISTORY_TURN_CAP

    def test_exactly_cap_turns_kept(self) -> None:
        """With more than cap turns, exactly cap turns should remain."""
        extra = 5
        history = _make_history(HISTORY_TURN_CAP + extra)
        result = build_narrative_prompt("sys", "stats", [], history, {"player": "now"})
        middle = result[1:-2]
        history_messages = [m for m in middle if m["role"] != "system"]
        assert len(history_messages) == 2 * HISTORY_TURN_CAP

    def test_pending_correction_injected_before_last_user(self) -> None:
        """A pending correction is inserted as a system message just before the
        final user message."""
        correction = "CORRECTION: you failed."
        result = build_narrative_prompt("sys", "stats", [], [], {"player": "hi"}, correction)
        # The second-to-last message should be a system message with the correction
        assert result[-3]["role"] == "system"
        assert correction in result[-3]["content"]
        assert result[-2]["role"] == "user"

    def test_no_pending_correction_when_none(self) -> None:
        """With no correction, no extra correction system message is added."""
        result = build_narrative_prompt("sys", "stats", [], [], {"player": "hi"}, None)
        roles = _roles(result)
        # Only one system message (the first) — no correction
        assert roles.count("system") == 2

    def test_rag_chunks_prepended_to_user_message(self) -> None:
        """Retrieved memory chunks are folded into the user message alongside
        the player's input."""
        chunks = ["Memory A", "Memory B"]
        result = build_narrative_prompt("sys", "stats", chunks, [], {"player": "What happened?"})
        user_content = result[-2]["content"]
        assert "Memory A" in user_content
        assert "Memory B" in user_content
        assert "What happened?" in user_content

    def test_rag_chunks_appear_before_user_message(self) -> None:
        """RAG context precedes the player's input within the user message."""
        chunks = ["Memory chunk"]
        result = build_narrative_prompt("sys", "stats", chunks, [], {"player": "Input"})
        content = result[-2]["content"]
        assert content.index("Memory chunk") < content.index("Input")

    def test_no_rag_chunks_user_message_unchanged(self) -> None:
        """Without RAG chunks, the user message contains the formatted intents."""
        result = build_narrative_prompt("sys", "stats", [], [], {"player": "Just this."})
        assert "[SIMULTANEOUS ACTIONS FOR THIS TICK]" in result[-2]["content"]
        assert "[player] INTENT: Just this." in result[-2]["content"]

    def test_history_system_messages_dropped(self) -> None:
        """System messages in history should not be replayed."""
        history = [
            {"role": "system", "content": "Old system"},
            {"role": "user", "content": "old user"},
            {"role": "assistant", "content": "old assistant"},
        ]
        result = build_narrative_prompt("sys", "stats", [], history, {"player": "now"})
        # The "Old system" content should not appear in middle turns
        middle_contents = [m["content"] for m in result[1:-1] if m["role"] != "system"]
        assert not any("Old system" in c for c in middle_contents)


# ---------------------------------------------------------------------------
# build_chronicler_prompt
# ---------------------------------------------------------------------------

class TestBuildChroniclerPrompt:
    def test_first_message_is_system(self) -> None:
        """The chronicler prompt opens with a system message."""
        result = build_chronicler_prompt([], 0.3)
        assert result[0]["role"] == "system"

    def test_system_contains_base_prompt(self) -> None:
        """The chronicler base prompt is present in the system message."""
        result = build_chronicler_prompt([], 0.3)
        from axiom.prompts import CHRONICLER_SYSTEM_PROMPT_BASE
        assert "Chronicler" in result[0]["content"]

    def test_low_tension_guidance_injected(self) -> None:
        """A low tension value injects low/mundane-tone guidance."""
        result = build_chronicler_prompt([], 0.2)
        assert "LOW" in result[0]["content"].upper() or "mundane" in result[0]["content"].lower()

    def test_high_tension_guidance_injected(self) -> None:
        """A high tension value injects high/dramatic-tone guidance."""
        result = build_chronicler_prompt([], 0.8)
        assert "HIGH" in result[0]["content"].upper() or "dramatic" in result[0]["content"].lower()

    def test_tension_boundary_at_threshold(self) -> None:
        """Exactly 0.5 should trigger high-tension guidance."""
        result = build_chronicler_prompt([], 0.5)
        assert "dramatic" in result[0]["content"].lower() or "HIGH" in result[0]["content"].upper()

    def test_entities_serialised_in_user_message(self) -> None:
        """Off-screen entities (names and stats) are serialised into the user
        message for the chronicler."""
        entities = [
            {"entity_id": "king1", "name": "King Aldric", "entity_type": "npc",
             "stats": {"Health": "90", "Army_Size": "5000"}}
        ]
        result = build_chronicler_prompt(entities, 0.3)
        user_content = result[1]["content"]
        assert "King Aldric" in user_content
        assert "Army_Size" in user_content

    def test_second_message_is_user(self) -> None:
        """The chronicler prompt's second message is the user message."""
        result = build_chronicler_prompt([], 0.5)
        assert result[1]["role"] == "user"

    def test_exactly_two_messages(self) -> None:
        """The chronicler prompt is exactly a system + user pair."""
        result = build_chronicler_prompt([], 0.5)
        assert len(result) == 2

    def test_tension_clamped_above_one(self) -> None:
        """Tension > 1.0 should be treated as 1.0 (high tension)."""
        result = build_chronicler_prompt([], 99.0)
        assert "dramatic" in result[0]["content"].lower() or "HIGH" in result[0]["content"].upper()

    def test_tension_clamped_below_zero(self) -> None:
        """Tension < 0.0 should be treated as 0.0 (low tension)."""
        result = build_chronicler_prompt([], -5.0)
        assert "mundane" in result[0]["content"].lower() or "LOW" in result[0]["content"].upper()


# ---------------------------------------------------------------------------
# build_mini_dico_prompt
# ---------------------------------------------------------------------------

class TestBuildMiniDicoPrompt:
    def test_first_message_is_system_with_mini_dico_prompt(self) -> None:
        """The mini-dico prompt opens with the fixed MINI_DICO_SYSTEM_PROMPT."""
        result = build_mini_dico_prompt("What is the Elder Wood?", [])
        assert result[0]["role"] == "system"
        assert result[0]["content"] == MINI_DICO_SYSTEM_PROMPT

    def test_second_message_is_user(self) -> None:
        """The mini-dico prompt's second message is the user message."""
        result = build_mini_dico_prompt("question", [])
        assert result[1]["role"] == "user"

    def test_exactly_two_messages(self) -> None:
        """The mini-dico prompt is exactly a system + user pair."""
        result = build_mini_dico_prompt("q", [])
        assert len(result) == 2

    def test_rag_chunks_appear_in_user_message(self) -> None:
        """Provided lore excerpts are included in the user message."""
        chunks = ["The Elder Wood is ancient.", "Dragons live there."]
        result = build_mini_dico_prompt("Tell me about the Elder Wood.", chunks)
        user_content = result[1]["content"]
        assert "Elder Wood is ancient" in user_content
        assert "Dragons live there" in user_content

    def test_question_appears_in_user_message(self) -> None:
        """The user's question is included in the user message."""
        result = build_mini_dico_prompt("Who is the Queen?", ["Some lore."])
        assert "Who is the Queen?" in result[1]["content"]

    def test_no_rag_chunks_indicates_unavailable(self) -> None:
        """With no lore excerpts, the user message says none are available."""
        result = build_mini_dico_prompt("question", [])
        assert "No lore excerpts available" in result[1]["content"]

    def test_system_prompt_forbids_roleplay(self) -> None:
        """The mini-dico system prompt explicitly forbids roleplay."""
        assert "roleplay" in MINI_DICO_SYSTEM_PROMPT.lower()

    def test_system_prompt_forbids_plot_advancement(self) -> None:
        """The mini-dico system prompt explicitly forbids advancing the plot."""
        assert "plot" in MINI_DICO_SYSTEM_PROMPT.lower()


# ---------------------------------------------------------------------------
# build_populate_prompt
# ---------------------------------------------------------------------------

class TestBuildPopulatePrompt:
    def test_returns_two_messages(self) -> None:
        """The populate prompt is a system + user pair."""
        result = build_populate_prompt("Some lore", ["Existing"])
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[1]["role"] == "user"

    def test_contains_lore_and_skip_list(self) -> None:
        """The lore chunk and the already-known (skip) names appear in the prompt."""
        result = build_populate_prompt("UNIQUE_LORE_CHUNK", ["King_Arthur"])
        user_content = result[1]["content"]
        assert "UNIQUE_LORE_CHUNK" in user_content
        assert "King_Arthur" in user_content

    def test_contains_json_schema(self) -> None:
        """The populate prompt documents the expected JSON entity schema."""
        result = build_populate_prompt("lore", [])
        user_content = result[1]["content"]
        assert "~~~json" in user_content
        assert '"name"' in user_content
        assert '"description"' in user_content

    def test_contains_available_stats_when_provided(self) -> None:
        """When stat definitions are supplied, they're listed under an AVAILABLE
        STATS section."""
        stat_defs = [{"name": "Health", "value_type": "numeric", "description": "HP", "parameters": {}}]
        result = build_populate_prompt("lore", [], stat_defs)
        user_content = result[1]["content"]
        assert "=== AVAILABLE STATS ===" in user_content
        assert '"Health"' in user_content
        assert "HP" in user_content

    def test_shows_no_stats_placeholder_when_empty(self) -> None:
        """With no stat definitions, a 'No stats defined' placeholder is shown."""
        result = build_populate_prompt("lore", [], [])
        user_content = result[1]["content"]
        assert "No stats defined" in user_content


# ---------------------------------------------------------------------------
# format_entity_stats_block
# ---------------------------------------------------------------------------

class TestFormatEntityStatsBlock:
    def test_empty_list_returns_placeholder(self) -> None:
        """An empty entity list formats to the '(no entities)' placeholder."""
        result = format_entity_stats_block([])
        assert result == "(no entities)"

    def test_entity_name_appears(self) -> None:
        """An entity's name is rendered in the formatted block."""
        snap = {"entity_id": "p1", "name": "Aria", "entity_type": "player",
                "stats": {"HP": "100"}}
        result = format_entity_stats_block([snap])
        assert "Aria" in result

    def test_entity_type_uppercased(self) -> None:
        """The entity type is rendered uppercased (player → PLAYER)."""
        snap = {"entity_id": "p1", "name": "Aria", "entity_type": "player",
                "stats": {}}
        result = format_entity_stats_block([snap])
        assert "PLAYER" in result

    def test_stat_key_value_appear(self) -> None:
        """Each stat key and its value are rendered in the block."""
        snap = {"entity_id": "p1", "name": "Aria", "entity_type": "player",
                "stats": {"HP": "80", "Gold": "200"}}
        result = format_entity_stats_block([snap])
        assert "HP" in result and "80" in result
        assert "Gold" in result and "200" in result

    def test_multiple_entities_all_appear(self) -> None:
        """All entities in the list are rendered in the block."""
        snaps = [
            {"entity_id": "p1", "name": "Aria", "entity_type": "player", "stats": {}},
            {"entity_id": "npc1", "name": "Goblin", "entity_type": "npc", "stats": {}},
        ]
        result = format_entity_stats_block(snaps)
        assert "Aria" in result
        assert "Goblin" in result

    def test_no_stats_shows_placeholder(self) -> None:
        """An entity with no stats shows a 'no stats' placeholder."""
        snap = {"entity_id": "p1", "name": "Ghost", "entity_type": "npc", "stats": {}}
        result = format_entity_stats_block([snap])
        assert "no stats" in result

    def test_returns_non_empty_string_for_valid_input(self) -> None:
        """A valid entity snapshot formats to a non-empty string."""
        snap = {"entity_id": "x", "name": "X", "entity_type": "npc", "stats": {"A": "1"}}
        result = format_entity_stats_block([snap])
        assert isinstance(result, str) and len(result) > 0


# ---------------------------------------------------------------------------
# _extract_conversation_turns (internal helper)
# ---------------------------------------------------------------------------

class TestExtractConversationTurns:
    def test_pairs_user_and_assistant(self) -> None:
        """Consecutive user/assistant messages are grouped into turn pairs."""
        history = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
        ]
        turns = _extract_conversation_turns(history)
        assert len(turns) == 2
        assert turns[0][0]["role"] == "user"
        assert turns[0][1]["role"] == "assistant"

    def test_system_messages_dropped(self) -> None:
        """System messages in history are excluded from the extracted turns."""
        history = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
        ]
        turns = _extract_conversation_turns(history)
        assert len(turns) == 1
        all_roles = [m["role"] for pair in turns for m in pair]
        assert "system" not in all_roles

    def test_empty_history_returns_empty(self) -> None:
        """Extracting turns from an empty history returns an empty list."""
        assert _extract_conversation_turns([]) == []

    def test_unpaired_user_included(self) -> None:
        """A trailing user message with no assistant reply is still kept as a turn."""
        history = [{"role": "user", "content": "u1"}]
        turns = _extract_conversation_turns(history)
        assert len(turns) == 1
        assert turns[0][0]["role"] == "user"
