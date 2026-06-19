"""tests/test_missions.py

Per-character belief missions (Phase 4, B-3): storage read from Universe_Meta,
text round-trip, and the consolidator's per-character "memory styles" section.
"""

import tempfile
from pathlib import Path

import pytest

from axiom import missions
from axiom.backends.base import LLMResponse
from axiom.consolidate import consolidate
from axiom.facts import Fact
from axiom.schema import create_universe_db, get_connection


@pytest.fixture
def db_path() -> str:
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "universe.db")
        create_universe_db(path)
        yield path


def _set_meta(db_path: str, key: str, value: str) -> None:
    with get_connection(db_path) as conn:
        conn.execute("INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES (?, ?);",
                     (key, value))
        conn.commit()


class _CapturingLLM:
    """Records the messages it was asked to complete."""
    def __init__(self, tool_call):
        self._tool_call = tool_call
        self.last_messages = None

    def complete(self, messages, **kwargs):
        self.last_messages = messages
        return LLMResponse(narrative_text="", tool_call=self._tool_call, finish_reason="stop")


# ------------------------------------------------------------------ storage

def test_missing_keys_default_empty(db_path: str) -> None:
    assert missions.get_universe_mission(db_path) == ""
    assert missions.get_belief_missions(db_path) == {}


def test_reads_universe_and_per_character(db_path: str) -> None:
    _set_meta(db_path, "belief_mission", "Remember what shapes this grim world.")
    _set_meta(db_path, "belief_missions",
              '{"Merchant": "remembers slights and debts", "Captain": "remembers oaths"}')
    assert missions.get_universe_mission(db_path) == "Remember what shapes this grim world."
    m = missions.get_belief_missions(db_path)
    assert m["Merchant"] == "remembers slights and debts"
    assert m["Captain"] == "remembers oaths"


def test_malformed_json_degrades(db_path: str) -> None:
    _set_meta(db_path, "belief_missions", "{not json")
    assert missions.get_belief_missions(db_path) == {}


def test_text_roundtrip() -> None:
    text = "Merchant: remembers debts\nCaptain: remembers oaths: sworn ones"
    parsed = missions.parse_missions_text(text)
    assert parsed["Merchant"] == "remembers debts"
    # First colon splits — the mission keeps its own colon.
    assert parsed["Captain"] == "remembers oaths: sworn ones"
    assert "Merchant: remembers debts" in missions.missions_to_text(parsed)


def test_parse_skips_bad_lines() -> None:
    assert missions.parse_missions_text("no colon here\n: empty name\nName:  ") == {}


# -------------------------------------------------------------- consolidate use

def test_consolidate_injects_matching_character_style() -> None:
    llm = _CapturingLLM(tool_call={"actions": []})
    fact = Fact(statement="The player shortchanged the merchant", fact_id=1, turn_id=3,
                who="Merchant", entities=["Merchant"])
    consolidate(llm, [fact], existing=[],
                missions={"Merchant": "remembers slights and debts",
                          "Dragon": "remembers nothing useful"})
    user_msg = llm.last_messages[1]["content"]
    assert "Character memory styles" in user_msg
    assert "Merchant: remembers slights and debts" in user_msg
    # The Dragon is not in this batch → its style is not shown.
    assert "Dragon" not in user_msg


def test_consolidate_no_styles_when_none_match() -> None:
    llm = _CapturingLLM(tool_call={"actions": []})
    fact = Fact(statement="A storm rolled in", fact_id=1, turn_id=2)
    consolidate(llm, [fact], existing=[], missions={"Merchant": "remembers debts"})
    assert "Character memory styles" not in llm.last_messages[1]["content"]
