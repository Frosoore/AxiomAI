"""tests/test_time_inventory_mods.py

Acceptance tests for Phase 2:
- axiom.time (Diegetic Time System, Calendar & Off-Screen Chronicler)
- axiom.inventory (Emergent Nested Inventory & Item Trees)

Validates:
1. Declarative compliance, loading via directory and .axmod archive, service registration.
2. Time passage and writing to Timeline table without hardcoded time code in the kernel.
3. Item movement into a container (container_id) via output_fields.
4. Unit deactivation (Rule D11): deactivating axiom.inventory allows axiom.turn to run smoothly,
   ignoring inventory_changes without error.
5. Scheduled events triggering on time passage.
"""

from __future__ import annotations

from pathlib import Path
import pytest

import axiom.paths
from axiom.cli.mods_cmd import pack_mod
from axiom.compile import compile_universe
from axiom.kernel import (
    KernelRegistry,
    load_mod,
    load_mod_from_archive,
    load_mod_from_dir,
    parse_manifest_file,
)
from axiom.savestore import create_save
from axiom.schema import get_connection
from axiom.session import Session
from axiom.testing.golden_harness import (
    ScriptedLLMBackend,
    ScriptedTurnResponse,
)


@pytest.fixture
def test_env(tmp_path: Path):
    """Prepares an isolated game environment with compiled Myria universe and player entity."""
    data_dir = tmp_path / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    axiom.paths.configure(data_dir=data_dir)

    myria_src = Path(__file__).resolve().parent.parent / "universes" / "Myria"
    uni_db = compile_universe(myria_src, tmp_path / "myria.db", force=True)

    with get_connection(str(uni_db)) as conn:
        conn.execute(
            "INSERT INTO Entities (entity_id, entity_type, entity_role, name, is_active) "
            "VALUES ('player', 'player', 'player', 'Hero', 1);"
        )
        conn.execute(
            "INSERT INTO Entity_Stats (entity_id, stat_key, stat_value) VALUES "
            "('player', 'Health', '100'), "
            "('player', 'Arcane Focus', '100'), "
            "('player', 'Coin', '50'), "
            "('player', 'Location', 'gilded_compass');"
        )
        conn.commit()

    yield {
        "tmp_path": tmp_path,
        "uni_db": uni_db,
    }


def test_manifests_and_loading(tmp_path: Path):
    """1. Verify manifests, directory loading, packaging, and archive loading for time & inventory."""
    root = Path(__file__).resolve().parent.parent
    time_dir = root / "mods" / "axiom.time"
    inv_dir = root / "mods" / "axiom.inventory"

    # Manifest parsing
    time_m = parse_manifest_file(time_dir / "mod.toml")
    assert time_m.id == "axiom.time"
    assert "axiom.step:after_step" in time_m.contributes.hooks
    assert "axiom.turn:output_fields" in time_m.contributes.slots
    assert "axiom.turn:prompt_sections" in time_m.contributes.slots

    inv_m = parse_manifest_file(inv_dir / "mod.toml")
    assert inv_m.id == "axiom.inventory"
    assert "axiom.turn:output_fields" in inv_m.contributes.slots
    assert "axiom.turn:prompt_sections" in inv_m.contributes.slots
    assert "axiom.inventory:actions" in inv_m.provides_slots

    # Load from directory
    reg = KernelRegistry()
    load_mod_from_dir(time_dir, reg)
    load_mod_from_dir(inv_dir, reg)
    assert reg.get_service("time") is not None
    assert reg.get_service("inventory") is not None

    # Pack and load from archive
    time_axmod = pack_mod(time_dir, tmp_path / "axiom.time.axmod")
    inv_axmod = pack_mod(inv_dir, tmp_path / "axiom.inventory.axmod")

    reg_arch = KernelRegistry()
    load_mod_from_archive(time_axmod, reg_arch)
    load_mod_from_archive(inv_axmod, reg_arch)
    assert reg_arch.get_service("time") is not None
    assert reg_arch.get_service("inventory") is not None


def test_time_passage_and_timeline_writing(test_env):
    """2. Time advances and writes to Timeline table without hardcoded time logic in kernel."""
    env = test_env
    save_info = create_save(env["uni_db"], "Hero", "Normal")
    save_id = save_info["save_id"]
    save_db = save_info["db_path"]

    llm = ScriptedLLMBackend([
        ScriptedTurnResponse(
            narrative_chunks=["You rest near the campfire for an hour."],
            tool_call={
                "time_elapsed_minutes": 60,
            },
        ),
    ])

    session = Session(save_db, save_id, llm=llm, time_llm=llm)
    res = session.take_turn("Rest for an hour.")

    assert res.narrative_text == "You rest near the campfire for an hour."
    assert session.turn_id == 1

    # Verify Timeline row written by axiom.time mod
    with get_connection(save_db) as conn:
        row = conn.execute(
            "SELECT turn_id, in_game_time, description FROM Timeline WHERE save_id = ? AND turn_id = 1;",
            (save_id,),
        ).fetchone()
        assert row is not None
        assert row[0] == 1
        assert row[1] == 60
        assert "Turn advanced by 60 mins" in row[2]

    # Verify service format_time
    time_svc = session.kernel_registry.get_service("time")
    assert time_svc is not None
    formatted = time_svc.format_time(save_db, 60)
    assert formatted != ""


