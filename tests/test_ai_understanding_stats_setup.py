"""Tests for AI understanding, interpretation, and reception of Stats and Story Setup."""

import json
import sqlite3
import pytest

from axiom.backends.base import LLMMessage
from axiom.prompts import (
    build_narrative_prompt,
    format_entity_stats_block,
    format_stat_definitions_block,
    format_story_setup_block,
)
from axiom.arbitrator import ArbitratorEngine, TurnContext
from axiom.schema import create_universe_db


class TestStorySetupFormatting:
    def test_empty_setup_answers_returns_empty_string(self):
        assert format_story_setup_block([]) == ""
        assert format_story_setup_block({}) == ""
        assert format_story_setup_block(None) == ""

    def test_list_of_dict_format(self):
        answers = [
            {"id": "origin", "question": "Where do you come from?", "answer": "The Northern Peaks"},
            {"id": "trade", "question": "What is your profession?", "answer": "Hedge mage"},
        ]
        block = format_story_setup_block(answers)
        assert "STORY SETUP & PREMISES:" in block
        assert "- Where do you come from?: The Northern Peaks" in block
        assert "- What is your profession?: Hedge mage" in block
        assert "Honor and weave these established background elements" in block

    def test_dict_format(self):
        answers = {
            "Origin": "Empire of Ashes",
            "Goal": "Find the ancient relic",
        }
        block = format_story_setup_block(answers)
        assert "STORY SETUP & PREMISES:" in block
        assert "- Origin: Empire of Ashes" in block
        assert "- Goal: Find the ancient relic" in block


class TestStatDefinitionsFormatting:
    def test_empty_stat_definitions_returns_empty_string(self):
        assert format_stat_definitions_block({}) == ""
        assert format_stat_definitions_block([]) == ""
        assert format_stat_definitions_block(None) == ""

    def test_stat_definitions_formatting_with_bounds_and_descriptions(self):
        stat_defs = {
            "health": {
                "name": "Health",
                "description": "Physical vitality. At 0, you are dying.",
                "parameters": {"min": 0, "max": 100},
            },
            "sanity": {
                "name": "Sanity",
                "description": "Mental stability against cosmic dread.",
                "parameters": {"min": -50, "max": 50},
            },
            "coin": {
                "name": "Coin",
                "description": "Currency in gold marks.",
                "parameters": {"min": 0},
            },
        }
        block = format_stat_definitions_block(stat_defs)
        assert "DEFINED STATS & SCALES:" in block
        assert "- Health [0..100]: Physical vitality. At 0, you are dying." in block
        assert "- Sanity [-50..50]: Mental stability against cosmic dread." in block
        assert "- Coin [min 0]: Currency in gold marks." in block
        assert "respect these defined stat names, scales, and boundaries" in block


class TestEntityStatsBlockEnrichment:
    def test_entity_with_description(self):
        snap = {
            "entity_id": "emperor_arven",
            "name": "Arven Deymar",
            "entity_type": "npc",
            "description": "The Usurper who seized the Ash Throne.",
            "stats": {"Health": 100},
        }
        res = format_entity_stats_block([snap])
        assert "[NPC] Arven Deymar (id: emperor_arven)" in res
        assert "Description: The Usurper who seized the Ash Throne." in res

    def test_entity_stats_with_stat_definitions_bounds(self):
        snap = {
            "entity_id": "player",
            "name": "Garen",
            "entity_type": "player",
            "stats": {"Health": 85, "Sanity": 10, "Coin": 25, "Rank": "Veteran"},
        }
        stat_defs = {
            "health": {"name": "Health", "parameters": {"min": 0, "max": 100}},
            "sanity": {"name": "Sanity", "parameters": {"min": -100, "max": 100}},
            "coin": {"name": "Coin", "parameters": {"min": 0}},
        }
        res = format_entity_stats_block([snap], stat_definitions=stat_defs)
        assert "Health: 85/100" in res
        assert "Sanity: 10 [-100..100]" in res
        assert "Coin: 25 [min 0]" in res
        assert "Rank: Veteran" in res

    def test_entity_stats_without_definitions_backwards_compatible(self):
        snap = {
            "entity_id": "player",
            "name": "Garen",
            "entity_type": "player",
            "stats": {"Health": 85},
        }
        res = format_entity_stats_block([snap])
        assert "Health: 85" in res
        assert "Description:" not in res


