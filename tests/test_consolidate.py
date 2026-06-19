"""tests/test_consolidate.py

LLM belief consolidation with a mocked backend, plus the deterministic
application of CREATE/UPDATE/DELETE actions to the store. No network.
"""

import tempfile
from pathlib import Path

import pytest

from axiom.backends.base import LLMResponse
from axiom.consolidate import ConsolidationAction, _scope_existing, consolidate
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


# ----------------------------------------------------------- _scope_existing (077)

def _obs(oid: int, subject: str) -> Observation:
    return Observation(statement=f"belief {oid}", subject=subject, observation_id=oid)


def test_scope_existing_noop_within_budget():
    existing = [_obs(i, "X") for i in range(3)]
    assert _scope_existing([], existing, max_existing=24) is existing


def test_scope_existing_disabled_when_zero():
    existing = [_obs(i, "X") for i in range(50)]
    assert _scope_existing([], existing, max_existing=0) is existing


def test_scope_existing_prefers_batch_subjects_then_recent():
    # 30 beliefs (recent-first order), only #25 is about "Mira" (the batch subject).
    existing = [_obs(i, "Mira" if i == 25 else "Other") for i in range(30)]
    facts = [Fact(statement="Mira returns", who="Mira", entities=["Mira"], fact_id=1, turn_id=2)]
    scoped = _scope_existing(facts, existing, max_existing=5)
    assert len(scoped) == 5
    assert scoped[0].observation_id == 25  # the Mira belief is rescued first
    # remainder filled with the most recent (input order), no duplicate of #25.
    assert [o.observation_id for o in scoped[1:]] == [0, 1, 2, 3]


def test_consolidate_only_shows_scoped_beliefs(db_path: str):
    captured = {}

    class _CapturingLLM:
        calls = 0

        def complete(self, messages, **kwargs):
            type(self).calls += 1
            captured["user"] = messages[-1]["content"]
            return LLMResponse(narrative_text="", tool_call={"actions": []}, finish_reason="stop")

    existing = [_obs(i, "Other") for i in range(30)] + [_obs(99, "Mira")]
    facts = [_fact(1, 2, "Mira returns")]
    facts[0].entities = ["Mira"]
    consolidate(_CapturingLLM(), facts, existing, max_existing=5)
    prompt = captured["user"]
    assert "[belief 99]" in prompt          # the on-subject belief is shown
    assert prompt.count("[belief ") == 5    # bounded to max_existing


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
