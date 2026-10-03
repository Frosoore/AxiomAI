"""tests/test_mod_kv_and_storage.py

Tests for:
1. Versioned key-value storage (Mod_KV / ModStore / ctx.store) (K9).
2. Rewind behavior on Mod_KV.
3. Fork behavior on Mod_KV.
4. Declarative [storage] registration from mod manifest.
5. Edge cases found by the 2026-10-03 audit: set/delete/set at the same step
   (used to violate the primary key), no implicit step 0, steps never go backwards,
   writes made during a turn committed with the turn only.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from axiom.kernel.context import ModContext
from axiom.kernel.registry import KernelRegistry
from axiom.kernel.kv_store import ModStore
from axiom.schema import create_universe_db, get_connection
from axiom.storage_registry import (
    StoragePolicy,
    TableStorageSpec,
    execute_fork,
    execute_rewind,
    register_table_storage,
    unregister_storage,
)


def test_mod_kv_crud(tmp_path: Path):
    db_file = tmp_path / "game.db"
    create_universe_db(str(db_file))
    save_id = "s_crud"

    store = ModStore("community.hunger")
    assert store.get_at(str(db_file), save_id, "hunger") is None
    assert store.get_at(str(db_file), save_id, "hunger", default=100) == 100

    # Set at step 1
    store.set_at(str(db_file), save_id, "hunger", 90, step=1)
    assert store.get_at(str(db_file), save_id, "hunger") == 90
    assert store.list_keys(str(db_file), save_id) == ["hunger"]

    # Update in-place at step 1
    store.set_at(str(db_file), save_id, "hunger", 85, step=1)
    assert store.get_at(str(db_file), save_id, "hunger") == 85

    # Update at step 2
    store.set_at(str(db_file), save_id, "hunger", 70, step=2)
    assert store.get_at(str(db_file), save_id, "hunger") == 70
    # Historical lookup at step 1
    assert store.get_at(str(db_file), save_id, "hunger", at_step=1) == 85

    # Complex JSON object
    store.set_at(str(db_file), save_id, "buffs", {"well_fed": True, "stamina_boost": 1.2}, step=2)
    assert store.get_at(str(db_file), save_id, "buffs") == {"well_fed": True, "stamina_boost": 1.2}

    # Delete at step 3
    store.delete_at(str(db_file), save_id, "buffs", step=3)
    assert store.get_at(str(db_file), save_id, "buffs") is None
    assert store.get_at(str(db_file), save_id, "buffs", at_step=2) == {"well_fed": True, "stamina_boost": 1.2}


def test_mod_kv_rewind(tmp_path: Path):
    db_file = tmp_path / "game.db"
    create_universe_db(str(db_file))
    save_id = "s_rewind"

    with get_connection(str(db_file)) as conn:
        conn.execute(
            "INSERT INTO Saves (save_id, player_name, difficulty, last_updated) "
            "VALUES (?, 'Hero', 'Normal', '2026-10-03T12:00:00Z');",
            (save_id,),
        )

    store = ModStore("community.hunger")
    store.set_at(str(db_file), save_id, "thirst", 100, step=0)
    store.set_at(str(db_file), save_id, "thirst", 80, step=2)
    store.set_at(str(db_file), save_id, "thirst", 50, step=5)

    assert store.get_at(str(db_file), save_id, "thirst") == 50

    # Rewind to turn 2: step 5 update should be gone, value at step 2 restored!
    with get_connection(str(db_file)) as conn:
        execute_rewind(conn, save_id, target_turn_id=2, external=False)

    assert store.get_at(str(db_file), save_id, "thirst") == 80


def test_mod_kv_fork(tmp_path: Path):
    db_file = tmp_path / "game.db"
    create_universe_db(str(db_file))
    src_save_id = "s_src"
    dst_save_id = "s_fork"

    with get_connection(str(db_file)) as conn:
        conn.execute(
            "INSERT INTO Saves (save_id, player_name, difficulty, last_updated) "
            "VALUES (?, 'Hero', 'Normal', '2026-10-03T12:00:00Z');",
            (src_save_id,),
        )
        conn.execute(
            "INSERT INTO Saves (save_id, player_name, difficulty, last_updated) "
            "VALUES (?, 'Hero', 'Normal', '2026-10-03T12:00:00Z');",
            (dst_save_id,),
        )

    store = ModStore("community.reputation")
    store.set_at(str(db_file), src_save_id, "guild_rep", 10, step=1)
    store.set_at(str(db_file), src_save_id, "guild_rep", 25, step=3)
    store.set_at(str(db_file), src_save_id, "guild_rep", 50, step=8)

    # Fork at turn 3 into dst_save_id
    with get_connection(str(db_file)) as conn:
        execute_fork(conn, src_save_id, dst_save_id, at_turn=3, external=False)

    # Destination save should have the value at turn 3 (25), not turn 8 (50)
    assert store.get_at(str(db_file), dst_save_id, "guild_rep") == 25
    # Source save still has 50
    assert store.get_at(str(db_file), src_save_id, "guild_rep") == 50


def test_declarative_storage_cleanup():
    reg = KernelRegistry()
    spec = TableStorageSpec(
        table_name="Custom_Test_Table",
        policy=StoragePolicy.STEP_KEYED,
        owner="mod.test",
    )
    register_table_storage(spec)

    ctx = ModContext("mod.test", reg)
    ctx._registered_storages.append(spec)
    ctx.cleanup()

    from axiom.storage_registry import _specs
    assert not any(s.table_name == "Custom_Test_Table" for s in _specs())


def _kv_rows(db_file: Path, key: str) -> list[tuple]:
    with get_connection(str(db_file)) as conn:
        return conn.execute(
            "SELECT value, from_step, to_step FROM Mod_KV WHERE key = ? ORDER BY from_step;", (key,)
        ).fetchall()


def test_mod_kv_set_delete_set_same_step(tmp_path: Path):
    db_file = tmp_path / "game.db"
    create_universe_db(str(db_file))
    store = ModStore("m")
    store.set_at(str(db_file), "S", "k", 1, step=5)
    store.delete_at(str(db_file), "S", "k", step=5)
    store.set_at(str(db_file), "S", "k", 2, step=5)  # used to raise IntegrityError
    assert store.get_at(str(db_file), "S", "k") == 2
    assert [tuple(r) for r in _kv_rows(db_file, "k")] == [("2", 5, None)]


def test_mod_kv_step_is_required_and_never_goes_backwards(tmp_path: Path):
    db_file = tmp_path / "game.db"
    create_universe_db(str(db_file))
    store = ModStore("m")
    with pytest.raises(TypeError):
        store.set_at(str(db_file), "S", "k", 1)  # no implicit "since the beginning"
    store.set_at(str(db_file), "S", "k", "a", step=5)
    with pytest.raises(ValueError, match="before the current value"):
        store.set_at(str(db_file), "S", "k", "b", step=3)
    assert [tuple(r) for r in _kv_rows(db_file, "k")] == [('"a"', 5, None)]


def test_mod_kv_turn_writes_are_committed_with_the_turn(tmp_path: Path):
    from types import SimpleNamespace
    from axiom.turn_batch import TurnWriteBatch

    db_file = tmp_path / "game.db"
    create_universe_db(str(db_file))
    with get_connection(str(db_file)) as conn:
        conn.execute(
            "INSERT INTO Saves (save_id, player_name, difficulty, last_updated) "
            "VALUES ('S', 'Hero', 'Normal', '2026-10-03T12:00:00Z');"
        )
    store = ModStore("community.hunger")
    store.set_at(str(db_file), "S", "hunger", 100, step=0)

    # Turn 1: staged, visible to the turn itself, not in the database yet.
    turn = SimpleNamespace(db_path=str(db_file), save_id="S", step_id=1, write_batch=TurnWriteBatch())
    store.set(turn, "hunger", store.get(turn, "hunger") - 10)
    assert store.get(turn, "hunger") == 90
    assert store.get_at(str(db_file), "S", "hunger") == 100

    # A cancelled turn (batch never committed) leaves nothing behind.
    assert [tuple(r) for r in _kv_rows(db_file, "hunger")] == [("100", 0, None)]

    # Committed with the turn, in its transaction.
    with get_connection(str(db_file)) as conn:
        turn.write_batch.commit_all(conn, "S", 1)
    assert store.get_at(str(db_file), "S", "hunger") == 90
    assert store.get_at(str(db_file), "S", "hunger", at_step=0) == 100

    # Deletion staged in a turn.
    turn2 = SimpleNamespace(db_path=str(db_file), save_id="S", step_id=2, write_batch=TurnWriteBatch())
    store.delete(turn2, "hunger")
    assert store.get(turn2, "hunger", "gone") == "gone"
    with get_connection(str(db_file)) as conn:
        turn2.write_batch.commit_all(conn, "S", 2)
    assert store.get_at(str(db_file), "S", "hunger") is None


def test_mod_kv_turn_api_rejects_a_non_turn_context(tmp_path: Path):
    with pytest.raises(TypeError, match="get_at/set_at"):
        ModStore("m").set(object(), "k", 1)


# ---------------------------------------------------------------------------
# Declarative [storage] of the manifest (DOC §10.2)
# ---------------------------------------------------------------------------

def _storage_mod(root: Path, mod_id: str, storage: str, main: str = "def init(ctx):\n    pass\n") -> None:
    d = root / mod_id
    d.mkdir(parents=True)
    (d / "mod.toml").write_text(
        f'[mod]\nid = "{mod_id}"\nversion = "1.0.0"\naxiom_api = 1\nname = "S"\n\n[storage]\n{storage}\n',
        encoding="utf-8",
    )
    (d / "main.py").write_text(main, encoding="utf-8")


def test_manifest_storage_validation_errors():
    from axiom.kernel.manifest import ManifestError, parse_manifest_string

    base = '[mod]\nid = "x.y"\nversion = "1.0.0"\naxiom_api = 1\nname = "x"\n\n[storage]\n'
    for bad in (
        'a = { policy = "nonsense" }',
        'a = { policy = "step_keyed_table" }',                                  # no columns
        'a = { policy = "step_keyed_table", columns = ["save_id", "x"] }',      # step_column not a column
        'a = { policy = "step_keyed_table", columns = ["turn_id", "x"] }',      # no save_id
        'a = ["T"]',                                                            # old list form
        'a = { policy = "custom", tabel = "T" }',                               # typo: unknown key
    ):
        with pytest.raises(ManifestError):
            parse_manifest_string(base + bad)
    m = parse_manifest_string(base + 'hunger = { policy = "versioned_kv" }')
    assert m.storage == {"hunger": {"policy": "versioned_kv"}}


def test_manifest_step_keyed_table_is_registered_rewound_and_kept_while_disabled(tmp_path: Path):
    from axiom.config import AppConfig
    from axiom.kernel.loader import bootstrap_all_mods, get_mod_status
    from axiom.storage_registry import find_storage_spec

    extra = tmp_path / "mods"
    _storage_mod(
        extra, "probe.hunger",
        'log = { policy = "step_keyed_table", table = "Probe_Hunger", '
        'columns = ["save_id", "turn_id", "level"] }',
    )
    reg = bootstrap_all_mods(KernelRegistry(), AppConfig(), extra_dirs=[extra])
    assert get_mod_status("probe.hunger", reg).state == "active"
    spec = find_storage_spec("probe_hunger")  # case-insensitive, like SQLite
    assert spec is not None and spec.owner == "probe.hunger"

    db_file = tmp_path / "game.db"
    create_universe_db(str(db_file))
    with get_connection(str(db_file)) as conn:
        conn.execute("INSERT INTO Saves (save_id, player_name, difficulty, last_updated) VALUES ('S','H','Normal','x'), ('F','H','Normal','x');")
        conn.execute("CREATE TABLE Probe_Hunger (save_id TEXT, turn_id INTEGER, level INTEGER);")
        conn.executemany("INSERT INTO Probe_Hunger VALUES ('S', ?, ?);", [(1, 90), (2, 80), (3, 70)])
    with get_connection(str(db_file)) as conn:
        execute_rewind(conn, "S", target_turn_id=1, external=False)
        execute_fork(conn, "S", "F", at_turn=1, external=False)
    with get_connection(str(db_file)) as conn:
        rows = conn.execute("SELECT save_id, turn_id, level FROM Probe_Hunger ORDER BY save_id;").fetchall()
    assert [tuple(r) for r in rows] == [("F", 1, 90), ("S", 1, 90)]

    # Disabled, the mod's data still follows rewinds and forks (owner decision
    # 2026-10-03): its storage stays registered while it is installed.
    reg.load_state.disable("probe.hunger")
    assert find_storage_spec("Probe_Hunger") is not None


def test_manifest_storage_conflict_and_missing_custom_reject_only_that_mod(tmp_path: Path):
    from axiom.config import AppConfig
    from axiom.kernel.loader import bootstrap_all_mods, get_mod_status

    extra = tmp_path / "mods"
    # Event_Log is the kernel journal (EVENTS): claiming it as a step-keyed table is a conflict.
    _storage_mod(
        extra, "probe.thief",
        'x = { policy = "step_keyed_table", table = "event_log", '
        'columns = ["save_id", "turn_id", "payload"] }',
    )
    # Declares a custom storage it never registers.
    _storage_mod(extra, "probe.liar", 'cache = { policy = "custom" }')
    # Declares and registers it: fine.
    _storage_mod(
        extra, "probe.honest", 'cache2 = { policy = "custom" }',
        "def init(ctx):\n    ctx.register_storage('cache2', rewind_callback=lambda c, s, t: None)\n",
    )
    reg = bootstrap_all_mods(KernelRegistry(), AppConfig(), extra_dirs=[extra])
    thief, liar, honest = (get_mod_status(m, reg) for m in ("probe.thief", "probe.liar", "probe.honest"))
    assert thief.state == "failed" and "already registered" in thief.reason
    assert liar.state == "failed" and "was not registered" in liar.reason
    assert honest.state == "active"
    assert get_mod_status("axiom.turn", reg).state == "active"
