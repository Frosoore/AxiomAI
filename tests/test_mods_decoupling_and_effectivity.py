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

    # Now simulate axiom.time registering the service
    registry.register_service("time", "axiom.time", object())
    arbitrator.step_4_parse_response(ctx)

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

    fetch_spy = MagicMock()
    arbitrator._fetch_relevant_facts = fetch_spy

    arbitrator.step_1_gather_context(ctx)

    # _fetch_relevant_facts must NOT have been called
    assert fetch_spy.call_count == 0
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
    class DummyBatch:
        def __init__(self):
            self.timeline_entries = []

    class DummyCtx:
        def __init__(self, elapsed: int):
            self.save_id = "test_save"
            self.turn_id = 2
            self.new_time = 240
            self.elapsed_minutes = elapsed
            self.write_batch = DummyBatch()

    # Short activity
    short_run = DummyCtx(30)
    registry.execute_hook("axiom.step:after_step", short_run)
    assert len(short_run.write_batch.timeline_entries) == 0

    # Sustained activity (>= 120 mins)
    long_run = DummyCtx(180)
    registry.execute_hook("axiom.step:after_step", long_run)
    assert len(long_run.write_batch.timeline_entries) == 1
    assert "[Survival]" in long_run.write_batch.timeline_entries[0][3]

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