def test_inventory_move_item_into_container(test_env):
    """3. Item movement into a container (container_id) via output_fields."""
    env = test_env
    save_info = create_save(env["uni_db"], "Hero", "Normal")
    save_id = save_info["save_id"]
    save_db = save_info["db_path"]

    # Pre-populate player with backpack (container) and potion
    from axiom.inventory import add_item
    with get_connection(save_db) as conn:
        backpack_inst = add_item(
            conn, save_id, "leather_backpack", quantity=1,
            holder_kind="entity", holder_id="player",
            name="Leather Backpack", is_container=True,
        )
        potion_inst = add_item(
            conn, save_id, "healing_potion", quantity=1,
            holder_kind="entity", holder_id="player",
            name="Healing Potion", is_container=False,
        )
        conn.commit()

    llm = ScriptedLLMBackend([
        ScriptedTurnResponse(
            narrative_chunks=["You stow the potion inside your backpack."],
            tool_call={
                "inventory_changes": [
                    {
                        "action": "move",
                        "item_id": "healing_potion",
                        "instance_id": potion_inst,
                        "container_id": backpack_inst,
                        "quantity": 1,
                    }
                ],
            },
        ),
    ])

    session = Session(save_db, save_id, llm=llm, time_llm=llm)
    res = session.take_turn("Stow potion in backpack")

    assert res.narrative_text == "You stow the potion inside your backpack."
    assert len(res.inventory_changes) == 1

    # Verify that healing_potion holder is now the backpack instance
    with get_connection(save_db) as conn:
        row = conn.execute(
            "SELECT holder_kind, holder_id FROM Item_Instances WHERE save_id = ? AND instance_id = ?;",
            (save_id, potion_inst),
        ).fetchone()
        assert row is not None
        assert row[0] == "instance"
        assert row[1] == backpack_inst

        # Verify Inventory_Snapshots row created
        snap_row = conn.execute(
            "SELECT turn_id, state_json FROM Inventory_Snapshots WHERE save_id = ? AND turn_id = 1;",
            (save_id,),
        ).fetchone()
        assert snap_row is not None


def test_inventory_deactivation_unit_reversibility(test_env):
    """4. Deactivating axiom.inventory: axiom.turn runs smoothly and ignores item fields without crash."""
    env = test_env
    save_info = create_save(env["uni_db"], "Hero", "Normal")
    save_id = save_info["save_id"]
    save_db = save_info["db_path"]

    # Explicit registry WITHOUT axiom.inventory
    registry = KernelRegistry()
    root = Path(__file__).resolve().parent.parent
    load_mod(root / "mods" / "axiom.world", registry)
    load_mod(root / "mods" / "axiom.turn", registry)
    load_mod(root / "mods" / "axiom.time", registry)
    # axiom.inventory is deliberately NOT loaded

    llm = ScriptedLLMBackend([
        ScriptedTurnResponse(
            narrative_chunks=["You spot a strange sword in the stones."],
            tool_call={
                "inventory_changes": [
                    {"action": "add", "item_id": "ancient_sword", "quantity": 1}
                ],
                "time_elapsed_minutes": 10,
            },
        ),
    ])

    session = Session(save_db, save_id, llm=llm, time_llm=llm, kernel_registry=registry)
    res = session.take_turn("Examine stones.")

    # Narrative produced without crash
    assert res.narrative_text == "You spot a strange sword in the stones."
    # inventory_changes was ignored by the turn pipeline
    assert res.inventory_changes == []

    # Verify ancient_sword was NOT added to database
    with get_connection(save_db) as conn:
        row = conn.execute(
            "SELECT count(*) FROM Item_Instances WHERE save_id = ? AND item_id = 'ancient_sword';",
            (save_id,),
        ).fetchone()
        assert row[0] == 0


def test_scheduled_events_trigger_on_time_advance(test_env):
    """5. Scheduled_Events are detected and recorded into Fired_Scheduled_Events upon time passage."""
    env = test_env
    save_info = create_save(env["uni_db"], "Hero", "Normal")
    save_id = save_info["save_id"]
    save_db = save_info["db_path"]

    # Insert a scheduled event at minute 30
    with get_connection(save_db) as conn:
        conn.execute(
            "INSERT INTO Scheduled_Events (event_id, title, description, trigger_minute) "
            "VALUES ('blood_moon', 'Blood Moon', 'The sky turns scarlet.', 30);"
        )
        conn.commit()

    llm = ScriptedLLMBackend([
        ScriptedTurnResponse(
            narrative_chunks=["You march towards the distant valley for 45 minutes."],
            tool_call={
                "time_elapsed_minutes": 45,
            },
        ),
    ])

    session = Session(save_db, save_id, llm=llm, time_llm=llm)
    session.take_turn("March into the valley")

    # Verify event fired
    with get_connection(save_db) as conn:
        fired = conn.execute(
            "SELECT event_id FROM Fired_Scheduled_Events WHERE save_id = ? AND event_id = 'blood_moon';",
            (save_id,),
        ).fetchone()
        assert fired is not None
        assert fired[0] == "blood_moon"
