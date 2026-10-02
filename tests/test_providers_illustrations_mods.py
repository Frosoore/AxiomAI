"""tests/test_providers_illustrations_mods.py

Acceptance tests for Phase 2:
- axiom.providers (LLM Drivers & Inference Providers)
- axiom.illustrations (AI Scene & Character Illustration Generator)
- Universe-as-Code Hooks (compile, decompile, refresh_definition)

Validates:
1. Dynamic registration of third-party LLM drivers via axiom.providers:drivers and selection as active backend.
2. Illustration asset generation and surgical cleanup via custom storage callback on rewind.
3. Extensible Universe-as-Code: compilation and decompilation hooks preserving custom mod data.
4. Autonomous Session construction with no explicit LLM passed (resolved via axiom.turn:llm_backend).
"""

from __future__ import annotations

import sqlite3
import tomllib
from pathlib import Path
import pytest
import tomlkit

import axiom.paths
from axiom.compile import compile_universe
from axiom.decompile import decompile_universe
from axiom.dev import refresh_definition
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
from axiom.storage_registry import execute_rewind
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
        "data_dir": data_dir,
    }


def test_manifests_and_loading(tmp_path: Path):
    """1. Manifest compliance and archive loading for providers and illustrations."""
    root = Path(__file__).resolve().parent.parent
    prov_dir = root / "mods" / "axiom.providers"
    illus_dir = root / "mods" / "axiom.illustrations"

    # Manifest axiom.providers
    prov_m = parse_manifest_file(prov_dir / "mod.toml")
    assert prov_m.id == "axiom.providers"
    assert "axiom.turn:llm_backend" in prov_m.contributes.slots
    assert "axiom.providers:drivers" in prov_m.provides_slots

    # Manifest axiom.illustrations
    illus_m = parse_manifest_file(illus_dir / "mod.toml")
    assert illus_m.id == "axiom.illustrations"
    assert "axiom.step:after_step" in illus_m.contributes.hooks
    assert "assets" in illus_m.storage
    assert illus_m.storage["assets"].get("policy") == "custom"

    # Loading archives (packed in tmp_path: dist/ is not versioned)
    from axiom.cli.mods_cmd import pack_mod
    reg = KernelRegistry()
    load_mod_from_archive(pack_mod(prov_dir, tmp_path / "axiom.providers.axmod"), reg)
    load_mod_from_archive(pack_mod(illus_dir, tmp_path / "axiom.illustrations.axmod"), reg)
    assert reg.get_service("providers") is not None
    assert reg.get_service("illustrations") is not None


def test_custom_driver_registration_and_activation(test_env):
    """2. Third-party mod contributing a custom driver to axiom.providers:drivers."""
    uni_db = test_env["uni_db"]
    save_info = create_save(str(uni_db), player_name="Hero", difficulty="Normal")
    save_id = save_info["save_id"]
    save_db = save_info["db_path"]

    root = Path(__file__).resolve().parent.parent
    reg = KernelRegistry()
    load_mod(root / "mods" / "axiom.world", reg)
    load_mod(root / "mods" / "axiom.turn", reg)
    load_mod(root / "mods" / "axiom.providers", reg)

    # Register custom mock driver
    custom_backend = ScriptedLLMBackend(
        responses=[
            ScriptedTurnResponse(
                narrative_chunks=["The custom LLM driver resolved the turn successfully."],
                tool_call={
                    "narration": "The custom LLM driver resolved the turn successfully.",
                    "stats": {"Health": 98},
                },
            )
        ]
    )

    prov_svc = reg.get_service("providers")
    assert prov_svc is not None
    prov_svc.register_driver("my_custom_llm", lambda cfg, override=None: custom_backend)

    # Verify driver is listed
    assert "my_custom_llm" in prov_svc.list_drivers()

    # Configure session to use this custom backend
    # Persist the choice in the (isolated) settings: mutating the object returned by
    # load_config() is lost when no settings.json exists, and the Session would then
    # fall back to the default backend (a real Ollama on localhost).
    from axiom.config import load_config, save_config
    cfg = load_config()
    cfg.llm_backend = "my_custom_llm"
    save_config(cfg)

    # Instantiate session with NO explicit llm parameter
    sess = Session(
        save_db,
        save_id,
        llm=None,
        kernel_registry=reg,
    )

    res = sess.take_turn("Test custom provider")
    assert "custom LLM driver" in res.narrative_text


def test_illustrations_and_rewind_cleanup(test_env):
    """3. Truncating PNG assets on rewind via custom storage policy."""
    data_dir = test_env["data_dir"]
    save_id = "test_illus_save"
    assets_dir = data_dir / "assets" / save_id
    assets_dir.mkdir(parents=True, exist_ok=True)

    # Create dummy illustration files
    (assets_dir / "turn_1.png").write_bytes(b"turn 1 image")
    (assets_dir / "turn_2.png").write_bytes(b"turn 2 image")
    (assets_dir / "turn_3.png").write_bytes(b"turn 3 image")

    root = Path(__file__).resolve().parent.parent
    reg = KernelRegistry()
    load_mod(root / "mods" / "axiom.illustrations", reg)
    illus_svc = reg.get_service("illustrations")
    assert illus_svc is not None

    # Test service truncation directly
    removed = illus_svc.truncate_assets(save_id, last_kept_turn_id=1, data_root=data_dir)
    assert removed == 2
    assert (assets_dir / "turn_1.png").exists()
    assert not (assets_dir / "turn_2.png").exists()
    assert not (assets_dir / "turn_3.png").exists()

    # Recreate turn 2 and test rewind via storage_registry
    (assets_dir / "turn_2.png").write_bytes(b"turn 2 image again")
    uni_db = test_env["uni_db"]
    with get_connection(str(uni_db)) as conn:
        execute_rewind(conn, save_id, target_turn_id=1)

    assert (assets_dir / "turn_1.png").exists()
    assert not (assets_dir / "turn_2.png").exists()


