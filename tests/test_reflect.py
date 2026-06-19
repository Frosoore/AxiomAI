"""tests/test_reflect.py

LLM mental-model generation (§7.8) with a mocked backend, plus the deterministic
helper that picks which subjects a consolidation batch touched. No network.
"""

from axiom.backends.base import LLMResponse
from axiom.consolidate import ConsolidationAction
from axiom.observations import Observation
from axiom.reflect import MIN_BELIEFS_FOR_MODEL, affected_subjects, reflect


class _FakeLLM:
    def __init__(self, *, text="", raise_exc=None):
        self._text = text
        self._raise = raise_exc
        self.calls = 0

    def complete(self, messages, **kwargs):
        self.calls += 1
        if self._raise is not None:
            raise self._raise
        return LLMResponse(narrative_text=self._text, tool_call=None, finish_reason="stop")


def _belief(statement: str, subject: str = "Merchant") -> Observation:
    return Observation(statement=statement, subject=subject)


def _beliefs(n: int) -> list[Observation]:
    return [_belief(f"belief {i}") for i in range(n)]


# ------------------------------------------------------------- affected_subjects

def test_affected_subjects_dedups_create_update_only():
    actions = [
        ConsolidationAction(kind="create", subject="Merchant"),
        ConsolidationAction(kind="update", subject="merchant", observation_id=1),
        ConsolidationAction(kind="create", subject="Guard"),
        ConsolidationAction(kind="delete", subject="Thief", observation_id=2),
        ConsolidationAction(kind="create", subject=""),  # world model
    ]
    # First-seen spelling kept, case-insensitive dedup, delete excluded.
    assert affected_subjects(actions) == ["Merchant", "Guard", ""]


def test_affected_subjects_empty():
    assert affected_subjects([]) == []
    assert affected_subjects(None) == []


# --------------------------------------------------------------------- reflect()

def test_reflect_returns_trimmed_summary():
    llm = _FakeLLM(text="  Merchant is now openly hostile to the player.  ")
    out = reflect(llm, "Merchant", _beliefs(MIN_BELIEFS_FOR_MODEL))
    assert out == "Merchant is now openly hostile to the player."
    assert llm.calls == 1


def test_reflect_skips_when_too_few_beliefs():
    llm = _FakeLLM(text="should not be called")
    out = reflect(llm, "Merchant", _beliefs(MIN_BELIEFS_FOR_MODEL - 1))
    assert out == ""
    assert llm.calls == 0  # never even hits the backend


def test_reflect_ignores_blank_beliefs_for_the_threshold():
    beliefs = _beliefs(MIN_BELIEFS_FOR_MODEL - 1) + [_belief("   ")]
    llm = _FakeLLM(text="x")
    assert reflect(llm, "Merchant", beliefs) == ""
    assert llm.calls == 0


def test_reflect_graceful_on_backend_failure():
    llm = _FakeLLM(raise_exc=RuntimeError("backend down"))
    assert reflect(llm, "Merchant", _beliefs(MIN_BELIEFS_FOR_MODEL)) == ""


def test_reflect_empty_answer_returns_empty():
    llm = _FakeLLM(text="   ")
    assert reflect(llm, "Merchant", _beliefs(MIN_BELIEFS_FOR_MODEL)) == ""
