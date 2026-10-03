"""tests/test_stat_dynamics_mod.py

Acceptance tests for Phase 2: core.stat_dynamics mod extraction.
Validates:
1. Manifest declarative compliance and packaging into .axmod archive.
2. Mod loading from both unpacked directory and .axmod ZIP archive.
3. TurnContext hooks calculation (arbitrate_stats passive decay & after_step modifier ticks).
4. Full deactivation and reversibility (Rule D11): engine runs without crash and without gauge decay.
"""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import pytest

from axiom.arbitrator import ArbitratorEngine, TurnContext
from axiom.cli.mods_cmd import pack_mod
from axiom.kernel import (
    KernelRegistry,
    load_manifest,
    load_mod,
    load_mod_from_archive,
    load_mod_from_dir,
    parse_manifest_file,
)
from axiom.schema import create_universe_db, get_connection


@pytest.fixture
def temp_universe_db(tmp_path: Path) -> Path:
    """Creates a temporary SQLite universe DB with stat definitions."""
    db_path = tmp_path / "universe.db"
    create_universe_db(str(db_path))

    with get_connection(str(db_path)) as conn:
        # Stat with heal dynamic profile: drifts to 100 over 60 in-game minutes
        conn.execute(
            """
            INSERT INTO Stat_Definitions (stat_id, name, description, value_type, parameters)
            VALUES (?, ?, ?, ?, ?);
            """,
            (
                "Health",
                "Health",
                "Vitality pool",
                "numeric",
                json.dumps({
                    "temporary": True,
                    "dynamics": {
                        "kind": "heal",
                        "min": 0,
                        "max": 100,
                        "resting": 100,
                        "heal_minutes": 60,
                    }
                }),
            )
        )
        # Buildup stat: max 100, resting 0, crash on "calm_down"
        conn.execute(
            """
            INSERT INTO Stat_Definitions (stat_id, name, description, value_type, parameters)
            VALUES (?, ?, ?, ?, ?);
            """,
            (
                "Panic",
                "Panic",
                "Stress meter",
                "numeric",
                json.dumps({
                    "temporary": True,
                    "dynamics": {
                        "kind": "buildup",
                        "min": 0,
                        "max": 100,
                        "resting": 0,
                        "crash_on": ["calm_down"],
                        "peak_hold_minutes": 10,
                    }
                }),
            )
        )
        conn.execute("INSERT INTO Saves (save_id, player_name, difficulty, last_updated) VALUES (?, ?, ?, ?);",
                     ("save_test", "Hero", "Normal", "2026-01-01T00:00:00"))
        conn.execute("INSERT INTO Entities (entity_id, entity_type, name, is_active) VALUES (?, ?, ?, ?);",
                     ("player", "player", "Hero", 1))
        conn.commit()

    return db_path


