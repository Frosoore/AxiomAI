"""tests/test_factextract.py

LLM fact extraction with a mocked backend — deterministic, no network.
Covers payload shapes, coercion, caps, and graceful failure.
"""

import json

from axiom.backends.base import LLMResponse
from axiom.factextract import extract_facts


class _FakeLLM:
    """Minimal LLMBackend stand-in: returns a canned response or raises."""

    def __init__(self, *, tool_call=None, narrative_text="", raise_exc=None):
        self._tool_call = tool_call
        self._narrative = narrative_text
        self._raise = raise_exc
        self.last_messages = None

    def complete(self, messages, **kwargs):
        self.last_messages = messages
        if self._raise is not None:
            raise self._raise
        return LLMResponse(
            narrative_text=self._narrative,
            tool_call=self._tool_call,
            finish_reason="stop",
        )


_ONE = {
    "type": "experience", "who": "Kael", "what": "swore an oath", "when": "dusk",
    "where": "the throne room", "why": "loyalty", "entities": ["Kael", "Queen"],
    "statement": "Kael swore an oath of loyalty to the Queen.",
}


def test_empty_input_returns_empty():
    llm = _FakeLLM(tool_call={"facts": [_ONE]})
    assert extract_facts(llm, "   ") == []
    assert llm.last_messages is None  # never called the LLM


def test_parses_tool_call_facts_object():
    llm = _FakeLLM(tool_call={"facts": [_ONE]})
    facts = extract_facts(llm, "Kael knelt and spoke.")
    assert len(facts) == 1
    f = facts[0]
    assert f.statement == "Kael swore an oath of loyalty to the Queen."
    assert f.fact_type == "experience"
    assert f.entities == ["Kael", "Queen"]
    assert f.where == "the throne room"


def test_parses_bare_list_tool_call():
    llm = _FakeLLM(tool_call=[_ONE])
    assert len(extract_facts(llm, "x")) == 1


def test_parses_json_from_narrative_text():
    llm = _FakeLLM(narrative_text=json.dumps({"facts": [_ONE]}))
    assert len(extract_facts(llm, "x")) == 1


def test_llm_failure_is_graceful():
    llm = _FakeLLM(raise_exc=RuntimeError("backend down"))
    assert extract_facts(llm, "something happened") == []


def test_blank_statements_skipped():
    items = [{"statement": "  "}, _ONE]
    facts = extract_facts(_FakeLLM(tool_call={"facts": items}), "x")
    assert len(facts) == 1


def test_unknown_type_defaults_world():
    item = dict(_ONE, type="nonsense")
    facts = extract_facts(_FakeLLM(tool_call={"facts": [item]}), "x")
    assert facts[0].fact_type == "world"


def test_max_facts_cap():
    items = [dict(_ONE, statement=f"fact {i}") for i in range(20)]
    facts = extract_facts(_FakeLLM(tool_call={"facts": items}), "x", max_facts=3)
    assert len(facts) == 3


def test_non_list_entities_tolerated():
    item = dict(_ONE, entities="not a list")
    facts = extract_facts(_FakeLLM(tool_call={"facts": [item]}), "x")
    assert facts[0].entities == []


def test_garbage_payload_returns_empty():
    llm = _FakeLLM(narrative_text="I could not find any facts, sorry!")
    assert extract_facts(llm, "x") == []


def test_known_entities_and_when_hint_in_prompt():
    llm = _FakeLLM(tool_call={"facts": []})
    extract_facts(llm, "passage", known_entities=["Mira"], when_hint="dawn")
    user_msg = llm.last_messages[-1]["content"]
    assert "Mira" in user_msg
    assert "dawn" in user_msg
