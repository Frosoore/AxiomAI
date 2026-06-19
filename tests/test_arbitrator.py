"""
tests/test_arbitrator.py

Unit tests for core/arbitrator.py.

The LLM backend is fully mocked.  A real universe db (via tmp_path) is used
so that Event_Log, State_Cache, and VectorMemory interactions are verified
against actual storage.  VectorMemory uses the fake embedding function from
test_vector_memory.py to avoid model downloads.
"""

import hashlib
import json
import math
import random
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from chromadb import EmbeddingFunction, Documents, Embeddings

from axiom.arbitrator import ArbitratorEngine, ArbitratorResult
from axiom.rules import RulesEngine
from axiom.events import EventSourcer
from axiom.modifiers import ModifierProcessor
from axiom.schema import create_universe_db
from axiom.backends.base import LLMBackend, LLMMessage, LLMResponse
from axiom.memory import VectorMemory, _EmbeddingSingleton


# ---------------------------------------------------------------------------
# Shared fake embedding function (same as test_vector_memory.py)
# ---------------------------------------------------------------------------

class _FakeEmbeddingFn(EmbeddingFunction[Documents]):
    def __call__(self, input: Documents) -> Embeddings:  # noqa: A002
        embeddings: Embeddings = []
        for text in input:
            seed = int(hashlib.md5(str(text).encode()).hexdigest(), 16) % (2 ** 32)
            rng = random.Random(seed)
            vec = [rng.gauss(0, 1) for _ in range(32)]
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            embeddings.append([x / norm for x in vec])
        return embeddings


# ---------------------------------------------------------------------------
# Stub LLM backend
# ---------------------------------------------------------------------------

