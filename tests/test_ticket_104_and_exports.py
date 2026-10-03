"""tests/test_ticket_104_and_exports.py

Tests for:
1. TICKET-104: regenerate_variant properly replaces NARRATIVE_TOOL_CALL_SCHEMA
   with _VARIANT_INSTRUCTION in prompts and strips any trailing JSON blocks
   before saving into Event_Log variants.
2. Mid-game fork: fork_save at turn N on a save currently at turn M (M > N)
   without prior rewind, ensuring future events (Fired_Scheduled_Events, Facts,
   Event_Log) do not leak into the forked save.
3. pack_universe: verifies that packaging an archive produces a definition-only
   universe cache with all runtime tables purged.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import zipfile

import pytest

from axiom.package import CACHE_DB_NAME, CACHE_DIRNAME, pack_universe
from axiom.prompts import NARRATIVE_TOOL_CALL_SCHEMA
from axiom.regenerate import _VARIANT_INSTRUCTION, regenerate_variant, strip_json_block
from axiom.saves import fork_save
from axiom.schema import create_universe_db, get_connection
from axiom.storage_registry import get_runtime_tables


def test_strip_json_block_fenced_and_bare():
    """Verify strip_json_block handles trailing fenced and bare JSON objects."""
    prose = "The party rested by the campfire."
    fenced = f"{prose}\n\n```json\n{{\"state_changes\": []}}\n```"
    bare = f"{prose}\n\n{{\"state_changes\": []}}"

    assert strip_json_block(fenced) == prose
    assert strip_json_block(bare) == prose
    assert strip_json_block(prose) == prose


def test_ticket_104_regenerate_replaces_schema_and_strips_json(tmp_path):
    """Verify that regenerate_variant targets the real NARRATIVE_TOOL_CALL_SCHEMA

    and strips JSON blocks emitted by the LLM before storing in Event_Log.
    """
    db_file = tmp_path / "game.db"
    create_universe_db(str(db_file))
    save_id = "s_regen"

    with get_connection(str(db_file)) as conn:
        conn.execute(
            "INSERT INTO Saves (save_id, player_name, difficulty, last_updated, player_persona) "
            "VALUES (?, 'Hero', 'Normal', '2026-10-03T12:00:00Z', 'adventurer');",
            (save_id,),
        )
        conn.execute(
            "INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) "
            "VALUES (?, 1, 'narrative_text', 'world', ?);",
            (save_id, json.dumps({"active": 0, "variants": ["Original prose."]}),),
        )

    class FakeLLM:
        def stream_tokens(self, prompt, **kw):
            sys_msg = next(m for m in prompt if m["role"] == "system")
            # Verify NARRATIVE_TOOL_CALL_SCHEMA was replaced by _VARIANT_INSTRUCTION
            assert NARRATIVE_TOOL_CALL_SCHEMA not in sys_msg["content"]
            assert _VARIANT_INSTRUCTION in sys_msg["content"]

            yield "The hero bravely "
            yield "climbed the mountain.\n\n"
            yield "```json\n"
            yield '{"action": "climb", "success": true}\n'
            yield "```"

    history = [
        {"event_type": "user_input", "payload": {"text": "I climb the mountain."}},
        {"event_type": "narrative_text", "payload": {"active": 0, "variants": ["Original prose."]}},
    ]

    result = regenerate_variant(
        FakeLLM(),
        str(db_file),
        save_id,
        1,
        history,
        system_prompt=f"Welcome to the game.\n\n{NARRATIVE_TOOL_CALL_SCHEMA}",
        user_message="I climb the mountain.",
    )

    expected_prose = "The hero bravely climbed the mountain."
    assert result == expected_prose

    with get_connection(str(db_file)) as conn:
        row = conn.execute(
            "SELECT payload FROM Event_Log WHERE save_id = ? AND turn_id = 1;",
            (save_id,),
        ).fetchone()
        payload = json.loads(row[0])

    assert payload["active"] == 1
    assert payload["variants"] == ["Original prose.", expected_prose]
    assert "```json" not in payload["variants"][1]


def test_mid_game_fork_vs_source_at_turn_n(tmp_path):
    """Verify forking at turn 2 when the save has progressed to turn 4

    does not leak events, facts, or fired scheduled events from turns 3 or 4.
    """
    db_file = tmp_path / "midgame.db"
    create_universe_db(str(db_file))
    src_save = "src_save"

    with get_connection(str(db_file)) as conn:
        conn.execute(
            "INSERT INTO Saves (save_id, player_name, difficulty, last_updated, player_persona) "
            "VALUES (?, 'Player', 'Normal', '2026-10-03T12:00:00Z', 'scholar');",
            (src_save,),
        )
        for t in range(1, 5):
            conn.execute(
                "INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) "
                "VALUES (?, ?, 'user_input', 'player', ?);",
                (src_save, t, json.dumps({"text": f"turn {t}"})),
            )
            conn.execute(
                "INSERT INTO Facts (save_id, turn_id, statement, fact_type) "
                "VALUES (?, ?, ?, 'world');",
                (src_save, t, f"Fact at turn {t}"),
            )

        # Insert Scheduled_Events definitions
        conn.execute(
            "INSERT INTO Scheduled_Events (event_id, trigger_minute, title, description) "
            "VALUES ('ev_1', 10, 'Event 1', 'Desc 1'), ('ev_4', 40, 'Event 4', 'Desc 4');"
        )
        # Scheduled events: one fired at turn 1, one fired at turn 4
        conn.execute(
            "INSERT INTO Fired_Scheduled_Events (save_id, event_id, fired_turn_id) "
            "VALUES (?, 'ev_1', 1);",
            (src_save,),
        )
        conn.execute(
            "INSERT INTO Fired_Scheduled_Events (save_id, event_id, fired_turn_id) "
            "VALUES (?, 'ev_4', 4);",
            (src_save,),
        )

    # Fork at turn 2 (source save is at turn 4)
    forked_id = fork_save(str(db_file), src_save, at_turn=2, player_name="Forked Hero")

    with get_connection(str(db_file)) as conn:
        # Check Event_Log
        turns = [
            r[0]
            for r in conn.execute(
                "SELECT turn_id FROM Event_Log WHERE save_id = ? ORDER BY turn_id;",
                (forked_id,),
            ).fetchall()
        ]
        assert turns == [1, 2], f"Expected turns [1, 2], got {turns}"

        # Check Facts
        fact_turns = [
            r[0]
            for r in conn.execute(
                "SELECT turn_id FROM Facts WHERE save_id = ? ORDER BY turn_id;",
                (forked_id,),
            ).fetchall()
        ]
        assert fact_turns == [1, 2], f"Expected facts up to turn 2, got {fact_turns}"

        # Check Fired_Scheduled_Events (TICKET-103)
        fired_events = [
            r[0]
            for r in conn.execute(
                "SELECT event_id FROM Fired_Scheduled_Events WHERE save_id = ?;",
                (forked_id,),
            ).fetchall()
        ]
        assert fired_events == ["ev_1"], f"Turn 4 fired event leaked into fork: {fired_events}"


def test_pack_universe_definition_only(tmp_path):
    """Verify that pack_universe packages definition tables while purging runtime tables."""
    from axiom.compile import compile_universe
    from axiom.db_helpers import create_new_save

    uni_src = tmp_path / "universe_src"
    uni_src.mkdir(parents=True, exist_ok=True)
    (uni_src / "universe.toml").write_text(
        'name = "PackTest"\naxiom_version = "0.2.0"\n',
        encoding="utf-8",
    )
    entities_dir = uni_src / "entities"
    entities_dir.mkdir(parents=True, exist_ok=True)
    (entities_dir / "player.toml").write_text(
        'entity_id = "player"\nname = "Hero"\nrole = "protagonist"\ntype = "human"\n',
        encoding="utf-8",
    )

    # Compile universe into cache
    cache_db = compile_universe(uni_src)
    assert cache_db.is_file()

    # Add runtime data to the compiled cache that must NOT ship in archive
    sid = create_new_save(str(cache_db), "Tester", "Normal")
    with get_connection(str(cache_db)) as conn:
        conn.execute(
            "INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) "
            "VALUES (?, 1, 'turn_start', 'world', '{}');",
            (sid,),
        )
        conn.execute(
            "INSERT INTO Timeline (save_id, turn_id, in_game_time, description) "
            "VALUES (?, 1, 100, 'Game start');",
            (sid,),
        )

    out_archive = tmp_path / "pack_test.axiom"
    pack_universe(uni_src, out_archive)
    assert out_archive.is_file()

    # Unpack and verify
    unpack_dir = tmp_path / "unpacked"
    unpack_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(out_archive), "r") as zf:
        zf.extractall(unpack_dir)

    unpacked_cache_db = unpack_dir / CACHE_DIRNAME / CACHE_DB_NAME
    assert unpacked_cache_db.is_file()

    with get_connection(str(unpacked_cache_db)) as conn:
        # Definition tables intact
        ent = conn.execute("SELECT name FROM Entities WHERE name = 'Hero';").fetchone()
        assert ent is not None and ent[0] == "Hero"

        # Runtime tables purged
        for runtime_table in get_runtime_tables():
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?;",
                (runtime_table,),
            ).fetchone()
            if row is not None:
                count = conn.execute(
                    f"SELECT COUNT(*) FROM {runtime_table};"
                ).fetchone()[0]
                assert count == 0, f"Runtime table {runtime_table} not purged in packed universe! ({count} rows)"
