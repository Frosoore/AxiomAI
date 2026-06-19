"""tests/test_fact_worker.py

App-layer fact extraction (Phase 2 item 4): the background worker and the
settings-dialog memory controls. Deterministic — the LLM is mocked, no network.
"""

from __future__ import annotations

from axiom.backends.base import LLMResponse
from axiom.facts import get_facts
from axiom.schema import create_universe_db, get_connection
from workers.fact_worker import FactExtractWorker


_FACT = {
    "type": "world", "who": "Kael", "what": "burned the bridge", "when": "dawn",
    "where": "Voss", "why": "to stop the army", "entities": ["Kael", "Voss"],
    "statement": "Kael burned the bridge at Voss to stop the army.",
}


class _FakeLLM:
    """Returns a canned fact payload, or raises to simulate a dead backend."""

    def __init__(self, *, tool_call=None, raise_exc=None):
        self._tool_call = tool_call
        self._raise = raise_exc
        self.calls = 0

    def complete(self, messages, **kwargs):
        self.calls += 1
        if self._raise is not None:
            raise self._raise
        return LLMResponse(narrative_text="", tool_call=self._tool_call, finish_reason="stop")


def _make_save(tmp_path) -> tuple[str, str]:
    db_path = str(tmp_path / "universe.db")
    create_universe_db(db_path)
    save_id = "save-1"
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO Saves (save_id, player_name, difficulty, last_updated) "
            "VALUES (?, ?, ?, ?);",
            (save_id, "Hero", "Normal", "2026-06-18"),
        )
        conn.commit()
    return db_path, save_id


def test_worker_extracts_and_persists(qtbot, tmp_path) -> None:
    db_path, save_id = _make_save(tmp_path)
    llm = _FakeLLM(tool_call={"facts": [_FACT]})
    worker = FactExtractWorker(
        llm, db_path, save_id, turn_id=3,
        narrative_text="Kael set the bridge alight.",
        known_entities=["Kael"], when_hint="dawn",
    )

    results: list[int] = []
    worker.facts_extracted.connect(results.append)
    worker.run()  # run synchronously on this thread (no event loop needed)

    assert results == [1]
    stored = get_facts(db_path, save_id)
    assert len(stored) == 1
    assert stored[0].statement == _FACT["statement"]
    assert stored[0].turn_id == 3


def test_worker_no_facts_emits_zero(qtbot, tmp_path) -> None:
    db_path, save_id = _make_save(tmp_path)
    llm = _FakeLLM(tool_call={"facts": []})
    worker = FactExtractWorker(llm, db_path, save_id, 1, "Nothing of note happened.")
    results: list[int] = []
    worker.facts_extracted.connect(results.append)
    worker.run()
    assert results == [0]
    assert get_facts(db_path, save_id) == []


def test_worker_consolidates_beliefs_when_enabled(qtbot, tmp_path) -> None:
    """With consolidate_beliefs=True, the worker also distils a belief.

    One canned payload satisfies both LLM calls: extract_facts reads "facts",
    consolidate reads "actions". The fact gets id 1 on a fresh DB, which the
    create action cites as its source.
    """
    from axiom.observations import get_observations
    db_path, save_id = _make_save(tmp_path)
    payload = {
        "facts": [_FACT],
        "actions": [{"action": "create", "subject": "Voss",
                     "statement": "Kael is an enemy of Voss", "source_fact_ids": [1]}],
    }
    llm = _FakeLLM(tool_call=payload)
    worker = FactExtractWorker(
        llm, db_path, save_id, turn_id=3,
        narrative_text="Kael set the bridge alight.",
        consolidate_beliefs=True,
    )
    worker.run()

    assert len(get_facts(db_path, save_id)) == 1
    beliefs = get_observations(db_path, save_id)
    assert len(beliefs) == 1
    assert beliefs[0].statement == "Kael is an enemy of Voss"
    assert beliefs[0].sources[0]["turn_id"] == 3