class _StubLLM(LLMBackend):
    """Configurable stub that returns preset LLMResponse objects."""

    def __init__(self, response: LLMResponse) -> None:
        self._response = response
        self.last_messages: list[LLMMessage] = []

    def complete(self, messages: list[LLMMessage], stream: bool = False, **kwargs) -> LLMResponse:
        self.last_messages = list(messages)
        return self._response

    def stream_tokens(self, messages, **kwargs):
        yield self._response.narrative_text

    def is_available(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db_path(tmp_path: Path) -> str:
    """Provision a universe db with one save and two entities."""
    path = str(tmp_path / "universe.db")
    create_universe_db(path)

    with sqlite3.connect(path) as conn:
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("INSERT INTO Stat_Definitions (stat_id, name, value_type) VALUES ('1', 'HP', 'numeric'), ('2', 'Gold', 'numeric'), ('3', 'Title', 'categorical'), ('4', 'Status', 'categorical'), ('5', 'Army_Size', 'numeric'), ('6', 'Wealth', 'numeric')")
        conn.execute("INSERT INTO Saves (save_id, player_name, difficulty, last_updated) VALUES (?,?,?,?);",
                     ("s1", "Hero", "Normal", "2026-01-01T00:00:00"))
        conn.execute("INSERT INTO Entities (entity_id, entity_type, name, is_active) VALUES (?,?,?,?);",
                     ("player1", "player", "Aria", 1))
        conn.execute("INSERT INTO Entities (entity_id, entity_type, name, is_active) VALUES (?,?,?,?);",
                     ("npc1", "npc", "Goblin", 1))
        conn.commit()

    # Seed State_Cache via EventSourcer
    es = EventSourcer(path)
    es.append_event("s1", 0, "entity_create", "player1",
                    {"entity_id": "player1", "entity_type": "player", "name": "Aria"})
    es.append_event("s1", 0, "stat_change", "player1",
                    {"entity_id": "player1", "stat_key": "HP", "delta": 100})
    es.append_event("s1", 0, "stat_change", "player1",
                    {"entity_id": "player1", "stat_key": "Gold", "delta": 50})
    es.append_event("s1", 0, "entity_create", "npc1",
                    {"entity_id": "npc1", "entity_type": "npc", "name": "Goblin"})
    es.append_event("s1", 0, "stat_change", "npc1",
                    {"entity_id": "npc1", "stat_key": "HP", "delta": 30})
    es.rebuild_state_cache("s1")
    return path


class TestLoreBookRetrieval:
    """B1: _fetch_relevant_lore reads Lore_Book directly and ranks by keyword/name.

    Regression guard — this used to always return [] (it filtered on a metadata
    key the vector query never produced, and lore was never embedded), so the
    Lore Book never reached the narrator prompt.
    """

    @staticmethod
    def _seed_lore(db_path: str) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.executemany(
                "INSERT INTO Lore_Book (entry_id, category, name, keywords, content) "
                "VALUES (?,?,?,?,?);",
                [
                    ("e1", "factions", "The Aicamed Federation",
                     "aicamed, federation, mages", "A reclusive order of mages."),
                    ("e2", "places", "The Sunken Library",
                     "library, books, archive", "A drowned hall of forbidden tomes."),
                ],
            )
            conn.commit()

    def test_returns_matching_entry_by_keyword(self, db_path: str) -> None:
        self._seed_lore(db_path)
        arb = ArbitratorEngine(db_path, [])
        res = arb._fetch_relevant_lore("s1", "I seek the mages of the federation.")
        assert [e["name"] for e in res] == ["The Aicamed Federation"]
        assert res[0]["category"] == "factions"
        assert "reclusive" in res[0]["content"]

    def test_no_match_returns_empty(self, db_path: str) -> None:
        self._seed_lore(db_path)
        arb = ArbitratorEngine(db_path, [])
        assert arb._fetch_relevant_lore("s1", "I walk down the road.") == []

    def test_stopwords_alone_do_not_match(self, db_path: str) -> None:
        # "The" leads both entry names but is a stopword → no spurious matches.
        self._seed_lore(db_path)
        arb = ArbitratorEngine(db_path, [])
        assert arb._fetch_relevant_lore("s1", "the the the") == []

    def test_empty_lore_book_returns_empty(self, db_path: str) -> None:
        arb = ArbitratorEngine(db_path, [])
        assert arb._fetch_relevant_lore("s1", "mages and federation") == []


class TestEffectiveStatsFreshness:
    """B2: effective stats are re-read every turn (no stale per-turn cache).

    The old `_stats_cache` froze the base+modifier overlay at the end of a turn,
    so a modifier added/expired afterwards was not reflected until a
    chronicler/rewind invalidation. We now always re-read State_Cache +
    Active_Modifiers.
    """

    def test_modifier_added_after_turn_is_reflected(self, db_path: str, vm) -> None:
        arb, _llm = _make_arbitrator(
            db_path, vm, LLMResponse("ok", {"state_changes": []}, "stop")
        )
        arb.process_turn("s1", 1, {"player1": "I wait."}, "sys", [])

        # A modifier applied AFTER the turn must show up on the next stats fetch,
        # not be masked by a stale snapshot cached during the turn.
        ModifierProcessor(db_path).add_modifier("s1", "player1", "HP", 50, minutes=60)
        eff = arb._fetch_effective_stats("s1")
        assert eff["player1"]["HP"] == "150"  # base 100 + modifier 50


@pytest.fixture
def vm(tmp_path: Path):
    # Injecte le faux embedder dans le singleton : la connexion réelle (chargement
    # de torch) est paresseuse et n'aurait pas été couverte par un patch autour du
    # seul constructeur. Tests déterministes et sans dépendance native torch.
    saved = _EmbeddingSingleton._instance
    _EmbeddingSingleton._instance = _FakeEmbeddingFn()
    try:
        yield VectorMemory(persist_dir=str(tmp_path / "chroma"))
    finally:
        _EmbeddingSingleton._instance = saved


def _make_arbitrator(
    db_path: str,
    vm: VectorMemory,
    llm_response: LLMResponse,
    rules: list[dict] | None = None,
) -> tuple[ArbitratorEngine, _StubLLM]:
    llm = _StubLLM(llm_response)
    arb = ArbitratorEngine(db_path, rules or [])
    # Give the Timekeeper its own backend so its second LLM call does not clobber
    # assertions made against the main narrative stub (e.g. last_messages). This
    # also mirrors the real architecture, where the time model is a separate
    # backend from the narration model (Pilier 5 / TICKET-016).
    time_llm = _StubLLM(LLMResponse('{"elapsed_minutes": 5}', None, "stop"))
    arb.configure(llm, vm, time_llm=time_llm)
    return arb, llm

# ---------------------------------------------------------------------------
# ArbitratorResult dataclass
# ---------------------------------------------------------------------------

class TestArbitratorResult:
    def test_fields_accessible(self) -> None:
        """ArbitratorResult exposes narrative_text and applied_changes."""
        r = ArbitratorResult(
            narrative_text="prose",
            applied_changes=[{"x": 1}],
            rejected_changes=[],
            triggered_rules=[],
        )
        assert r.narrative_text == "prose"
        assert r.applied_changes == [{"x": 1}]

    def test_defaults_are_empty_lists(self) -> None:
        """Omitted change lists default to empty lists, not None."""
        r = ArbitratorResult(narrative_text="hello")
        assert r.applied_changes == []
        assert r.rejected_changes == []
        assert r.triggered_rules == []


# ---------------------------------------------------------------------------
# process_turn — valid state change
# ---------------------------------------------------------------------------

class TestProcessTurnValidChange:
    def test_valid_change_appears_in_applied_changes(self, db_path, vm) -> None:
        """A valid LLM-proposed stat change is accepted and listed in
        applied_changes."""
        response = LLMResponse(
            narrative_text="The goblin hits you.",
            tool_call={"state_changes": [
                {"entity_id": "player1", "stat_key": "HP", "delta": -10}
            ]},
            finish_reason="stop",
        )
        arb, _ = _make_arbitrator(db_path, vm, response)
        result = arb.process_turn("s1", 1, {"player": "I attack"}, "Universe prompt", [])
        assert len(result.applied_changes) == 1
        assert result.applied_changes[0]["stat_key"] == "HP"

    def test_valid_change_persisted_in_event_log(self, db_path, vm) -> None:
        """An accepted change is written to Event_Log as a stat_change event."""
        response = LLMResponse(
            narrative_text="You spend 10 gold.",
            tool_call={"state_changes": [
                {"entity_id": "player1", "stat_key": "Gold", "delta": -10}
            ]},
            finish_reason="stop",
        )
        arb, _ = _make_arbitrator(db_path, vm, response)
        arb.process_turn("s1", 1, {"player": "buy item"}, "sys", [])

        es = EventSourcer(db_path)
        events = es.get_events("s1")
        stat_events = [e for e in events if e["event_type"] == "stat_change"
                       and e["payload"].get("stat_key") == "Gold"]
        # Should have the initial +50 seeded event plus this -10
        deltas = [e["payload"]["delta"] for e in stat_events]
        assert -10 in deltas

    def test_narrative_returned_always(self, db_path, vm) -> None:
        """The narrative text is returned even when there is no tool-call."""
        response = LLMResponse(
            narrative_text="Nothing happens.",
            tool_call=None,
            finish_reason="stop",
        )
        arb, _ = _make_arbitrator(db_path, vm, response)
        result = arb.process_turn("s1", 1, {"player": "wait"}, "sys", [])
        assert result.narrative_text == "Nothing happens."

    def test_stat_set_value_change_applied(self, db_path, vm) -> None:
        """A value (string) change, not just a delta, is accepted and applied."""
        response = LLMResponse(
            narrative_text="Your title changes.",
            tool_call={"state_changes": [
                {"entity_id": "player1", "stat_key": "Title", "value": "Knight"}
            ]},
            finish_reason="stop",
        )
        arb, _ = _make_arbitrator(db_path, vm, response)
        result = arb.process_turn("s1", 1, {"player": "earn title"}, "sys", [])
        assert len(result.applied_changes) == 1


# ---------------------------------------------------------------------------
# process_turn — invalid state change (Correction Loop)
# ---------------------------------------------------------------------------

class TestCorrectionLoop:
    def test_insufficient_resource_rejected(self, db_path, vm) -> None:
        """A change that would drive a resource below zero (spend 200 of 50 Gold)
        is rejected with a reason."""
        # player1 has Gold=50; try to deduct 200
        response = LLMResponse(
            narrative_text="You try to buy a castle.",
            tool_call={"state_changes": [
                {"entity_id": "player1", "stat_key": "Gold", "delta": -200}
            ]},
            finish_reason="stop",
        )
        arb, _ = _make_arbitrator(db_path, vm, response)
        result = arb.process_turn("s1", 1, {"player": "buy castle"}, "sys", [])
        assert len(result.rejected_changes) == 1
        assert "reason" in result.rejected_changes[0]
        assert "Gold" in result.rejected_changes[0]["reason"]

    def test_rejected_change_not_in_event_log(self, db_path, vm) -> None:
        """A rejected change is never persisted to Event_Log."""
        response = LLMResponse(
            narrative_text="Attempted theft.",
            tool_call={"state_changes": [
                {"entity_id": "player1", "stat_key": "Gold", "delta": -999}
            ]},
            finish_reason="stop",
        )
        arb, _ = _make_arbitrator(db_path, vm, response)
        arb.process_turn("s1", 1, {"player": "steal"}, "sys", [])

        es = EventSourcer(db_path)
        events = es.get_events("s1")
        turn1_stat_changes = [
            e for e in events
            if e["turn_id"] == 1
            and e["event_type"] == "stat_change"
            and e["payload"].get("stat_key") == "Gold"
        ]
        assert len(turn1_stat_changes) == 0

    def test_pending_correction_set_after_rejection(self, db_path, vm) -> None:
        """A rejection queues a pending narrator-hint correction for next turn."""
        response = LLMResponse(
            narrative_text="Bad action.",
            tool_call={"state_changes": [
                {"entity_id": "player1", "stat_key": "Gold", "delta": -999}
            ]},
            finish_reason="stop",
        )
        arb, _ = _make_arbitrator(db_path, vm, response)
        arb.process_turn("s1", 1, {"player": "bad"}, "sys", [])
        assert arb._pending_correction is not None
        assert "[NARRATOR HINT:" in arb._pending_correction

    def test_pending_correction_injected_in_next_turn(self, db_path, vm) -> None:
        """The queued correction is injected into the next turn's system prompt."""
        # Turn 1: reject a change
        response1 = LLMResponse(
            narrative_text="Fail.",
            tool_call={"state_changes": [
                {"entity_id": "player1", "stat_key": "Gold", "delta": -999}
            ]},
            finish_reason="stop",
        )
        response2 = LLMResponse(narrative_text="Acknowledged.", tool_call=None, finish_reason="stop")

        llm1 = _StubLLM(response1)
        llm2 = _StubLLM(response2)

        es = EventSourcer(db_path)
        mp = ModifierProcessor(db_path)
        re = RulesEngine([])
        arb = ArbitratorEngine(db_path, [])
        arb.configure(llm1, vm)

        arb.process_turn("s1", 1, {"player": "bad"}, "sys", [])
        assert arb._pending_correction is not None

        # Turn 2: switch LLM stub and check correction injected
        arb._llm = llm2
        arb.process_turn("s1", 2, {"player": "continue"}, "sys", [])

        # Correction must appear in the messages sent to turn-2 LLM
        messages = llm2.last_messages
        system_msgs = [m for m in messages if m["role"] == "system"]
        correction_injected = any("[NARRATOR HINT:" in m["content"] for m in system_msgs)
        assert correction_injected

    def test_pending_correction_cleared_after_use(self, db_path, vm) -> None:
        """Once injected, the pending correction is cleared so it fires only once."""
        response1 = LLMResponse(
            narrative_text="Fail.",
            tool_call={"state_changes": [
                {"entity_id": "player1", "stat_key": "Gold", "delta": -999}
            ]},
            finish_reason="stop",
        )
        response2 = LLMResponse(narrative_text="ok", tool_call=None, finish_reason="stop")

        arb, _ = _make_arbitrator(db_path, vm, response1)
        arb.process_turn("s1", 1, {"player": "bad"}, "sys", [])

        arb._llm = _StubLLM(response2)
        arb.process_turn("s1", 2, {"player": "continue"}, "sys", [])

        assert arb._pending_correction is None

    def test_unknown_entity_rejected(self, db_path, vm) -> None:
        """A change targeting a non-existent entity is rejected as 'Unknown entity'."""
        response = LLMResponse(
            narrative_text="ghost action",
            tool_call={"state_changes": [
                {"entity_id": "ghost_entity", "stat_key": "HP", "delta": -10}
            ]},
            finish_reason="stop",
        )
        arb, _ = _make_arbitrator(db_path, vm, response)
        result = arb.process_turn("s1", 1, {"player": "hmm"}, "sys", [])
        assert len(result.rejected_changes) == 1
        assert "Unknown entity" in result.rejected_changes[0]["reason"]


# ---------------------------------------------------------------------------
# process_turn — Rules Engine integration
# ---------------------------------------------------------------------------

class TestRulesTrigger:
    def test_rule_triggered_action_in_triggered_rules(self, db_path, vm) -> None:
        """When a change crosses a rule's threshold, the rule's action is reported
        in triggered_rules."""
        # Rule: if player1 HP <= 50, set Status = "wounded"
        rule = {
            "rule_id": "wound_rule",
            "priority": 0,
            "target_entity": "player1",
            "conditions": {"operator": "AND", "clauses": [
                {"stat": "HP", "comparator": "<=", "value": 50}
            ]},
            "actions": [
                {"type": "stat_set", "target": "player1", "stat": "Status", "value": "wounded"}
            ],
        }
        # Reduce HP from 100 to 40
        response = LLMResponse(
            narrative_text="You are badly hurt.",
            tool_call={"state_changes": [
                {"entity_id": "player1", "stat_key": "HP", "delta": -60}
            ]},
            finish_reason="stop",
        )
        arb, _ = _make_arbitrator(db_path, vm, response, rules=[rule])
        result = arb.process_turn("s1", 1, {"player": "fight"}, "sys", [])

        assert len(result.triggered_rules) == 1
        assert result.triggered_rules[0]["type"] == "stat_set"

    def test_rule_trigger_persisted_in_event_log(self, db_path, vm) -> None:
        """A fired rule writes a rule_trigger event to Event_Log."""
        rule = {
            "rule_id": "death_rule",
            "priority": 0,
            "target_entity": "player1",
            "conditions": {"operator": "AND", "clauses": [
                {"stat": "HP", "comparator": "<=", "value": 0}
            ]},
            "actions": [
                {"type": "stat_set", "target": "player1", "stat": "Status", "value": "dead"}
            ],
        }
        response = LLMResponse(
            narrative_text="Fatal blow.",
            tool_call={"state_changes": [
                {"entity_id": "player1", "stat_key": "HP", "delta": -100}
            ]},
            finish_reason="stop",
        )
        arb, _ = _make_arbitrator(db_path, vm, response, rules=[rule])
        arb.process_turn("s1", 1, {"player": "die"}, "sys", [])

        es = EventSourcer(db_path)
        events = es.get_events("s1")
        rule_events = [e for e in events if e["event_type"] == "rule_trigger"]
        assert len(rule_events) == 1


# ---------------------------------------------------------------------------
# process_turn — VectorMemory embedding
# ---------------------------------------------------------------------------

class TestVectorMemoryIntegration:
    def test_narrative_embedded_after_turn(self, db_path, vm) -> None:
        """The turn's narrative is embedded into VectorMemory and is retrievable."""
        response = LLMResponse(
            narrative_text="The ancient ruins loom before you.",
            tool_call=None,
            finish_reason="stop",
        )
        arb, _ = _make_arbitrator(db_path, vm, response)
        arb.process_turn("s1", 1, {"player": "explore"}, "sys", [])

        results = vm.query("s1", "ruins ancient", k=5)
        assert any("ruins" in r["text"] for r in results)

    def test_embedded_chunk_has_correct_turn_id(self, db_path, vm) -> None:
        """The embedded narrative chunk is tagged with the turn it came from."""
        response = LLMResponse(
            narrative_text="Turn 5 narrative content.",
            tool_call=None,
            finish_reason="stop",
        )
        arb, _ = _make_arbitrator(db_path, vm, response)
        arb.process_turn("s1", 5, {"player": "action"}, "sys", [])

        results = vm.query("s1", "narrative content", k=1)
        assert results[0]["turn_id"] == 5


# ---------------------------------------------------------------------------
# process_turn — streaming callback (Phase 4)
# ---------------------------------------------------------------------------

class TestStreamingCallback:
    """Verify that stream_token_callback is called per-token and the
    assembled result is consistent with non-streaming behaviour."""

    class _StreamingStubLLM(_StubLLM):
        """Stub that yields tokens one-by-one from stream_tokens()."""

        def stream_tokens(self, messages, **kwargs):
            # Split the narrative text into character tokens for fine granularity
            text = self._response.narrative_text
            # If there's a tool call, append the fence so parse_tool_call works
            if self._response.tool_call is not None:
                import json as _j
                text = (
                    text
                    + "\n~~~json\n"
                    + _j.dumps(self._response.tool_call)
                    + "\n~~~"
                )
            for char in text:
                yield char

    def test_callback_called_for_each_token(self, db_path, vm) -> None:
        """With a stream callback, every streamed token is delivered to it."""
        response = LLMResponse(
            narrative_text="Stream test.",
            tool_call=None,
            finish_reason="stop",
        )
        llm = self._StreamingStubLLM(response)
        from axiom.events import EventSourcer
        from axiom.modifiers import ModifierProcessor
        from axiom.rules import RulesEngine
        from axiom.arbitrator import ArbitratorEngine
        arb = ArbitratorEngine(db_path, [])
        arb.configure(llm, vm)
        received: list[str] = []
        arb.process_turn(
            "s1", 1, {"player": "test"}, "sys", [],
            stream_token_callback=received.append,
        )
        # Every character of "Stream test." must have been received
        assert "".join(received) == "Stream test."

    def test_callback_result_matches_non_streaming(self, db_path, vm) -> None:
        """The assembled streaming result equals the non-streaming result for the
        same response."""
        response = LLMResponse(
            narrative_text="Consistent result.",
            tool_call=None,
            finish_reason="stop",
        )
        # Non-streaming result
        arb_ns, _ = _make_arbitrator(db_path, vm, response)
        result_ns = arb_ns.process_turn("s1", 1, {"player": "go"}, "sys", [])

        # Streaming result (different db needed to avoid turn collision)
        import tempfile
        from pathlib import Path
        from axiom.schema import create_universe_db
        import sqlite3
        tmp2 = tempfile.mkdtemp()
        db2 = str(Path(tmp2) / "u2.db")
        create_universe_db(db2)
        with sqlite3.connect(db2) as conn:
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute("INSERT INTO Stat_Definitions (stat_id, name, value_type) VALUES ('1', 'HP', 'numeric'), ('2', 'Gold', 'numeric'), ('3', 'Title', 'categorical'), ('4', 'Status', 'categorical'), ('5', 'Army_Size', 'numeric'), ('6', 'Wealth', 'numeric')")
            conn.execute("INSERT INTO Saves (save_id, player_name, difficulty, last_updated) VALUES (?,?,?,?);",
                         ("s1", "H", "Normal", "2026-01-01T00:00:00"))
            conn.execute("INSERT INTO Entities (entity_id, entity_type, name, is_active) VALUES (?,?,?,?);",
                         ("player1", "player", "A", 1))
            conn.commit()
        from unittest.mock import patch
        with patch(
            "axiom.memory.SentenceTransformerEmbeddingFunction",
            return_value=_FakeEmbeddingFn(),
        ):
            from axiom.memory import VectorMemory
            import os
            vm2 = VectorMemory(persist_dir=str(Path(tmp2) / "chroma"))

        llm_s = self._StreamingStubLLM(response)
        from axiom.events import EventSourcer
        from axiom.modifiers import ModifierProcessor
        from axiom.rules import RulesEngine
        from axiom.arbitrator import ArbitratorEngine
        arb_s = ArbitratorEngine(db2, [])
        arb_s.configure(llm_s, vm2)
        tokens: list[str] = []
        result_s = arb_s.process_turn(
            "s1", 1, {"player": "go"}, "sys", [],
            stream_token_callback=tokens.append,
        )
        assert result_s.narrative_text == result_ns.narrative_text

    def test_none_callback_uses_complete(self, db_path, vm) -> None:
        """Passing no callback must call llm.complete(), not stream_tokens."""
        response = LLMResponse("Classic path.", None, "stop")
        arb, llm = _make_arbitrator(db_path, vm, response)
        result = arb.process_turn("s1", 1, {"player": "action"}, "sys", [])
        # complete() was called (stream_tokens would have raised on _StubLLM)
        assert result.narrative_text == "Classic path."


# ---------------------------------------------------------------------------
# process_turn — Dynamic Stop Sequences (Phase 11.1)
# ---------------------------------------------------------------------------

class TestDynamicStopSequences:
    def test_dynamic_stop_sequences_passed_to_llm(self, db_path, vm) -> None:
        """Per-player stop sequences (e.g. '\\nplayer1:') are passed to the LLM to
        prevent it impersonating the player."""
        response = LLMResponse("OK", None, "stop")

        class _SpyLLM(_StubLLM):
            def __init__(self, res):
                super().__init__(res)
                self.passed_stops = []
            
            def complete(self, messages, stream=False, stop_sequences=None, **kwargs):
                self.passed_stops = stop_sequences or []
                return super().complete(messages, stream)

        llm = _SpyLLM(response)

        from axiom.events import EventSourcer
        from axiom.modifiers import ModifierProcessor
        from axiom.rules import RulesEngine
        from axiom.arbitrator import ArbitratorEngine
        arb = ArbitratorEngine(db_path, [])
        # Separate Timekeeper backend so its second call (no stop_sequences) does
        # not overwrite the stops captured from the narrative call (TICKET-016).
        time_llm = _StubLLM(LLMResponse('{"elapsed_minutes": 5}', None, "stop"))
        arb.configure(llm, vm, time_llm=time_llm)

        arb.process_turn("s1", 1, {"player1": "hello"}, "sys", [])
        
        # Verify the dynamic stop sequences contains the player entity
        assert llm.passed_stops is not None
        assert "\nplayer1:" in llm.passed_stops
        assert "\n[player1]" in llm.passed_stops
        assert "\nUser:" in llm.passed_stops


# ---------------------------------------------------------------------------
# process_turn — Companion Mode (Asymmetric Gameplay)
# ---------------------------------------------------------------------------

class TestCompanionMode:
    def test_plot_armor_prevents_rejection(self, db_path, vm) -> None:
        """In Companion mode, a change that would normally be rejected for the
        Hero is allowed (plot armor)."""
        # Create a Hero NPC via EventSourcer for correct State_Cache integration
        from axiom.events import EventSourcer
        es = EventSourcer(db_path)
        es.append_event("s1", 0, "entity_create", "hero1",
                        {"entity_id": "hero1", "entity_type": "npc", "name": "Legendary Hero"})
        es.append_event("s1", 0, "stat_change", "hero1",
                        {"entity_id": "hero1", "stat_key": "HP", "delta": 10})
        es.rebuild_state_cache("s1")

        # Try to deduct 20 HP from Hero (current HP=10)
        response = LLMResponse(
            narrative_text="The hero is hit hard.",
            tool_call={"state_changes": [
                {"entity_id": "hero1", "stat_key": "HP", "delta": -20}
            ]},
            finish_reason="stop",
        )
        
        arb, _ = _make_arbitrator(db_path, vm, response)
        
        # In Companion mode, this should be ALLOWED (valid=True) due to Plot Armor
        result = arb.process_turn(
            "s1", 1, {"player": "watch"}, "sys", [], 
            mode="Companion", 
            hero_entity_id="hero1"
        )
        
        assert len(result.applied_changes) == 1
        assert len(result.rejected_changes) == 0

    def test_hero_action_included_in_prompt_and_logged(self, db_path, vm) -> None:
        """A Companion hero_action is injected into the prompt as [HERO INTENT]
        and logged as a hero_intent event."""
        response = LLMResponse("OK", None, "stop")
        arb, llm = _make_arbitrator(db_path, vm, response)

        arb.process_turn(
            "s1", 1, {"player": "companion action", "hero1": "Hero charges forward!"}, "sys", [], 
            mode="Companion",
            hero_entity_id="hero1"
        )
        
        # 1. Check messages sent to LLM
        found = False
        for msg in llm.last_messages:
            if "[hero1] INTENT: Hero charges forward!" in msg["content"]:
                found = True
        assert found

        # 2. Check Event_Log
        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT event_type, target_entity, payload FROM Event_Log "
                "WHERE event_type = 'hero_intent';"
            ).fetchone()
            assert row is not None
            assert row[0] == "hero_intent"
            assert row[1] == "hero1"
            assert json.loads(row[2])["text"] == "Hero charges forward!"


