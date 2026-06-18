"""tests/test_consolidate.py

LLM belief consolidation with a mocked backend, plus the deterministic
application of CREATE/UPDATE/DELETE actions to the store. No network.
"""

import tempfile
from pathlib import Path

import pytest

from axiom.backends.base import LLMResponse
from axiom.consolidate import ConsolidationAction, consolidate
from axiom.facts import Fact
from axiom import observations
from axiom.observations import Observation, apply_consolidation
from axiom.schema import create_universe_db, get_connection


class _FakeLLM:
    def __init__(self, *, tool_call=None, raise_exc=None):
        self._tool_call = tool_call
        self._raise = raise_exc
        self.calls = 0

    def complete(self, messages, **kwargs):
        self.calls += 1
        if self._raise is not None:
            raise self._raise
        return LLMResponse(narrative_text="", tool_call=self._tool_call, finish_reason="stop")


def _fact(fid: int, turn: int, statement: str) -> Fact:
    return Fact(statement=statement, fact_id=fid, turn_id=turn)


@pytest.fixture
def db_path() -> str:
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "universe.db")
        create_universe_db(path)
        with get_connection(path) as conn:
            conn.execute(
                "INSERT INTO Saves (save_id, player_name, difficulty, last_updated) "
                "VALUES (?, ?, ?, ?);", ("s1", "Hero", "Normal", "2026-06-18"))
            conn.commit()
        yield path


# ---------------------------------------------------------------- consolidate()

def test_empty_facts_returns_empty():
    llm = _FakeLLM(tool_call={"actions": [{"action": "create", "statement": "x",
                                           "source_fact_ids": [1]}]})
    assert consolidate(llm, [], []) == []
    assert llm.calls == 0  # never called the LLM with nothing to consolidate


def test_parses_create_action():
    llm = _FakeLLM(tool_call={"actions": [
        {"action": "create", "subject": "Merchant",
         "statement": "The merchant distrusts the player", "source_fact_ids": [1]},
    ]})
    actions = consolidate(llm, [_fact(1, 3, "The player insulted the merchant")], [])
    assert len(actions) == 1
    assert actions[0].kind == "create"
    assert actions[0].subject == "Merchant"
    assert actions[0].source_fact_ids == [1]


def test_drops_hallucinated_fact_ids_and_unknown_beliefs():
    # Fact 99 was never shown; belief 5 does not exist → both actions dropped.
    llm = _FakeLLM(tool_call={"actions": [
        {"action": "create", "statement": "bogus", "source_fact_ids": [99]},
        {"action": "update", "observation_id": 5, "statement": "y", "source_fact_ids": [1]},
    ]})
    actions = consolidate(llm, [_fact(1, 2, "real fact")], existing=[])
    assert actions == []


def test_graceful_on_backend_failure():
    llm = _FakeLLM(raise_exc=RuntimeError("down"))
    assert consolidate(llm, [_fact(1, 1, "f")], []) == []


# ---------------------------------------------------------- apply_consolidation()

def test_apply_create(db_path: str):
    actions = [ConsolidationAction(kind="create", subject="Merchant",
                                   statement="Merchant distrusts player", source_fact_ids=[1])]
    res = apply_consolidation(db_path, "s1", turn_id=3, actions=actions,
                              fact_turn_map={1: 3})
    assert res["created"] == 1
    got = observations.get_observations(db_path, "s1")
    assert len(got) == 1 and got[0].proof_count == 1
    assert got[0].created_turn_id == 3 and got[0].sources[0]["turn_id"] == 3


def test_apply_update_merges_sources(db_path: str):
    oid = observations.insert_observation(db_path, "s1", Observation(
        statement="Merchant wary of player", subject="Merchant",
        sources=[{"fact_id": 1, "turn_id": 3}], created_turn_id=3, updated_turn_id=3))
    actions = [ConsolidationAction(kind="update", observation_id=oid,
                                   statement="Merchant openly hostile", source_fact_ids=[2])]
    res = apply_consolidation(db_path, "s1", turn_id=7, actions=actions,
                              fact_turn_map={2: 7})
    assert res["updated"] == 1
    o = observations.get_observations(db_path, "s1")[0]
    assert o.statement == "Merchant openly hostile"
    assert {s["turn_id"] for s in o.sources} == {3, 7}  # merged, not replaced
    assert o.proof_count == 2 and o.updated_turn_id == 7


def test_apply_delete(db_path: str):
    oid = observations.insert_observation(db_path, "s1", Observation(
        statement="The bridge stands", sources=[{"fact_id": 1, "turn_id": 2}],
        created_turn_id=2, updated_turn_id=2))
    res = apply_consolidation(db_path, "s1", turn_id=9,
                              actions=[ConsolidationAction(kind="delete", observation_id=oid)],
                              fact_turn_map={})
    assert res["deleted"] == 1
    assert observations.count_observations(db_path, "s1") == 0


def test_apply_then_rollback_acceptance(db_path: str):
    """End-to-end: a belief updated at turn 7, rewind to 5 drops the turn-7 source."""
    oid = observations.insert_observation(db_path, "s1", Observation(
        statement="Merchant wary", subject="Merchant",
        sources=[{"fact_id": 1, "turn_id": 3}], created_turn_id=3, updated_turn_id=3))
    apply_consolidation(db_path, "s1", turn_id=7,
                        actions=[ConsolidationAction(kind="update", observation_id=oid,
                                                     statement="Merchant hostile",
                                                     source_fact_ids=[2])],
                        fact_turn_map={2: 7})
    observations.rollback_observations_standalone(db_path, "s1", target_turn_id=5)
    o = observations.get_observations(db_path, "s1")[0]
    assert {s["turn_id"] for s in o.sources} == {3}   # turn-7 reinforcement undone
    assert o.proof_count == 1 and o.stale is True