class TestCoreStatDynamicsMod:
    """Acceptance test suite for core.stat_dynamics mod."""

    MOD_DIR = Path("mods/core.stat_dynamics").resolve()

    def test_manifest_compliance(self) -> None:
        """Verify mod.toml matches declarative spec."""
        manifest_file = self.MOD_DIR / "mod.toml"
        assert manifest_file.is_file(), "Missing mod.toml in mod directory"

        manifest = parse_manifest_file(manifest_file)
        assert manifest.id == "core.stat_dynamics"
        assert manifest.version == "1.0.0"
        assert manifest.axiom_api == 1
        assert "axiom.turn:arbitrate_stats" in manifest.contributes.hooks
        assert "axiom.step:after_step" in manifest.contributes.hooks
        assert manifest.storage["active_modifiers"]["policy"] == "custom"
        assert manifest.storage["active_modifiers"]["table"] == "Active_Modifiers"
        assert manifest.storage["modifier_snapshots"]["policy"] == "step_keyed_table"
        assert manifest.storage["modifier_snapshots"]["table"] == "Modifier_Snapshots"

    def test_load_from_directory(self) -> None:
        """Verify mod loads directly from unpacked directory."""
        registry = KernelRegistry()
        manifest, mod_ctx, module = load_mod_from_dir(self.MOD_DIR, registry)

        assert manifest.id == "core.stat_dynamics"
        assert registry.has_hook("axiom.turn:arbitrate_stats")
        assert registry.has_hook("axiom.step:after_step")

    def test_pack_and_load_from_axmod_archive(self, tmp_path: Path) -> None:
        """Verify CLI pack utility creates .axmod and kernel loads it cleanly."""
        axmod_path = tmp_path / "test_stat_dynamics.axmod"
        packed_path = pack_mod(self.MOD_DIR, axmod_path)
        assert packed_path.is_file()

        registry = KernelRegistry()
        manifest, mod_ctx, module = load_mod_from_archive(packed_path, registry)

        assert manifest.id == "core.stat_dynamics"
        assert registry.has_hook("axiom.turn:arbitrate_stats")
        assert registry.has_hook("axiom.step:after_step")

    def test_hook_arbitrate_stats_heal_calculation(self, temp_universe_db: Path) -> None:
        """Verify axiom.turn:arbitrate_stats correctly computes passive healing and batch mutations."""
        registry = KernelRegistry()
        load_mod_from_dir(self.MOD_DIR, registry)

        # Health is at 80, resting at 100, heal_minutes is 60.
        # Over 30 minutes, it should heal by +10 to 90.
        ctx = TurnContext(
            save_id="save_test",
            step_id=1,
            user_input="Resting by the fire",
            player_entity_id="player",
            verbosity="balanced",
            db_path=str(temp_universe_db),
            elapsed_minutes=30,
            all_stats={"player": {"Health": "80"}},
        )

        results = registry.execute_hook("axiom.turn:arbitrate_stats", ctx)
        assert len(results) == 1

        # Check all_stats updated in memory
        assert ctx.all_stats["player"]["Health"] == "90"

        # Check applied_changes record
        assert len(ctx.applied_changes) == 1
        assert ctx.applied_changes[0]["stat_key"] == "Health"
        assert ctx.applied_changes[0]["value"] == "90"
        assert ctx.applied_changes[0]["reason"] == "heal"

        # Check write_batch events
        assert len(ctx.write_batch.events) == 1
        evt_save, evt_turn, evt_type, evt_target, payload = ctx.write_batch.events[0]
        assert evt_type == "stat_set"
        assert evt_target == "player"
        assert payload["value"] == "90"
        assert payload["source"] == "dynamics"

    def test_hook_arbitrate_stats_crash_event(self, temp_universe_db: Path) -> None:
        """Verify crash_on events snap buildup meters to resting and clear modifiers."""
        registry = KernelRegistry()
        load_mod_from_dir(self.MOD_DIR, registry)

        # Panic is at 90 (resting 0). "calm_down" event triggers crash.
        ctx = TurnContext(
            save_id="save_test",
            step_id=2,
            user_input="Deep breath",
            player_entity_id="player",
            verbosity="balanced",
            db_path=str(temp_universe_db),
            elapsed_minutes=5,
            stat_events=[{"entity_id": "player", "event": "calm_down"}],
            all_stats={"player": {"Panic": "90"}},
        )

        registry.execute_hook("axiom.turn:arbitrate_stats", ctx)

        assert ctx.all_stats["player"]["Panic"] == "0"
        assert any(c["reason"] == "crash" for c in ctx.applied_changes)
        assert len(ctx.write_batch.staged_ops) >= 1
        with get_connection(str(temp_universe_db)) as conn:
            conn.execute(
                "INSERT INTO Active_Modifiers (modifier_id, save_id, entity_id, stat_key, delta, minutes_remaining) "
                "VALUES ('m1', 'save_test', 'player', 'Panic', 10, 60);"
            )
            for op in ctx.write_batch.staged_ops:
                op(conn, "save_test", 2)
            rem = conn.execute("SELECT COUNT(*) FROM Active_Modifiers WHERE save_id = 'save_test';").fetchone()[0]
            assert rem == 0

    def test_hook_after_step_modifier_mutations(self, temp_universe_db: Path) -> None:
        """Verify axiom.step:after_step registers tick mutations in TurnWriteBatch."""
        registry = KernelRegistry()
        load_mod_from_dir(self.MOD_DIR, registry)

        ctx = TurnContext(
            save_id="save_test",
            step_id=4,
            user_input="Travel",
            player_entity_id="player",
            verbosity="balanced",
            elapsed_minutes=45,
            db_path=str(temp_universe_db),
        )

        registry.execute_hook("axiom.step:after_step", ctx)

        assert len(ctx.write_batch.staged_ops) == 1
        with get_connection(str(temp_universe_db)) as conn:
            conn.execute(
                "INSERT INTO Active_Modifiers (modifier_id, save_id, entity_id, stat_key, delta, minutes_remaining) "
                "VALUES ('m1', 'save_test', 'player', 'Buff', 10, 60);"
            )
            for op in ctx.write_batch.staged_ops:
                op(conn, "save_test", 4)
            mins = conn.execute("SELECT minutes_remaining FROM Active_Modifiers WHERE modifier_id = 'm1';").fetchone()[0]
            assert mins == 15  # 60 - 45

    def test_mod_deactivation_reversibility_rule_d11(self, temp_universe_db: Path) -> None:
        """Verify Rule D11: When mod is deactivated, turn executes without crash and without decay."""
        registry = KernelRegistry()
        manifest, mod_ctx, module = load_mod_from_dir(self.MOD_DIR, registry)

        # Unregister / deactivate mod
        mod_ctx.cleanup()
        assert not registry.has_hook("axiom.turn:arbitrate_stats")
        assert not registry.has_hook("axiom.step:after_step")

        # Execute turn context with arbitrator
        engine = ArbitratorEngine(str(temp_universe_db), [], kernel_registry=registry)
        ctx = TurnContext(
            save_id="save_test",
            step_id=1,
            user_input="Pass time",
            player_entity_id="player",
            verbosity="balanced",
            db_path=str(temp_universe_db),
            elapsed_minutes=60,
            all_stats={"player": {"Health": "80"}},
            auto_commit=False,
        )

        engine.step_5_arbitrate_rules(ctx)
        engine.step_6_stage_mutations(ctx)

        # Health must remain unmodified (passive behavior)
        assert ctx.all_stats["player"]["Health"] == "80"
        assert len(ctx.applied_changes) == 0

        # No modifier tick or snapshot mutations staged
        assert len(ctx.write_batch.staged_ops) == 0