def test_universe_as_code_mod_extension(tmp_path: Path):
    """4. Universe-as-Code extension: custom section in universe.toml compiled and decompiled by hooks."""
    src_dir = tmp_path / "custom_universe"
    src_dir.mkdir(parents=True, exist_ok=True)

    # Write a minimal universe.toml with a custom mod section
    uni_toml_content = """
[universe]
name = "Modded Universe"
description = "A universe with custom mod configuration."

[faction_dynamics]
rebellion_index = 42
dominant_faction = "Rebels"
"""
    (src_dir / "universe.toml").write_text(uni_toml_content, encoding="utf-8")

    reg = KernelRegistry()

    # Hook for axiom.universe:compile
    def on_compile(ctx: dict):
        conn = ctx["conn"]
        uni_toml = ctx["universe_toml"]
        conn.execute("CREATE TABLE IF NOT EXISTS Mod_Factions (rebellion_index INT, dominant_faction TEXT);")
        fd = uni_toml.get("faction_dynamics", {})
        if fd:
            conn.execute(
                "INSERT INTO Mod_Factions VALUES (?, ?);",
                (fd.get("rebellion_index", 0), fd.get("dominant_faction", ""))
            )

    # Hook for axiom.universe:decompile
    def on_decompile(ctx: dict):
        db_conn = ctx["db_conn"]
        target_dir = ctx["target_dir"]
        row = db_conn.execute("SELECT rebellion_index, dominant_faction FROM Mod_Factions LIMIT 1;").fetchone()
        if row:
            dest_toml = target_dir / "universe.toml"
            if dest_toml.exists():
                doc = tomlkit.parse(dest_toml.read_text(encoding="utf-8"))
            else:
                doc = tomlkit.document()
            fd_table = tomlkit.table()
            fd_table["rebellion_index"] = row[0]
            fd_table["dominant_faction"] = row[1]
            doc["faction_dynamics"] = fd_table
            dest_toml.write_text(tomlkit.dumps(doc), encoding="utf-8")

    reg.add_hook("axiom.universe:compile", "test_faction_mod", on_compile)
    reg.add_hook("axiom.universe:decompile", "test_faction_mod", on_decompile)

    # 1. Compile with hook
    db_path = tmp_path / "custom_universe.db"
    compile_universe(src_dir, output_db=db_path, force=True, kernel_registry=reg)

    # Verify table in SQLite DB
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute("SELECT rebellion_index, dominant_faction FROM Mod_Factions;").fetchone()
        assert row is not None
        assert row[0] == 42
        assert row[1] == "Rebels"

    # 2. Decompile with hook
    decomp_dir = tmp_path / "decompiled_universe"
    decompile_universe(db_path, decomp_dir, kernel_registry=reg)

    # Verify custom section preserved in decompiled universe.toml
    decomp_toml = decomp_dir / "universe.toml"
    assert decomp_toml.exists()
    with open(decomp_toml, "rb") as f:
        data = tomllib.load(f)
    assert "faction_dynamics" in data
    assert data["faction_dynamics"]["rebellion_index"] == 42
    assert data["faction_dynamics"]["dominant_faction"] == "Rebels"


def test_full_turn_with_all_official_mods_and_implicit_llm(test_env):
    """5. End-to-end game turn with all official mods loaded and LLM resolved automatically."""
    uni_db = test_env["uni_db"]
    save_info = create_save(str(uni_db), player_name="Hero", difficulty="Normal")
    save_id = save_info["save_id"]
    save_db = save_info["db_path"]

    root = Path(__file__).resolve().parent.parent
    reg = KernelRegistry()
    for mod_name in [
        "axiom.world",
        "axiom.turn",
        "core.stat_dynamics",
        "axiom.time",
        "axiom.inventory",
        "axiom.rag",
        "axiom.living_memory",
        "axiom.providers",
        "axiom.illustrations",
    ]:
        load_mod(root / "mods" / mod_name, reg)

    # Scripted LLM returned by providers
    scripted = ScriptedLLMBackend(
        responses=[
            ScriptedTurnResponse(
                narrative_chunks=["You step forward with determination."],
                tool_call={
                    "narration": "You step forward with determination.",
                    "stats": {"Health": 88},
                    "time_elapsed_minutes": 10,
                },
            )
        ]
    )

    prov_svc = reg.get_service("providers")
    prov_svc.register_driver("scripted_test", lambda cfg, override=None: scripted)

    # Persisted in the isolated settings (see test_custom_driver_registration_and_activation):
    # the turn must never reach a real LLM.
    from axiom.config import load_config, save_config
    cfg = load_config()
    cfg.llm_backend = "scripted_test"
    save_config(cfg)

    # Session initialized WITHOUT passing llm parameter
    sess = Session(
        save_db,
        save_id,
        llm=None,
        kernel_registry=reg,
    )

    turn_res = sess.take_turn("March ahead")
    assert "determination" in turn_res.narrative_text
    assert turn_res.elapsed_minutes == 10