class TestBuildNarrativePromptIntegration:
    def test_prompt_includes_setup_answers_and_stat_definitions(self):
        setup_answers = [
            {"id": "origin", "question": "Where were you born?", "answer": "Highport docks"}
        ]
        stat_defs = {
            "hp": {
                "name": "HP",
                "description": "Life points",
                "parameters": {"min": 0, "max": 100},
            }
        }
        entity_stats_block = "[PLAYER] Roland (id: player)\n    HP: 90/100"

        messages = build_narrative_prompt(
            universe_system_prompt="You are the Dungeon Master.",
            entity_stats_block=entity_stats_block,
            rag_chunks=[],
            history=[],
            intents={"player": "Look around"},
            player_persona="A quiet rogue.",
            setup_answers=setup_answers,
            stat_definitions=stat_defs,
        )

        sys_msg = messages[0]["content"]
        assert "CHARACTER BACKGROUND:\nA quiet rogue." in sys_msg
        assert "STORY SETUP & PREMISES:" in sys_msg
        assert "- Where were you born?: Highport docks" in sys_msg
        assert "DEFINED STATS & SCALES:" in sys_msg
        assert "- HP [0..100]: Life points" in sys_msg
        assert "CURRENT STATE:\n[PLAYER] Roland (id: player)\n    HP: 90/100" in sys_msg

        # Order check: Persona -> Setup -> Stat definitions -> Current State
        pos_persona = sys_msg.find("CHARACTER BACKGROUND:")
        pos_setup = sys_msg.find("STORY SETUP & PREMISES:")
        pos_stat_defs = sys_msg.find("DEFINED STATS & SCALES:")
        pos_state = sys_msg.find("CURRENT STATE:")
        assert pos_persona < pos_setup < pos_stat_defs < pos_state


class TestArbitratorContextGathering:
    def test_arbitrator_extracts_setup_answers_stat_defs_and_descriptions(self, tmp_path):
        db_path = str(tmp_path / "test_game.db")
        save_id = "save_test_001"

        create_universe_db(db_path)

        with sqlite3.connect(db_path) as conn:

            # Insert Saves
            conn.execute(
                "INSERT INTO Saves (save_id, player_name, difficulty, player_persona, last_updated) VALUES (?, 'Aria', 'Normal', 'A scholar', '2026-10-23');",
                (save_id,),
            )
            # Insert Story_Setup
            conn.execute(
                "INSERT INTO Story_Setup (setup_id, question, type, priority) VALUES ('origin', 'Where do you come from?', 'single_choice', 1);"
            )
            # Insert Event_Log setup_answer
            conn.execute(
                "INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) "
                "VALUES (?, 0, 'setup_answer', 'origin', ?);",
                (save_id, json.dumps({"answer": "Aicamed Federation"})),
            )
            # Insert Stat_Definitions
            conn.execute(
                "INSERT INTO Stat_Definitions (stat_id, name, description, value_type, parameters) "
                "VALUES ('arcane_focus', 'Arcane Focus', 'Arcane core stamina.', 'numeric', ?);",
                (json.dumps({"min": 0, "max": 100}),),
            )
            # Insert Entities with description
            conn.execute(
                "INSERT INTO Entities (entity_id, entity_type, name, description) "
                "VALUES ('npc_mentor', 'npc', 'Master Elidor', 'An ancient archmage with cloudy eyes.');"
            )
            # Insert Entity_Stats
            conn.execute(
                "INSERT INTO Entity_Stats (entity_id, stat_key, stat_value) "
                "VALUES ('npc_mentor', 'Arcane Focus', '80');"
            )
            conn.commit()

        engine = ArbitratorEngine(db_path=db_path)
        ctx = TurnContext(
            save_id=save_id,
            step_id=1,
            user_input="Hello mentor",
            player_entity_id="player",
            verbosity="balanced",
            intents={"player": "Hello mentor"},
        )

        engine.step_1_gather_context(ctx)

        # Assert context was gathered
        assert len(ctx.setup_answers) == 1
        assert ctx.setup_answers[0]["id"] == "origin"
        assert ctx.setup_answers[0]["question"] == "Where do you come from?"
        assert ctx.setup_answers[0]["answer"] == "Aicamed Federation"

        assert "arcane focus" in ctx.stat_definitions
        assert ctx.stat_definitions["arcane focus"]["description"] == "Arcane core stamina."
        assert ctx.stat_definitions["arcane focus"]["parameters"]["max"] == 100

        assert ctx.id_to_description.get("npc_mentor") == "An ancient archmage with cloudy eyes."

        # Run step 2
        engine.step_2_build_prompt(ctx)

        prompt_sys = ctx.prompt_messages[0]["content"]
        assert "STORY SETUP & PREMISES:" in prompt_sys
        assert "- Where do you come from?: Aicamed Federation" in prompt_sys
        assert "DEFINED STATS & SCALES:" in prompt_sys
        assert "- Arcane Focus [0..100]: Arcane core stamina." in prompt_sys
        assert "Master Elidor" in prompt_sys
        assert "Description: An ancient archmage with cloudy eyes." in prompt_sys
        assert "Arcane Focus: 80/100" in prompt_sys
