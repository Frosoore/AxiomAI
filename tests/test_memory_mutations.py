"""Engine CRUD for player-facing memory corrections (facts / beliefs / models)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from axiom.schema import create_universe_db, get_connection
from mods.axiom.living_memory.facts import Fact, delete_fact, get_fact, insert_facts, update_fact
from mods.axiom.living_memory.mental_models import (
    delete_mental_model,
    get_mental_model,
    update_mental_model,
    upsert_mental_model,
)
from mods.axiom.living_memory.observations import (
    Observation,
    delete_observation,
    get_observation,
    insert_observation,
    update_observation,
)


@pytest.fixture
def db_path() -> str:
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "save.db")
        create_universe_db(path)
        with get_connection(path) as conn:
            conn.execute(
                "INSERT INTO Saves (save_id, player_name, difficulty, last_updated) "
                "VALUES (?, ?, ?, ?);",
                ("s1", "Hero", "Normal", "2026-08-03"),
            )
            conn.execute(
                "INSERT INTO Saves (save_id, player_name, difficulty, last_updated) "
                "VALUES (?, ?, ?, ?);",
                ("s2", "Other", "Normal", "2026-08-03"),
            )
            conn.commit()
        yield path


def test_fact_update_delete_and_save_scoping(db_path: str) -> None:
    ids = insert_facts(
        db_path,
        "s1",
        3,
        [Fact(statement="Kael swore an oath", fact_type="experience", entities=["Kael"])],
    )
    assert len(ids) == 1
    fid = ids[0]

    assert update_fact(db_path, "s1", fid, statement="Kael broke the oath") is True
    f = get_fact(db_path, "s1", fid)
    assert f is not None
    assert f.statement == "Kael broke the oath"

    assert update_fact(db_path, "s1", fid, statement="   ") is False
    assert update_fact(db_path, "s2", fid, statement="stolen") is False
    assert get_fact(db_path, "s1", fid).statement == "Kael broke the oath"

    assert delete_fact(db_path, "s2", fid) is False
    assert delete_fact(db_path, "s1", fid) is True
    assert get_fact(db_path, "s1", fid) is None


def test_observation_update_delete(db_path: str) -> None:
    oid = insert_observation(
        db_path,
        "s1",
        Observation(
            statement="The smith holds a debt",
            subject="Smith",
            sources=[{"fact_id": 1, "turn_id": 2}],
            created_turn_id=2,
            updated_turn_id=2,
        ),
    )
    assert oid is not None
    assert update_observation(db_path, "s1", oid, statement="The smith is free") is True
    o = get_observation(db_path, "s1", oid)
    assert o is not None
    assert o.statement == "The smith is free"
    assert o.subject == "Smith"

    assert delete_observation(db_path, "s1", oid) is True
    assert get_observation(db_path, "s1", oid) is None


def test_mental_model_update_delete(db_path: str) -> None:
    mid = upsert_mental_model(
        db_path, "s1", "Kael", "Loyal and stubborn.", turn_id=5, sources=[1]
    )
    assert mid is not None
    assert update_mental_model(db_path, "s1", mid, summary="Cautious after betrayal.") is True
    m = get_mental_model(db_path, "s1", mid)
    assert m is not None
    assert "Cautious" in m.summary
    assert m.stale is False

    assert update_mental_model(db_path, "s1", mid, summary="") is False
    assert delete_mental_model(db_path, "s1", mid) is True
    assert get_mental_model(db_path, "s1", mid) is None