# ---------------------------------------------------------------------------
# process_turn — Causal time (Pilier 5)
# ---------------------------------------------------------------------------

class TestCausalTime:
    def test_timekeeper_elapsed_minutes_drives_clock_and_timeline(self, db_path, vm) -> None:
        """When the Timekeeper returns elapsed_minutes, the result and the single
        Timeline row both advance the in-game clock by exactly that amount."""
        from axiom.config import AppConfig
        narrative_llm = _StubLLM(LLMResponse("You wait by the fire.", None, "stop"))
        time_llm = _StubLLM(LLMResponse("", {"elapsed_minutes": 45}, "stop"))
        arb = ArbitratorEngine(db_path, [])
        arb.configure(narrative_llm, vm, time_llm=time_llm)

        with patch("axiom.config.load_config", return_value=AppConfig(timekeeper_enabled=True)):
            result = arb.process_turn("s1", 1, {"player1": "I wait."}, "sys", [])

        assert result.elapsed_minutes == 45
        # App-M3: the absolute in-game time is carried in the result so the GUI
        # can refresh its clock without a main-thread DB read.
        assert result.in_game_time == 45
        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT in_game_time, description FROM Timeline WHERE save_id='s1' AND turn_id=1;"
            ).fetchall()
        assert len(rows) == 1          # exactly one timeline row per turn
        assert rows[0][0] == 45
        assert "45" in rows[0][1]
        assert result.in_game_time == rows[0][0]

    def test_timekeeper_disabled_uses_scene_pace_and_skips_second_call(self, db_path, vm) -> None:
        """With the Timekeeper disabled, no second LLM call is made and the
        elapsed time falls back to the scene-pace default (combat -> 2 min)."""
        from axiom.config import AppConfig

        class _CountingLLM(_StubLLM):
            def __init__(self, response):
                super().__init__(response)
                self.calls = 0

            def complete(self, messages, stream=False, **kwargs):
                self.calls += 1
                return super().complete(messages, stream)

        narrative_llm = _StubLLM(LLMResponse(
            "Blades clash.",
            {"state_changes": [], "scene_pace": "combat"},
            "stop",
        ))
        time_llm = _CountingLLM(LLMResponse("", {"elapsed_minutes": 999}, "stop"))
        arb = ArbitratorEngine(db_path, [])
        arb.configure(narrative_llm, vm, time_llm=time_llm)

        with patch("axiom.config.load_config", return_value=AppConfig(timekeeper_enabled=False)):
            result = arb.process_turn("s1", 1, {"player1": "I strike!"}, "sys", [])

        assert time_llm.calls == 0          # Timekeeper never consulted
        assert result.elapsed_minutes == 2  # combat pace default
        assert result.scene_pace == "combat"

    def test_single_timeline_row_when_player_travels(self, db_path, vm) -> None:
        """A turn where the player changes Location writes exactly one Timeline
        row, annotated with the destination (no duplicate row — TICKET-019)."""
        from axiom.config import AppConfig
        with sqlite3.connect(db_path) as conn:
            conn.execute("INSERT INTO Stat_Definitions (stat_id, name, value_type) VALUES ('7','Location','categorical');")
            conn.execute("INSERT INTO Locations (location_id, name, scale) VALUES ('town_a','Town A','city'), ('city_b','City B','city');")
            conn.execute("INSERT INTO Location_Connections (source_id, target_id, distance_km) VALUES ('town_a','city_b',12);")
            conn.commit()
        es = EventSourcer(db_path)
        es.append_event("s1", 0, "stat_set", "player1",
                        {"entity_id": "player1", "stat_key": "Location", "value": "town_a"})
        es.rebuild_state_cache("s1")

        narrative_llm = _StubLLM(LLMResponse(
            "You journey to City B.",
            {"state_changes": [{"entity_id": "player1", "stat_key": "Location", "value": "city_b"}]},
            "stop",
        ))
        time_llm = _StubLLM(LLMResponse("", {"elapsed_minutes": 60}, "stop"))
        arb = ArbitratorEngine(db_path, [])
        arb.configure(narrative_llm, vm, time_llm=time_llm)

        with patch("axiom.config.load_config", return_value=AppConfig(timekeeper_enabled=True)):
            arb.process_turn("s1", 1, {"player1": "Go to City B."}, "sys", [])

        with sqlite3.connect(db_path) as conn:
            rows = conn.execute(
                "SELECT in_game_time, description FROM Timeline WHERE save_id='s1' AND turn_id=1;"
            ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 60
        assert "city_b" in rows[0][1].lower()

    def test_process_turn_injects_player_persona(self, db_path, vm) -> None:
        """process_turn fetches player_persona from Saves and includes it in the narrative prompt."""
        with sqlite3.connect(db_path) as conn:
            conn.execute("UPDATE Saves SET player_persona = 'A legendary warrior' WHERE save_id = 's1';")
            conn.commit()

        response = LLMResponse(narrative_text="Prose", tool_call=None, finish_reason="stop")
        arb, llm = _make_arbitrator(db_path, vm, response)
        
        arb.process_turn("s1", 1, {"player1": "I draw my weapon"}, "Universe prompt", [])
        
        # Verify the prompt passed to the LLM contains the player persona
        system_msg = next(m for m in llm.last_messages if m["role"] == "system")
        assert "A legendary warrior" in system_msg["content"]
        assert "CHARACTER BACKGROUND:" in system_msg["content"]

    def test_process_turn_injects_group_awareness(self, db_path, vm) -> None:
        """process_turn identifies local entities and injects the Group Awareness rule."""
        es = EventSourcer(db_path)
        # Register entities and set their location to Forest (matching player1, npc1 from db_path fixture)
        es.append_event("s1", 0, "entity_create", "npc2", {"entity_id": "npc2"})
        
        es.append_event("s1", 0, "stat_set", "player1", {"entity_id": "player1", "stat_key": "Location", "value": "Forest"})
        es.append_event("s1", 0, "stat_set", "npc1", {"entity_id": "npc1", "stat_key": "Location", "value": "Forest"})
        es.append_event("s1", 0, "stat_set", "npc2", {"entity_id": "npc2", "stat_key": "Location", "value": "Forest"})
        es.rebuild_state_cache("s1")

        with sqlite3.connect(db_path) as conn:
            conn.execute("INSERT INTO Entities (entity_id, entity_type, name, is_active) VALUES ('npc2', 'npc', 'Aglae', 1);")
            conn.commit()


        response = LLMResponse(narrative_text="Prose", tool_call=None, finish_reason="stop")
        arb, llm = _make_arbitrator(db_path, vm, response)
        
        arb.process_turn("s1", 1, {"player1": "I walk"}, "Universe prompt", [])
        
        system_msg = next(m for m in llm.last_messages if m["role"] == "system")
        assert "Group Awareness" in system_msg["content"]
        assert "Aria" in system_msg["content"]
        assert "Goblin" in system_msg["content"]
        assert "Aglae" in system_msg["content"]
        assert "are all present together in the same location" in system_msg["content"]

        
        final_msg = llm.last_messages[-1]
        assert "are ALL present in the scene together" in final_msg["content"]
        assert "DO NOT ignore any members or refer to them as 'you two'" in final_msg["content"]

    def test_focus_terms_include_location_and_on_scene_names(self, db_path, vm) -> None:
        """TICKET-073: the scene's location AND the names of the characters sharing
        it are passed as focus_terms to the vector query (the player is excluded)."""
        es = EventSourcer(db_path)
        es.append_event("s1", 0, "stat_set", "player1", {"entity_id": "player1", "stat_key": "Location", "value": "Forest"})
        es.append_event("s1", 0, "stat_set", "npc1", {"entity_id": "npc1", "stat_key": "Location", "value": "Forest"})
        es.rebuild_state_cache("s1")

        response = LLMResponse(narrative_text="Prose", tool_call=None, finish_reason="stop")
        arb, _ = _make_arbitrator(db_path, vm, response)

        captured: dict = {}
        real_query = arb._vector_memory.query

        def _spy(*args, **kwargs):
            # Capture the narrative query, not the dedicated lore query (TICKET-072).
            if kwargs.get("chunk_type") != "lore":
                captured["focus_terms"] = kwargs.get("focus_terms")
            return real_query(*args, **kwargs)

        arb._vector_memory.query = _spy
        arb.process_turn("s1", 1, {"player1": "I look around"}, "sys", [])

        terms = captured["focus_terms"]
        assert terms is not None
        assert "Forest" in terms          # the player's current location
        assert "Goblin" in terms          # npc1, sharing the location
        assert "Aria" not in terms        # player1's name is excluded

    def test_focus_terms_exclude_characters_elsewhere(self, db_path, vm) -> None:
        """A character in a *different* location is not added to focus_terms."""
        es = EventSourcer(db_path)
        es.append_event("s1", 0, "stat_set", "player1", {"entity_id": "player1", "stat_key": "Location", "value": "Forest"})
        es.append_event("s1", 0, "stat_set", "npc1", {"entity_id": "npc1", "stat_key": "Location", "value": "Castle"})
        es.rebuild_state_cache("s1")

        response = LLMResponse(narrative_text="Prose", tool_call=None, finish_reason="stop")
        arb, _ = _make_arbitrator(db_path, vm, response)

        captured: dict = {}
        real_query = arb._vector_memory.query

        def _spy(*args, **kwargs):
            # Capture the narrative query, not the dedicated lore query (TICKET-072).
            if kwargs.get("chunk_type") != "lore":
                captured["focus_terms"] = kwargs.get("focus_terms")
            return real_query(*args, **kwargs)

        arb._vector_memory.query = _spy
        arb.process_turn("s1", 1, {"player1": "I look around"}, "sys", [])

        terms = captured["focus_terms"]
        assert terms == ["Forest"]        # only the location; the NPC is elsewhere


class TestScheduledEventFiring:
    """TICKET-075: when a scheduled event fires, the turn it fired on is recorded
    in Fired_Scheduled_Events so a later rewind can un-fire it."""

    def test_fired_event_is_tagged_with_current_turn(self, db_path, vm) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO Scheduled_Events (event_id, trigger_minute, title, description) "
                "VALUES ('ev1', 0, 'Quake', 'The ground shakes.');"
            )
            conn.commit()

        response = LLMResponse(narrative_text="Prose", tool_call=None, finish_reason="stop")
        arb, _ = _make_arbitrator(db_path, vm, response)
        arb.process_turn("s1", 7, {"player1": "I look around"}, "sys", [])

        with sqlite3.connect(db_path) as conn:
            row = conn.execute(
                "SELECT fired_turn_id FROM Fired_Scheduled_Events "
                "WHERE save_id = 's1' AND event_id = 'ev1';"
            ).fetchone()
        assert row is not None        # the event fired (trigger_minute 0 <= clock)
        assert row[0] == 7            # tagged with the turn it fired on