def test_worker_beliefs_off_creates_no_observation(qtbot, tmp_path) -> None:
    from axiom.observations import count_observations
    db_path, save_id = _make_save(tmp_path)
    llm = _FakeLLM(tool_call={"facts": [_FACT], "actions": [
        {"action": "create", "statement": "x", "source_fact_ids": [1]}]})
    worker = FactExtractWorker(llm, db_path, save_id, 3, "Kael set the bridge alight.",
                               consolidate_beliefs=False)
    worker.run()
    assert count_observations(db_path, save_id) == 0  # consolidation never ran


def _seed_beliefs(db_path: str, save_id: str, subject: str, n: int) -> None:
    from axiom.observations import Observation, insert_observation
    for i in range(n):
        insert_observation(db_path, save_id, Observation(
            statement=f"{subject} fact {i}", subject=subject,
            sources=[{"fact_id": 100 + i, "turn_id": 1}],
            created_turn_id=1, updated_turn_id=1))


def test_worker_refreshes_mental_model_when_enabled(qtbot, tmp_path) -> None:
    """With refresh_mental_models=True, a changed subject with enough beliefs
    gets a profile written from the LLM's prose.

    The canned payload serves all three calls: extract/consolidate read the
    tool_call dict, reflect reads narrative_text. Voss is pre-seeded with enough
    beliefs to clear the MIN_BELIEFS_FOR_MODEL threshold.
    """
    from axiom.mental_models import get_mental_models
    db_path, save_id = _make_save(tmp_path)
    _seed_beliefs(db_path, save_id, "Voss", 3)
    payload = {
        "facts": [_FACT],
        "actions": [{"action": "create", "subject": "Voss",
                     "statement": "Kael is an enemy of Voss", "source_fact_ids": [1]}],
    }
    llm = _FakeLLM(tool_call=payload)
    llm._text = "Voss is a town scarred by Kael's sabotage."  # reflect reads this

    # _FakeLLM.complete ignores narrative_text; give it one for the reflect call.
    def complete(messages, **kwargs):
        llm.calls += 1
        return LLMResponse(narrative_text=llm._text, tool_call=payload, finish_reason="stop")
    llm.complete = complete

    worker = FactExtractWorker(
        llm, db_path, save_id, turn_id=3,
        narrative_text="Kael set the bridge alight.",
        consolidate_beliefs=True, refresh_mental_models=True,
    )
    worker.run()

    models = get_mental_models(db_path, save_id, subject="Voss")
    assert len(models) == 1
    assert models[0].summary == "Voss is a town scarred by Kael's sabotage."
    assert models[0].updated_turn_id == 3


def test_worker_no_model_when_refresh_off(qtbot, tmp_path) -> None:
    from axiom.mental_models import count_mental_models
    db_path, save_id = _make_save(tmp_path)
    _seed_beliefs(db_path, save_id, "Voss", 3)
    payload = {
        "facts": [_FACT],
        "actions": [{"action": "create", "subject": "Voss",
                     "statement": "Kael is an enemy of Voss", "source_fact_ids": [1]}],
    }
    llm = _FakeLLM(tool_call=payload)
    worker = FactExtractWorker(
        llm, db_path, save_id, turn_id=3,
        narrative_text="Kael set the bridge alight.",
        consolidate_beliefs=True, refresh_mental_models=False,
    )
    worker.run()
    assert count_mental_models(db_path, save_id) == 0


def test_worker_dead_backend_is_graceful(qtbot, tmp_path) -> None:
    db_path, save_id = _make_save(tmp_path)
    llm = _FakeLLM(raise_exc=RuntimeError("provider down"))
    worker = FactExtractWorker(llm, db_path, save_id, 1, "A dragon appeared.")
    results: list[int] = []
    errors: list[str] = []
    worker.facts_extracted.connect(results.append)
    worker.error_occurred.connect(errors.append)
    worker.run()
    # extract_facts swallows backend errors → 0 facts, no error signal, no rows.
    assert results == [0]
    assert errors == []
    assert get_facts(db_path, save_id) == []
