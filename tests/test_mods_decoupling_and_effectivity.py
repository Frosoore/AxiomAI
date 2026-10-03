"""tests/test_mods_decoupling_and_effectivity.py

Integration and decoupling verification tests for Axiom AI Mod System:
1. Strict Decoupling:
   - axiom.world: when disabled, core does not arbitrate mutations or execute rules.
   - axiom.time: when disabled, core does not advance time or call Timekeeper LLM.
   - axiom.living_memory: when disabled, core does not query facts/beliefs/models or spawn distillation.
   - axiom.rag: when disabled in config, Session does not instantiate VectorMemory.
   - core.stat_dynamics: when disabled in config, Session does not initialize stat dynamics.
2. Effectivity:
   - community.survival: active, non-silent, provides prompt section and tracks sustained exertion.
   - All installed mods: verify non-empty contributions and healthy lifecycle.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
import pytest

import axiom.paths
from axiom.arbitrator import ArbitratorEngine, TurnContext
from axiom.config import AppConfig
from axiom.compile import compile_universe
from axiom.cli.mods_cmd import discover_installed_mods
from axiom.kernel import (
    KernelRegistry,
    ModContext,
    bootstrap_all_mods,
    load_manifest,
    parse_manifest_file,
)
from axiom.schema import get_connection
from axiom.session import Session
from axiom.testing.golden_harness import ScriptedLLMBackend


@pytest.fixture
def test_env(tmp_path: Path):
    """Sets up an isolated test universe and database."""
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
            "('player', 'Coin', '50');"
        )
        conn.commit()

    return {
        "tmp_path": tmp_path,
        "db_path": str(uni_db),
    }


def test_world_mod_decoupling(test_env):
    """Verify that when axiom.world is not loaded, core does not arbitrate mutations or run rules."""
    db_path = test_env["db_path"]
    arbitrator = ArbitratorEngine(db_path=db_path, rules_list=[])

    # Empty registry (axiom.world not loaded)
    registry = KernelRegistry()
    arbitrator.kernel_registry = registry

    ctx = TurnContext(
        save_id="save_1",
        step_id=1,
        user_input="take coin",
        player_entity_id="player",
        verbosity="normal",
        total_mins=100,
        intents={},
        db_path=db_path,
    )
    ctx.raw_state_changes = [{"entity_id": "player", "stat": "Coin", "delta": -10}]

    # step_5_arbitrate_rules should NOT run fallback mutation arbitration
    arbitrator.step_5_arbitrate_rules(ctx)
    assert len(ctx.write_batch.stat_changes) == 0

    # Now simulate axiom.world by registering a hook
    hook_called = False

    def mock_arbitrate(turn_ctx):
        nonlocal hook_called
        hook_called = True
        turn_ctx.write_batch.stat_changes.append({"entity_id": "player", "stat": "Coin", "new_value": "40"})

    registry.add_hook("axiom.step:arbitrate_mutations", "axiom.world", mock_arbitrate)
    arbitrator.step_5_arbitrate_rules(ctx)

    assert hook_called is True
    assert len(ctx.write_batch.stat_changes) == 1
    assert ctx.write_batch.stat_changes[0]["new_value"] == "40"


def test_time_mod_decoupling(test_env):
    """Verify that when axiom.time is not loaded, core does not advance time or call timekeeper."""
    db_path = test_env["db_path"]
    arbitrator = ArbitratorEngine(db_path=db_path, rules_list=[])

    # Registry without "time" service
    registry = KernelRegistry()
    arbitrator.kernel_registry = registry

    ctx = TurnContext(
        save_id="save_1",
        step_id=1,
        user_input="walk around for an hour",
        player_entity_id="player",
        verbosity="normal",
        total_mins=120,
        intents={},
        db_path=db_path,
    )
    ctx.parsed_tool_call = {"thought": "journey", "action": "walk", "time_elapsed_minutes": 60}

    arbitrator.step_4_parse_response(ctx)

    # Without time mod: elapsed_minutes remains 0, new_time equals total_mins
    assert ctx.elapsed_minutes == 0
    assert ctx.new_time == 120

    # Now simulate axiom.time registering its response_parsed hook
    from mods.axiom.time.main import on_response_parsed
    registry.add_hook("axiom.step:response_parsed", "axiom.time", on_response_parsed)
    arbitrator._fire("axiom.step:response_parsed", ctx)

    assert ctx.elapsed_minutes == 60
    assert ctx.new_time == 180


def test_living_memory_decoupling(test_env):
    """Verify that when axiom.living_memory is not loaded, core does not inject facts or query tables."""
    db_path = test_env["db_path"]
    arbitrator = ArbitratorEngine(db_path=db_path, rules_list=[])

    # Registry without "living_memory" service
    registry = KernelRegistry()
    arbitrator.kernel_registry = registry

    ctx = TurnContext(
        save_id="save_1",
        step_id=1,
        user_input="remember the king",
        player_entity_id="player",
        verbosity="normal",
        total_mins=100,
        intents={},
        db_path=db_path,
    )

    arbitrator.step_1_gather_context(ctx)

    # The kernel turn holds no memory recall of its own: nothing without the mod.
    assert not hasattr(arbitrator, "_fetch_relevant_facts")
    assert ctx.rag_chunks == []

    # Session get_memory_snapshot returns disabled: True when living_memory service is absent
    session = Session(db_path, "save_1", llm=ScriptedLLMBackend([]), kernel_registry=registry)
    mem_snapshot = session.get_memory_snapshot()
    assert mem_snapshot.get("disabled") is True


def test_rag_mod_decoupling_in_session(test_env):
    """Verify that disabling axiom.rag prevents VectorMemory instantiation."""
    db_path = test_env["db_path"]
    cfg = AppConfig()
    cfg.disabled_mods = ["axiom.rag"]

    session = Session(db_path, "save_1", llm=ScriptedLLMBackend([]), cfg=cfg)
    assert session._vector_memory is None


def test_stat_dynamics_decoupling_in_session(test_env):
    """Verify that disabling core.stat_dynamics prevents its hook from registering."""
    db_path = test_env["db_path"]
    cfg = AppConfig()
    cfg.disabled_mods = ["core.stat_dynamics"]

    session = Session(db_path, "save_1", llm=ScriptedLLMBackend([]), cfg=cfg)
    if session._kernel_registry is not None:
        assert not session._kernel_registry.has_hook("axiom.turn:arbitrate_stats")


def test_community_survival_effectivity():
    """Verify that community.survival is active, non-silent, and affects turn pipeline."""
    from axiom.turn_batch import TurnWriteBatch

    root = Path(__file__).resolve().parent.parent
    mod_dir = root / "mods" / "community.survival"
    manifest = parse_manifest_file(mod_dir / "mod.toml")

    registry = KernelRegistry()
    ctx = ModContext(manifest, registry)

    import importlib.util
    spec = importlib.util.spec_from_file_location("community_survival", mod_dir / "main.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.init(ctx)

    # 1. Slot contribution to prompt sections
    sections = registry.get_slot_contributions("axiom.turn:prompt_sections")
    assert len(sections) == 1
    section_item = sections[0](None)
    assert section_item["position"] == "system"
    assert "SURVIVAL GUIDELINES" in section_item["text"]

    # 2. Hook contribution on sustained exertion
    class DummyCtx:
        def __init__(self, elapsed: int):
            self.save_id = "test_save"
            self.turn_id = 2
            self.new_time = 240
            self.elapsed_minutes = elapsed
            self.player_entity_id = "player"
            self.write_batch = TurnWriteBatch()

    # Short activity
    short_run = DummyCtx(30)
    registry.execute_hook("axiom.step:after_step", short_run)
    assert len(short_run.write_batch.events) == 0

    # Sustained activity (>= 120 mins)
    long_run = DummyCtx(180)
    registry.execute_hook("axiom.step:after_step", long_run)
    assert len(long_run.write_batch.events) == 1
    assert long_run.write_batch.events[0]["event_type"] == "mod.community.survival.fatigue"
    assert "[Survival]" in long_run.write_batch.events[0]["payload"]["note"]

    # Clean unregistration
    ctx.cleanup()
    assert len(registry.get_slot_contributions("axiom.turn:prompt_sections")) == 0
    assert not registry.has_hook("axiom.step:after_step")


def test_all_mods_declare_meaningful_contributions():
    """Verify that all installed mods declare real contributions (slots, hooks, services, or tools)."""
    installed = discover_installed_mods()
    assert len(installed) >= 12

    for manifest, path in installed:
        has_hooks = bool(manifest.contributes.hooks)
        has_slots = bool(manifest.contributes.slots)
        has_provides_slots = bool(manifest.provides_slots)
        has_ordering_provides = bool(manifest.ordering.provides)

        # Every mod must provide at least one capability to the kernel
        assert has_hooks or has_slots or has_provides_slots or has_ordering_provides, (
            f"Mod {manifest.id} has no contributions or provided slots (placebo mod)."
        )


def test_living_memory_storage_and_fork_remapping(test_env):
    """Verify that axiom.living_memory storage handlers run via [storage] declaration
    and that fork rewrites IDs across Facts -> Observations -> Mental_Models."""
    import json
    import sqlite3
    from axiom.schema import (
        ensure_facts_table,
        ensure_mental_models_table,
        ensure_observations_table,
    )
    from axiom.storage_registry import execute_fork, execute_rewind

    db_path = test_env["db_path"]
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_facts_table(conn)
        ensure_observations_table(conn)
        ensure_mental_models_table(conn)

        # 1. Insert Facts
        cur = conn.execute(
            "INSERT INTO Facts (save_id, turn_id, fact_type, statement) VALUES (?, ?, ?, ?);",
            ("s_src", 1, "world", "The tower stands"),
        )
        f1_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO Facts (save_id, turn_id, fact_type, statement) VALUES (?, ?, ?, ?);",
            ("s_src", 2, "world", "The tower fell"),
        )
        f2_id = cur.lastrowid

        # 2. Insert Observations linked to Facts
        obs1_src = json.dumps([{"fact_id": f1_id, "turn_id": 1}])
        obs2_src = json.dumps([{"fact_id": f2_id, "turn_id": 2}])
        cur = conn.execute(
            "INSERT INTO Observations (save_id, subject, statement, proof_count, sources, history, created_turn_id, updated_turn_id, stale) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);",
            ("s_src", "Tower", "Tower is whole", 1, obs1_src, "[]", 1, 1, 0),
        )
        obs1_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO Observations (save_id, subject, statement, proof_count, sources, history, created_turn_id, updated_turn_id, stale) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);",
            ("s_src", "Dungeon", "Dungeon is dark", 1, obs2_src, "[]", 2, 2, 0),
        )
        obs2_id = cur.lastrowid

        # 3. Insert Mental_Models linked to Observations
        cur = conn.execute(
            "INSERT INTO Mental_Models (save_id, subject, summary, sources, created_turn_id, updated_turn_id, stale) "
            "VALUES (?, ?, ?, ?, ?, ?, ?);",
            ("s_src", "Tower", "Strong landmark", json.dumps([obs1_id]), 1, 1, 0),
        )
        mm1_id = cur.lastrowid
        cur = conn.execute(
            "INSERT INTO Mental_Models (save_id, subject, summary, sources, created_turn_id, updated_turn_id, stale) "
            "VALUES (?, ?, ?, ?, ?, ?, ?);",
            ("s_src", "Dungeon", "Dangerous ruins", json.dumps([obs2_id]), 2, 2, 0),
        )
        mm2_id = cur.lastrowid
        conn.commit()

        # 4. Fork at turn 1 to s_dst
        id_maps = execute_fork(conn, "s_src", "s_dst", 1, external=False)
        conn.commit()

        # Verify Facts forked
        forked_facts = conn.execute("SELECT fact_id, statement FROM Facts WHERE save_id = ?;", ("s_dst",)).fetchall()
        assert len(forked_facts) == 1
        new_f1_id = forked_facts[0]["fact_id"]
        assert new_f1_id != f1_id

        # Verify Observations forked with remapped source fact_id
        forked_obs = conn.execute("SELECT observation_id, sources FROM Observations WHERE save_id = ?;", ("s_dst",)).fetchall()
        assert len(forked_obs) == 1
        new_obs1_id = forked_obs[0]["observation_id"]
        assert new_obs1_id != obs1_id
        sources = json.loads(forked_obs[0]["sources"])
        assert sources[0]["fact_id"] == new_f1_id

        # Verify Mental_Models forked with remapped source observation_id
        forked_mm = conn.execute("SELECT model_id, sources FROM Mental_Models WHERE save_id = ?;", ("s_dst",)).fetchall()
        assert len(forked_mm) == 1
        assert forked_mm[0]["model_id"] != mm1_id
        mm_sources = json.loads(forked_mm[0]["sources"])
        assert mm_sources == [new_obs1_id]

        # 5. Rewind source save to turn 1
        execute_rewind(conn, "s_src", 1)
        conn.commit()

        remaining_facts = conn.execute("SELECT fact_id FROM Facts WHERE save_id = ?;", ("s_src",)).fetchall()
        assert len(remaining_facts) == 1
        assert remaining_facts[0]["fact_id"] == f1_id

        remaining_obs = conn.execute("SELECT observation_id FROM Observations WHERE save_id = ?;", ("s_src",)).fetchall()
        assert len(remaining_obs) == 1
        assert remaining_obs[0]["observation_id"] == obs1_id

        remaining_mm = conn.execute("SELECT model_id FROM Mental_Models WHERE save_id = ?;", ("s_src",)).fetchall()
        assert len(remaining_mm) == 1
        assert remaining_mm[0]["model_id"] == mm1_id


def test_providers_required_for_narration_with_clear_error():
    """Verify that narration requires axiom.providers (no core fallback) with a clear error message,
    and that axiom.providers is loaded in safe mode."""
    import pytest
    from pathlib import Path
    from axiom.kernel.registry import KernelRegistry
    from axiom.kernel.loader import load_mod, set_safe_mode, bootstrap_all_mods
    from axiom.config import AppConfig
    from axiom.session import resolve_llm_backend

    # 1. Empty registry: resolve_llm_backend raises clear RuntimeError
    empty_reg = KernelRegistry()
    with pytest.raises(RuntimeError, match="axiom.providers"):
        resolve_llm_backend(registry=empty_reg)

    # 2. Registry with axiom.providers loaded
    reg = KernelRegistry()
    root = Path(__file__).resolve().parent.parent
    load_mod(root / "mods" / "axiom.providers", reg)
    backend = resolve_llm_backend(registry=reg)
    assert backend is not None

    # 3. Safe mode loads axiom.providers
    set_safe_mode(True)
    try:
        sm_reg = KernelRegistry()
        bootstrap_all_mods(sm_reg, AppConfig())
        assert sm_reg.load_state.is_active("axiom.providers")
    finally:
        set_safe_mode(False)


def test_m5_structured_output_dynamic_fields():
    """M5: Verify that output fields (inventory_changes, modifiers, elapsed_minutes)
    are contributed dynamically via slot 'axiom.turn:output_fields' and not hardcoded."""
    from axiom.kernel.registry import KernelRegistry
    from axiom.kernel.loader import load_mod
    from axiom.kernel.context import ModContext
    from mods.axiom.turn.main import build_dynamic_tool_call_schema, _route_output_fields
    from axiom.arbitrator import TurnContext

    root = Path(__file__).resolve().parent.parent

    # 1. Without feature mods: base schema only
    reg_base = KernelRegistry()
    load_mod(root / "mods" / "axiom.turn", reg_base)
    mod_ctx_base = ModContext("axiom.turn", reg_base)
    schema_base = build_dynamic_tool_call_schema(mod_ctx_base)
    assert "inventory_changes" not in schema_base
    assert "modifiers" not in schema_base
    assert "stat_events" not in schema_base
    assert "elapsed_minutes" not in schema_base
    assert "state_changes" in schema_base

    # 2. With axiom.inventory loaded: inventory_changes is dynamically contributed
    reg_inv = KernelRegistry()
    load_mod(root / "mods" / "axiom.turn", reg_inv)
    load_mod(root / "mods" / "axiom.inventory", reg_inv)
    mod_ctx_inv = ModContext("axiom.turn", reg_inv)
    schema_inv = build_dynamic_tool_call_schema(mod_ctx_inv)
    assert "inventory_changes" in schema_inv
    assert "INVENTORY_CHANGES:" in schema_inv
    assert "modifiers" not in schema_inv

    # 3. With core.stat_dynamics loaded: modifiers and stat_events are contributed
    reg_stats = KernelRegistry()
    load_mod(root / "mods" / "axiom.turn", reg_stats)
    load_mod(root / "mods" / "core.stat_dynamics", reg_stats)
    mod_ctx_stats = ModContext("axiom.turn", reg_stats)
    schema_stats = build_dynamic_tool_call_schema(mod_ctx_stats)
    assert "modifiers" in schema_stats
    assert "MODIFIERS:" in schema_stats
    assert "stat_events" in schema_stats

    # 4. With axiom.time loaded: elapsed_minutes is contributed
    reg_time = KernelRegistry()
    load_mod(root / "mods" / "axiom.turn", reg_time)
    load_mod(root / "mods" / "axiom.time", reg_time)
    mod_ctx_time = ModContext("axiom.turn", reg_time)
    schema_time = build_dynamic_tool_call_schema(mod_ctx_time)
    assert "elapsed_minutes" in schema_time
    assert "ELAPSED_MINUTES:" in schema_time

    # 5. Routing test: verify _route_output_fields executes handlers
    routed = []
    reg_custom = KernelRegistry()
    mod_ctx_turn = ModContext("axiom.turn", reg_custom)
    mod_ctx_custom = ModContext("test.custom", reg_custom)
    mod_ctx_custom.contribute_slot(
        "axiom.turn:output_fields",
        {"name": "custom_field", "handler": lambda val, ctx: routed.append(val)}
    )
    turn_ctx = TurnContext(
        save_id="s1",
        step_id=1,
        user_input="hi",
        player_entity_id="player",
        verbosity="normal",
    )
    turn_ctx.parsed_tool_call = {"custom_field": "hello_custom"}
    _route_output_fields(turn_ctx, mod_ctx_turn)
    assert routed == ["hello_custom"]


def test_disabled_mod_not_executed_during_turn(test_env):
    """Verify that when a mod is disabled via config, none of its turn slots or prompt sections run,
    while its storage declarations remain present for system integrity."""
    from axiom.kernel.context import ModContext
    from axiom.kernel.registry import KernelRegistry
    from axiom.kernel.loader import bootstrap_all_mods
    from axiom.config import AppConfig
    from axiom.storage_registry import find_storage_spec

    cfg = AppConfig()
    cfg.mod_settings["axiom.inventory"] = {"enabled": False}

    reg = KernelRegistry()
    bootstrap_all_mods(reg, cfg)

    assert not reg.load_state.is_active("axiom.inventory")

    # Turn context slots must not execute / must not expose inactive mod contributions
    mod_ctx = ModContext("axiom.turn", reg)
    entries = mod_ctx.get_slot_entries("axiom.turn:output_fields")
    assert not any(mod_id == "axiom.inventory" for mod_id, _ in entries)

    # But its storage spec is registered
    assert find_storage_spec("Item_Instances") is not None
    assert find_storage_spec("Inventory_Snapshots") is not None


def test_disabled_mod_rewind_fork_and_reactivation_consistency(test_env):
    """Verify that when a mod (e.g. axiom.inventory or core.stat_dynamics) is disabled,
    a rewind or fork still processes its storage faithfully via storage.py,
    and upon reactivation all data is consistent."""
    import json
    import sqlite3
    from axiom.db_helpers import create_new_save
    from axiom.saves import fork_save
    from axiom.storage_registry import execute_rewind
    from axiom.kernel.registry import KernelRegistry
    from axiom.kernel.loader import bootstrap_all_mods
    from axiom.config import AppConfig
    from axiom.schema import ensure_inventory_snapshots_table, ensure_modifier_snapshots_table
    from axiom.events import EventSourcer

    db_path = test_env["db_path"]
    save_id = create_new_save(db_path, "Hero", "Normal")

    with get_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        ensure_inventory_snapshots_table(conn)
        ensure_modifier_snapshots_table(conn)

        conn.execute(
            "INSERT OR REPLACE INTO Item_Definitions (item_id, name) VALUES ('potion', 'Potion'), ('sword', 'Sword');"
        )

        # Tour 1: 1 item et 1 modifier
        conn.execute(
            "INSERT INTO Item_Instances (instance_id, save_id, item_id, quantity, holder_kind, holder_id) "
            "VALUES ('inst_t1', ?, 'potion', 1, 'entity', 'player');",
            (save_id,),
        )
        snap_t1 = [{"instance_id": "inst_t1", "item_id": "potion", "quantity": 1, "holder_kind": "entity", "holder_id": "player"}]
        conn.execute(
            "INSERT INTO Inventory_Snapshots (save_id, turn_id, state_json) VALUES (?, 1, ?);",
            (save_id, json.dumps(snap_t1)),
        )
        conn.execute(
            "INSERT INTO Active_Modifiers (modifier_id, save_id, entity_id, stat_key, delta, minutes_remaining) "
            "VALUES ('mod_t1', ?, 'player', 'Health', -5.0, 999);",
            (save_id,),
        )
        mod_snap_t1 = [{"modifier_id": "mod_t1", "entity_id": "player", "stat_key": "Health", "delta": -5.0, "minutes_remaining": 999}]
        conn.execute(
            "INSERT INTO Modifier_Snapshots (save_id, turn_id, state_json) VALUES (?, 1, ?);",
            (save_id, json.dumps(mod_snap_t1)),
        )

        # Tour 2: 1 item en plus, 1 modifier en plus
        conn.execute(
            "INSERT INTO Item_Instances (instance_id, save_id, item_id, quantity, holder_kind, holder_id) "
            "VALUES ('inst_t2', ?, 'sword', 1, 'entity', 'player');",
            (save_id,),
        )
        snap_t2 = snap_t1 + [{"instance_id": "inst_t2", "item_id": "sword", "quantity": 1, "holder_kind": "entity", "holder_id": "player"}]
        conn.execute(
            "INSERT INTO Inventory_Snapshots (save_id, turn_id, state_json) VALUES (?, 2, ?);",
            (save_id, json.dumps(snap_t2)),
        )
        conn.execute(
            "INSERT INTO Active_Modifiers (modifier_id, save_id, entity_id, stat_key, delta, minutes_remaining) "
            "VALUES ('mod_t2', ?, 'player', 'Coin', 10.0, 60);",
            (save_id,),
        )
        mod_snap_t2 = mod_snap_t1 + [{"modifier_id": "mod_t2", "entity_id": "player", "stat_key": "Coin", "delta": 10.0, "minutes_remaining": 60}]
        conn.execute(
            "INSERT INTO Modifier_Snapshots (save_id, turn_id, state_json) VALUES (?, 2, ?);",
            (save_id, json.dumps(mod_snap_t2)),
        )
        conn.commit()

    es = EventSourcer(db_path)
    es.append_events_batch([
        (save_id, 1, "stat_set", "player", {"entity_id": "player", "stat_key": "Health", "value": "90"}),
        (save_id, 2, "stat_set", "player", {"entity_id": "player", "stat_key": "Health", "value": "80"}),
    ])

    # Configuration avec les deux mods désactivés
    cfg_disabled = AppConfig()
    cfg_disabled.mod_settings["axiom.inventory"] = {"enabled": False}
    cfg_disabled.mod_settings["core.stat_dynamics"] = {"enabled": False}
    reg_disabled = KernelRegistry()
    bootstrap_all_mods(reg_disabled, cfg_disabled)
    assert not reg_disabled.load_state.is_active("axiom.inventory")
    assert not reg_disabled.load_state.is_active("core.stat_dynamics")

    # Forker la save au tour 1 pendant que les mods sont désactivés
    forked_id = fork_save(db_path, save_id, at_turn=1)

    # Rewinder la save source au tour 1 pendant que les mods sont désactivés
    with get_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        execute_rewind(conn, save_id, 1)
        conn.commit()

    # Réactiver les mods (nouveau bootstrap avec config par défaut)
    cfg_enabled = AppConfig()
    reg_enabled = KernelRegistry()
    bootstrap_all_mods(reg_enabled, cfg_enabled)
    assert reg_enabled.load_state.is_active("axiom.inventory")
    assert reg_enabled.load_state.is_active("core.stat_dynamics")

    with get_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        # Vérifier la save rewindée
        rewound_items = conn.execute(
            "SELECT item_id, quantity FROM Item_Instances WHERE save_id = ? ORDER BY item_id;",
            (save_id,),
        ).fetchall()
        assert len(rewound_items) == 1
        assert rewound_items[0]["item_id"] == "potion"

        rewound_mods = conn.execute(
            "SELECT stat_key, delta FROM Active_Modifiers WHERE save_id = ?;",
            (save_id,),
        ).fetchall()
        assert len(rewound_mods) == 1
        assert rewound_mods[0]["stat_key"] == "Health"

        # Vérifier la save forked
        forked_items = conn.execute(
            "SELECT item_id, quantity, instance_id FROM Item_Instances WHERE save_id = ? ORDER BY item_id;",
            (forked_id,),
        ).fetchall()
        assert len(forked_items) == 1
        assert forked_items[0]["item_id"] == "potion"
        assert forked_items[0]["instance_id"] != "inst_t1"  # remapped

        forked_mods = conn.execute(
            "SELECT stat_key, delta, modifier_id FROM Active_Modifiers WHERE save_id = ?;",
            (forked_id,),
        ).fetchall()
        assert len(forked_mods) == 1
        assert forked_mods[0]["stat_key"] == "Health"
        assert forked_mods[0]["modifier_id"] != "mod_t1"  # remapped