class TestLoreSemanticRetrieval:
    """TICKET-072: lore retrieval is semantic with link expansion, and falls back
    to deterministic keyword overlap when no embedding runtime is available."""

    def _seed_lore(self, db_path: str) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.executemany(
                "INSERT INTO Lore_Book (entry_id, category, name, keywords, content) "
                "VALUES (?, ?, ?, ?, ?);",
                [
                    ("coup", "history", "The Coup", "rebellion power",
                     "The Coup of Highport toppled the throne."),
                    ("house", "history", "House Arodan", "noble family",
                     "House Arodan, an old noble line."),
                    ("storm", "nature", "Storms", "rain wind",
                     "Storms batter the northern sea."),
                ],
            )
            conn.commit()

    def test_expand_lore_adds_same_category_link(self, db_path) -> None:
        """A semantic seed pulls in a related entry (shared category), but not an
        unrelated one."""
        self._seed_lore(db_path)
        arb = ArbitratorEngine(db_path, [])
        result = arb._expand_lore(["coup"], k=1)
        names = [e["name"] for e in result]
        assert names[0] == "The Coup"      # the seed comes first
        assert "House Arodan" in names     # linked by shared category 'history'
        assert "Storms" not in names       # different category, no shared keywords

    def test_semantic_path_used_when_vector_memory_present(self, db_path, vm) -> None:
        self._seed_lore(db_path)
        response = LLMResponse(narrative_text="Prose", tool_call=None, finish_reason="stop")
        arb, _ = _make_arbitrator(db_path, vm, response)

        result = arb._fetch_relevant_lore("s1", "tell me about the Coup of Highport", k=2)

        assert result                      # semantic retrieval returned entries
        assert "s1" in arb._lore_synced    # lore was embedded once
        assert vm.query("s1", "Highport", k=5, chunk_type="lore")  # chunks present

    def test_keyword_fallback_when_no_vector_memory(self, db_path) -> None:
        """With no embedding runtime, retrieval degrades to keyword overlap."""
        self._seed_lore(db_path)
        arb = ArbitratorEngine(db_path, [])   # vector memory never configured
        result = arb._fetch_relevant_lore("s1", "rebellion against the throne", k=5)
        assert any(e["name"] == "The Coup" for e in result)  # matched on 'rebellion'


