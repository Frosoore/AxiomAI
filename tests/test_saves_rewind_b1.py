"""Lot B1 (corrections 2026-10) — the proofs the audit of 2026-10-03 found missing.

- TICKET-088: a fork keeps the living memory (facts -> beliefs -> mental models),
  with the source ids remapped;
- a fork at turn N while the source is further ahead equals the source at turn N
  (golden canonicalizer, every runtime table of the storage registry, Mod_KV included);
- mods' schema migrations are applied when a save is created and when it is opened;
- an epoch check and its write are atomic with respect to a rewind (bump);
- an aborted turn leaves no item definition behind (0d);
- external stores (vector memory, images) are rewound only after the SQL commit:
  a failing SQL rewind leaves them untouched (TICKET-100).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

import pytest

import axiom.paths
from axiom.backends.base import GenerationCancelled, LLMResponse
from axiom.compile import compile_universe
from axiom.config import AppConfig
from axiom.saves import fork_save
from axiom.savestore import create_save
from axiom.schema import create_universe_db, ensure_facts_table, get_connection
from axiom.session import Session
from axiom.testing.golden_harness import (
    ScriptedLLMBackend,
    ScriptedTurnResponse,
    SessionStateCanonicalizer,
)


def _rows(db: str, sql: str, params: tuple = ()) -> list[tuple]:
    with get_connection(db) as conn:
        return [tuple(r) for r in conn.execute(sql, params).fetchall()]


# ---------------------------------------------------------------------------
# TICKET-088 — fork keeps the living memory
# ---------------------------------------------------------------------------

def test_fork_keeps_living_memory_with_remapped_sources(tmp_path: Path):
    db = str(tmp_path / "u.db")
    create_universe_db(db)
    with get_connection(db) as conn:
        ensure_facts_table(conn)
        conn.execute(
            "INSERT INTO Saves (save_id, player_name, difficulty, last_updated, player_persona) "
            "VALUES ('S', 'P', 'Normal', 'x', '');"
        )
        for t in (1, 2, 3):
            conn.execute(
                "INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) "
                "VALUES ('S', ?, 'user_input', 'player', '{}');", (t,),
            )
        fact_ids = [
            conn.execute(
                "INSERT INTO Facts (save_id, turn_id, statement, fact_type) VALUES ('S', ?, ?, 'world');",
                (t, f"fact {t}"),
            ).lastrowid
            for t in (1, 2, 3)
        ]
        obs_id = conn.execute(
            "INSERT INTO Observations (save_id, subject, statement, proof_count, sources, history, "
            "created_turn_id, updated_turn_id, stale) VALUES ('S', 'hero', 'brave', 2, ?, '[]', 2, 2, 0);",
            (json.dumps([{"fact_id": fact_ids[0], "turn_id": 1}, {"fact_id": fact_ids[1], "turn_id": 2}]),),
        ).lastrowid
        conn.execute(
            "INSERT INTO Mental_Models (save_id, subject, summary, sources, created_turn_id, "
            "updated_turn_id, stale) VALUES ('S', 'hero', 'a brave hero', ?, 2, 2, 0);",
            (json.dumps([obs_id]),),
        )

    new_id = fork_save(db, "S", at_turn=2, player_name="F")

    facts = _rows(db, "SELECT fact_id, statement FROM Facts WHERE save_id = ? ORDER BY turn_id;", (new_id,))
    assert [f[1] for f in facts] == ["fact 1", "fact 2"]           # turn 3 not copied
    new_fact_ids = {f[0] for f in facts}
    assert not new_fact_ids & set(fact_ids)                        # new ids, not the source's
    obs = _rows(db, "SELECT observation_id, statement, sources FROM Observations WHERE save_id = ?;", (new_id,))
    assert [o[1] for o in obs] == ["brave"]
    assert {src["fact_id"] for src in json.loads(obs[0][2])} == new_fact_ids  # sources remapped
    mm = _rows(db, "SELECT summary, sources FROM Mental_Models WHERE save_id = ?;", (new_id,))
    assert mm[0][0] == "a brave hero"
    assert json.loads(mm[0][1]) == [obs[0][0]]                     # sources remapped


# ---------------------------------------------------------------------------
# Fork in the middle of a game == source at that turn (golden canonicalizer)
# ---------------------------------------------------------------------------

@pytest.fixture
def myria(tmp_path: Path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    axiom.paths.configure(data_dir=data_dir)
    try:
        src = Path(__file__).resolve().parent.parent / "universes" / "Myria"
        uni_db = compile_universe(src, tmp_path / "myria.db", force=True)
        with get_connection(str(uni_db)) as conn:
            conn.execute(
                "INSERT INTO Entities (entity_id, entity_type, entity_role, name, is_active) "
                "VALUES ('player', 'player', 'player', 'Hero', 1);"
            )
            conn.execute(
                "INSERT INTO Entity_Stats (entity_id, stat_key, stat_value) VALUES "
                "('player', 'Health', '100'), ('player', 'Coin', '50'), "
                "('player', 'Location', 'gilded_compass');"
            )
        yield uni_db
    finally:
        axiom.paths.reset()


def test_mid_game_fork_equals_source_at_that_turn(myria):
    from axiom.kernel.kv_store import ModStore

    info = create_save(myria, "Hero", "Normal")
    save_id, save_db = info["save_id"], info["db_path"]
    turns = [
        ScriptedTurnResponse(["You walk to Highport."], {
            "state_changes": [{"entity_id": "player", "stat_key": "Location", "value": "highport"}],
            "elapsed_minutes": 10}),
        ScriptedTurnResponse(["You find a satchel."], {
            "inventory_changes": [{"action": "add", "item_id": "satchel", "name": "Satchel",
                                   "quantity": 1, "is_container": True,
                                   "holder_kind": "entity", "holder_id": "player"}],
            "elapsed_minutes": 5}),
        ScriptedTurnResponse(["You are paid."], {
            "state_changes": [{"entity_id": "player", "stat_key": "Coin", "delta": 25}],
            "elapsed_minutes": 20}),
        ScriptedTurnResponse(["You get hurt."], {
            "state_changes": [{"entity_id": "player", "stat_key": "Health", "delta": -10}],
            "elapsed_minutes": 15}),
    ]
    llm = ScriptedLLMBackend(turns)
    session = Session(save_db, save_id, llm=llm, time_llm=llm)
    store = ModStore("probe.kv")
    for i in range(1, 5):
        session.take_turn(f"Turn {i}")
        store.set_at(save_db, save_id, "counter", i, step=i)   # a mod's versioned key-value
        with get_connection(save_db) as conn:                   # a living-memory fact per turn
            ensure_facts_table(conn)
            conn.execute(
                "INSERT INTO Facts (save_id, turn_id, statement, fact_type) VALUES (?, ?, ?, 'world');",
                (save_id, i, f"fact {i}"),
            )
    assert session.turn_id == 4

    expected = SessionStateCanonicalizer.canonicalize(save_db, save_id, at_turn=2)
    forked_id = fork_save(save_db, save_id, at_turn=2)       # source still at turn 4
    forked = SessionStateCanonicalizer.canonicalize(save_db, forked_id)

    diff = SessionStateCanonicalizer.diff(expected, forked)
    assert diff == [], "Mid-game fork drift:\n" + "".join(diff)
    assert store.get_at(save_db, forked_id, "counter") == 2
    assert session.turn_id == 4 and store.get_at(save_db, save_id, "counter") == 4


# ---------------------------------------------------------------------------
# Mods' schema migrations (0e)
# ---------------------------------------------------------------------------

def test_mod_migrations_applied_on_create_and_on_open(tmp_path: Path):
    from axiom.kernel.context import ModContext
    from axiom.kernel.manifest import ModManifest, ModOrdering
    from axiom.kernel.registry import KernelRegistry
    from axiom.storage_registry import get_registered_mod_migrations

    reg = KernelRegistry()
    manifest = ModManifest(id="x.hunger", name="h", version="1.0.0", axiom_api=1, ordering=ModOrdering())
    ctx = ModContext(manifest, reg)
    try:
        ctx.register_migrations(1, {
            0: lambda c: c.execute("CREATE TABLE IF NOT EXISTS Hunger (save_id TEXT, turn_id INTEGER, v INTEGER);"),
        })
        uni = str(tmp_path / "w.db")
        create_universe_db(uni)
        info = create_save(uni, "P", "Normal")
        cols = [r[1] for r in _rows(info["db_path"], "PRAGMA table_info(Hunger);")]
        assert cols == ["save_id", "turn_id", "v"]

        # The mod is updated (version 2): applied when the save is opened.
        ctx.cleanup()
        ctx = ModContext(manifest, reg)
        ctx.register_migrations(2, {
            0: lambda c: c.execute("CREATE TABLE IF NOT EXISTS Hunger (save_id TEXT, turn_id INTEGER, v INTEGER);"),
            1: lambda c: c.execute("ALTER TABLE Hunger ADD COLUMN note TEXT;"),
        })
        Session(info["db_path"], info["save_id"], llm=object(), time_llm=object())
        cols = [r[1] for r in _rows(info["db_path"], "PRAGMA table_info(Hunger);")]
        assert cols == ["save_id", "turn_id", "v", "note"]
        assert _rows(info["db_path"], "SELECT mod_id, schema_version FROM Mod_Schema_Versions;") == [("x.hunger", 2)]
    finally:
        ctx.cleanup()
    assert not [m for m in get_registered_mod_migrations() if m.mod_id == "x.hunger"]


# ---------------------------------------------------------------------------
# Epochs: check + write atomic with respect to a rewind (R2-m-6)
# ---------------------------------------------------------------------------

def test_guarded_write_holds_off_the_epoch_bump():
    from axiom.epoch import SessionEpochManager

    mgr = SessionEpochManager()
    captured = mgr.current
    inside, release, bumped = threading.Event(), threading.Event(), threading.Event()
    seen_valid: list[bool] = []

    def job() -> None:
        with mgr.guarded_write(captured) as valid:
            seen_valid.append(valid)
            inside.set()
            release.wait(5)            # the job is writing...

    t = threading.Thread(target=job)
    t.start()
    assert inside.wait(5)
    b = threading.Thread(target=lambda: (mgr.bump(), bumped.set()))
    b.start()
    assert not bumped.wait(0.3)        # a rewind cannot slip between check and write
    release.set()
    t.join(5)
    b.join(5)
    assert bumped.is_set() and seen_valid == [True]
    with mgr.guarded_write(captured) as valid:
        assert valid is False          # after the rewind, the stale job writes nothing


# ---------------------------------------------------------------------------
# 0d — an aborted turn leaves no item definition behind
# ---------------------------------------------------------------------------

def test_aborted_turn_creates_no_item_definition(tmp_path: Path):
    from axiom.db_helpers import create_new_save
    from axiom.kernel import KernelRegistry, bootstrap_all_mods
    from tests.test_turn_pipeline_b2 import _ScriptLLM, _write_probe_mod

    extra = tmp_path / "mods"
    _write_probe_mod(
        extra, "probe.abort",
        """
        from axiom.backends.base import GenerationCancelled

        def init(ctx):
            def stop(turn_ctx):
                raise GenerationCancelled("stopped by the player")
            ctx.register_hook("axiom.step:after_step", stop)
        """,
        'hooks = ["axiom.step:after_step"]',
    )
    registry = bootstrap_all_mods(KernelRegistry(), AppConfig(), extra_dirs=[extra])
    db = str(tmp_path / "world.db")
    create_universe_db(db)
    save_id = create_new_save(db, player_name="Hero", difficulty="Normal")
    with get_connection(db) as conn:
        conn.execute(
            "INSERT INTO Entities (entity_id, entity_type, entity_role, name, is_active) "
            "VALUES ('hero', 'player', 'player', 'Hero', 1);"
        )
    llm = _ScriptLLM(LLMResponse("x", {"elapsed_minutes": 1}, "stop"))
    sess = Session(db, save_id, llm=llm, time_llm=llm, kernel_registry=registry)
    llm.queue(LLMResponse("You find an orb.", {"elapsed_minutes": 1, "inventory_changes": [
        {"action": "add", "item_id": "mystery_orb", "name": "Mystery Orb", "quantity": 1,
         "entity_id": "hero"}]}, "stop"))

    with pytest.raises(GenerationCancelled):
        sess.take_turn("I search the room.", player_id="hero")

    assert _rows(db, "SELECT item_id FROM Item_Definitions WHERE item_id = 'mystery_orb';") == []
    assert _rows(db, "SELECT item_id FROM Item_Instances WHERE item_id = 'mystery_orb';") == []
    assert sess.turn_id == 0


# ---------------------------------------------------------------------------
# TICKET-100 — external stores rewound only after the SQL commit
# ---------------------------------------------------------------------------

def test_external_store_untouched_when_the_sql_rewind_fails(tmp_path: Path, monkeypatch):
    import axiom.storage_registry as sr
    from axiom.checkpoint import CheckpointManager

    db = str(tmp_path / "u.db")
    create_universe_db(db)
    with get_connection(db) as conn:
        conn.execute(
            "INSERT INTO Saves (save_id, player_name, difficulty, last_updated) VALUES ('S','P','Normal','x');"
        )
    calls: list[int] = []
    spec = sr.register_custom_storage("probe_vectors", rewind_callback=lambda c, s, t: calls.append(t))
    try:
        def broken(conn, save_id, target, *, external=True):
            raise sqlite3.OperationalError("disk I/O error (test)")
        monkeypatch.setattr(sr, "execute_rewind", broken)
        with pytest.raises(sqlite3.OperationalError):
            CheckpointManager(db).rewind("S", 0, backup=False)
        assert calls == []                      # nothing rolled back outside the db

        monkeypatch.undo()
        CheckpointManager(db).rewind("S", 0, backup=False)
        assert calls == [0]                     # after a committed SQL rewind: yes
    finally:
        sr.unregister_storage(spec)