class TestInventoryQuantityValidation:
    """A malformed `quantity` from LLM JSON must reject the change, never crash.

    `quantity` is untrusted: int(None)/int("two") raise, a negative add violates
    the quantity>=0 CHECK, and a negative remove would silently *add* items.
    """

    def _arb(self, db_path: str) -> ArbitratorEngine:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO Item_Definitions (item_id, name) VALUES ('sword', 'Sword');"
            )
            conn.commit()
        return ArbitratorEngine(db_path, [])

    def test_valid_positive_quantity_passes(self, db_path: str) -> None:
        arb = self._arb(db_path)
        ok, _ = arb._validate_inventory_change(
            "s1", {"entity_id": "player1", "item_id": "sword", "action": "add", "quantity": 2}
        )
        assert ok is True

    def test_missing_quantity_defaults_to_one(self, db_path: str) -> None:
        arb = self._arb(db_path)
        ok, _ = arb._validate_inventory_change(
            "s1", {"entity_id": "player1", "item_id": "sword", "action": "add"}
        )
        assert ok is True

    @pytest.mark.parametrize("bad", ["two", None, "2.5", "", [1]])
    def test_non_integer_quantity_rejected_not_raised(self, db_path: str, bad) -> None:
        arb = self._arb(db_path)
        ok, reason = arb._validate_inventory_change(
            "s1", {"entity_id": "player1", "item_id": "sword", "action": "add", "quantity": bad}
        )
        assert ok is False
        assert "whole number" in reason

    @pytest.mark.parametrize("bad", [0, -3])
    def test_non_positive_quantity_rejected(self, db_path: str, bad) -> None:
        arb = self._arb(db_path)
        ok, reason = arb._validate_inventory_change(
            "s1", {"entity_id": "player1", "item_id": "sword", "action": "remove", "quantity": bad}
        )
        assert ok is False
        assert "positive" in reason



