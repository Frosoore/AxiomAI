"""
tests/test_event_sourcing.py

Unit tests for database/event_sourcing.py — verifies event appending,
retrieval, State_Cache rebuilding, and the _apply_event pure function.
"""

from pathlib import Path

import pytest

from axiom.schema import create_universe_db
from axiom.events import EventSourcer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def db(tmp_path: Path) -> tuple[str, EventSourcer]:
    """Provision a fresh universe db and return (db_path, EventSourcer)."""
    db_path = str(tmp_path / "universe.db")
    create_universe_db(db_path)

    # Seed the minimum required rows so FK constraints are satisfied
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute(
            "INSERT INTO Saves (save_id, player_name, difficulty, last_updated) VALUES (?, ?, ?, ?);",
            ("save1", "Hero", "Normal", "2026-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO Entities (entity_id, entity_type, name, is_active) VALUES (?, ?, ?, ?);",
            ("player1", "player", "Aria", 1),
        )
        conn.execute(
            "INSERT INTO Entities (entity_id, entity_type, name, is_active) VALUES (?, ?, ?, ?);",
            ("npc1", "npc", "Goblin", 1),
        )
        conn.commit()

    return db_path, EventSourcer(db_path)


# ---------------------------------------------------------------------------
# append_event
# ---------------------------------------------------------------------------

class TestAppendEvent:
    def test_returns_incrementing_ids(self, db: tuple) -> None:
        """Each append_event returns a strictly larger auto-generated event_id."""
        _, es = db
        id1 = es.append_event("save1", 1, "dialogue", "player1", {"text": "Hello"})
        id2 = es.append_event("save1", 1, "dialogue", "player1", {"text": "World"})
        assert id2 > id1

    def test_event_stored_correctly(self, db: tuple) -> None:
        """An appended event is retrievable with its turn_id, type and payload intact."""
        db_path, es = db
        es.append_event("save1", 3, "stat_change", "player1", {"entity_id": "player1", "stat_key": "HP", "delta": -10})
        events = es.get_events("save1")
        assert len(events) == 1
        ev = events[0]
        assert ev["turn_id"] == 3
        assert ev["event_type"] == "stat_change"
        assert ev["payload"]["stat_key"] == "HP"
        assert ev["payload"]["delta"] == -10


# ---------------------------------------------------------------------------
# get_events
# ---------------------------------------------------------------------------

class TestGetEvents:
    def test_returns_all_events(self, db: tuple) -> None:
        """get_events with no filter returns every appended event for the save."""
        _, es = db
        for turn in range(1, 6):
            es.append_event("save1", turn, "dialogue", "player1", {"text": f"turn{turn}"})
        events = es.get_events("save1")
        assert len(events) == 5

    def test_up_to_turn_id_filter(self, db: tuple) -> None:
        """get_events(up_to_turn_id=N) returns only events with turn_id <= N."""
        _, es = db
        for turn in range(1, 11):
            es.append_event("save1", turn, "dialogue", "player1", {"text": f"t{turn}"})
        events = es.get_events("save1", up_to_turn_id=5)
        assert len(events) == 5
        assert all(ev["turn_id"] <= 5 for ev in events)

    def test_returns_empty_for_unknown_save(self, db: tuple) -> None:
        """get_events for a save with no events returns an empty list."""
        _, es = db
        assert es.get_events("nonexistent_save") == []

    def test_payload_decoded_to_dict(self, db: tuple) -> None:
        """get_events deserialises the stored JSON payload back into a dict."""
        _, es = db
        es.append_event("save1", 1, "stat_set", "player1", {"entity_id": "player1", "stat_key": "Name", "value": "Aria"})
        events = es.get_events("save1")
        assert isinstance(events[0]["payload"], dict)


# ---------------------------------------------------------------------------
# _apply_event (pure function)
# ---------------------------------------------------------------------------

class TestApplyEvent:
    def test_entity_create(self) -> None:
        """entity_create registers the entity in the cache with no stats."""
        cache: dict = {}
        event = {"event_type": "entity_create", "target_entity": "p1",
                 "payload": {"entity_id": "p1", "entity_type": "player", "name": "Hero"}}
        result = EventSourcer._apply_event(event, cache)
        assert "p1" in result

    def test_stat_change_delta(self) -> None:
        """stat_change with a delta adjusts the existing numeric stat (100 - 30 = 70)."""
        cache = {"p1": {"HP": "100"}}
        event = {"event_type": "stat_change", "target_entity": "p1",
                 "payload": {"entity_id": "p1", "stat_key": "HP", "delta": -30}}
        result = EventSourcer._apply_event(event, cache)
        assert result["p1"]["HP"] == "70"

    def test_stat_change_delta_from_zero(self) -> None:
        """A delta on an absent stat treats the prior value as 0."""
        cache: dict = {}
        event = {"event_type": "stat_change", "target_entity": "p1",
                 "payload": {"entity_id": "p1", "stat_key": "Gold", "delta": 50}}
        result = EventSourcer._apply_event(event, cache)
        assert result["p1"]["Gold"] == "50"

    def test_stat_set_string_value(self) -> None:
        """stat_set overwrites a stat with the given string value."""
        cache = {"p1": {"Status": "alive"}}
        event = {"event_type": "stat_set", "target_entity": "p1",
                 "payload": {"entity_id": "p1", "stat_key": "Status", "value": "dead"}}
        result = EventSourcer._apply_event(event, cache)
        assert result["p1"]["Status"] == "dead"

    def test_stat_change_with_value_key(self) -> None:
        """stat_change with a 'value' key (not 'delta') acts like stat_set."""
        cache: dict = {}
        event = {"event_type": "stat_change", "target_entity": "p1",
                 "payload": {"entity_id": "p1", "stat_key": "Alignment", "value": "Chaotic"}}
        result = EventSourcer._apply_event(event, cache)
        assert result["p1"]["Alignment"] == "Chaotic"

    def test_dialogue_event_ignored(self) -> None:
        """Non-stat events (e.g. dialogue) leave the cache unchanged."""
        cache = {"p1": {"HP": "50"}}
        event = {"event_type": "dialogue", "target_entity": "p1",
                 "payload": {"speaker": "p1", "text": "Hello"}}
        result = EventSourcer._apply_event(event, cache)
        assert result == {"p1": {"HP": "50"}}

    def test_integer_display_preserved(self) -> None:
        """Whole-number results must be stored without decimal point."""
        cache = {"p1": {"Gold": "10"}}
        event = {"event_type": "stat_change", "target_entity": "p1",
                 "payload": {"entity_id": "p1", "stat_key": "Gold", "delta": 5}}
        result = EventSourcer._apply_event(event, cache)
        assert result["p1"]["Gold"] == "15"
        assert "." not in result["p1"]["Gold"]

    def test_float_delta_preserved(self) -> None:
        """A fractional result keeps its decimal part (10 + 0.5 = '10.5')."""
        cache = {"p1": {"Mana": "10"}}
        event = {"event_type": "stat_change", "target_entity": "p1",
                 "payload": {"entity_id": "p1", "stat_key": "Mana", "delta": 0.5}}
        result = EventSourcer._apply_event(event, cache)
        assert result["p1"]["Mana"] == "10.5"


# ---------------------------------------------------------------------------
# rebuild_state_cache + get_current_stats
# ---------------------------------------------------------------------------

class TestRebuildStateCache:
    def _seed_entity(self, es: EventSourcer, save_id: str, entity_id: str,
                     entity_type: str, name: str) -> None:
        es.append_event(save_id, 0, "entity_create", entity_id,
                        {"entity_id": entity_id, "entity_type": entity_type, "name": name})

    def test_full_replay(self, db: tuple) -> None:
        """rebuild replays the whole Event_Log so the cache reflects every
        accumulated change (HP 100 - 20 = 80, Gold 50)."""
        _, es = db
        self._seed_entity(es, "save1", "player1", "player", "Aria")
        es.append_event("save1", 1, "stat_change", "player1",
                        {"entity_id": "player1", "stat_key": "HP", "delta": 100})
        es.append_event("save1", 2, "stat_change", "player1",
                        {"entity_id": "player1", "stat_key": "HP", "delta": -20})
        es.append_event("save1", 3, "stat_change", "player1",
                        {"entity_id": "player1", "stat_key": "Gold", "delta": 50})

        es.rebuild_state_cache("save1")
        stats = es.get_current_stats("save1", "player1")
        assert stats["HP"] == "80"
        assert stats["Gold"] == "50"

    def test_partial_replay_up_to_turn(self, db: tuple) -> None:
        """rebuild(up_to_turn_id=N) only applies changes through turn N
        (turn-3 change excluded → HP stays 80)."""
        _, es = db
        self._seed_entity(es, "save1", "player1", "player", "Aria")
        es.append_event("save1", 1, "stat_change", "player1",
                        {"entity_id": "player1", "stat_key": "HP", "delta": 100})
        es.append_event("save1", 2, "stat_change", "player1",
                        {"entity_id": "player1", "stat_key": "HP", "delta": -20})
        es.append_event("save1", 3, "stat_change", "player1",
                        {"entity_id": "player1", "stat_key": "HP", "delta": -30})

        es.rebuild_state_cache("save1", up_to_turn_id=2)
        stats = es.get_current_stats("save1", "player1")
        assert stats["HP"] == "80"  # only turns 0-2 applied

    def test_multiple_entities(self, db: tuple) -> None:
        """rebuild materialises independent stats for each entity in the save."""
        _, es = db
        self._seed_entity(es, "save1", "player1", "player", "Aria")
        self._seed_entity(es, "save1", "npc1", "npc", "Goblin")
        es.append_event("save1", 1, "stat_change", "player1",
                        {"entity_id": "player1", "stat_key": "HP", "delta": 100})
        es.append_event("save1", 1, "stat_change", "npc1",
                        {"entity_id": "npc1", "stat_key": "HP", "delta": 30})

        es.rebuild_state_cache("save1")
        assert es.get_current_stats("save1", "player1")["HP"] == "100"
        assert es.get_current_stats("save1", "npc1")["HP"] == "30"

    def test_rebuild_is_idempotent(self, db: tuple) -> None:
        """Running rebuild twice yields the same cache (no double-application)."""
        _, es = db
        self._seed_entity(es, "save1", "player1", "player", "Aria")
        es.append_event("save1", 1, "stat_change", "player1",
                        {"entity_id": "player1", "stat_key": "HP", "delta": 75})

        es.rebuild_state_cache("save1")
        es.rebuild_state_cache("save1")
        stats = es.get_current_stats("save1", "player1")
        assert stats["HP"] == "75"

    def test_get_current_stats_empty_for_unknown_entity(self, db: tuple) -> None:
        """get_current_stats returns {} for an entity with no cached stats."""
        _, es = db
        es.rebuild_state_cache("save1")
        assert es.get_current_stats("save1", "ghost") == {}


# ---------------------------------------------------------------------------
# update_state_cache — incremental sync after a turn (TICKET-002)
# ---------------------------------------------------------------------------

class TestUpdateStateCache:
    """update_state_cache applies a freshly-appended batch on top of the cache
    so DB reads reflect the turn without a full rebuild_state_cache replay."""

    def test_applies_delta_on_top_of_existing_cache(self, db: tuple) -> None:
        _, es = db
        # Establish a baseline cache (as a session load would).
        es.append_event("save1", 1, "stat_change", "player1",
                        {"entity_id": "player1", "stat_key": "HP", "delta": 100})
        es.rebuild_state_cache("save1")
        assert es.get_current_stats("save1", "player1")["HP"] == "100"

        # A new turn appends a stat change but does NOT rebuild.
        batch = [("save1", 2, "stat_change", "player1",
                  {"entity_id": "player1", "stat_key": "HP", "delta": -30})]
        es.append_events_batch(batch)
        es.update_state_cache("save1", batch)

        # State_Cache reflects the turn immediately, no rebuild needed.
        assert es.get_current_stats("save1", "player1")["HP"] == "70"

    def test_handles_chained_deltas_within_one_batch(self, db: tuple) -> None:
        _, es = db
        es.rebuild_state_cache("save1")  # empty baseline
        batch = [
            ("save1", 1, "stat_set", "player1",
             {"entity_id": "player1", "stat_key": "Gold", "value": "50"}),
            ("save1", 1, "stat_change", "player1",
             {"entity_id": "player1", "stat_key": "Gold", "delta": 25}),
        ]
        es.append_events_batch(batch)
        es.update_state_cache("save1", batch)
        assert es.get_current_stats("save1", "player1")["Gold"] == "75"

    def test_ignores_non_stat_events(self, db: tuple) -> None:
        _, es = db
        es.rebuild_state_cache("save1")
        batch = [
            ("save1", 1, "narrative_text", "player",
             {"active": 0, "variants": ["A quiet morning."]}),
            ("save1", 1, "rule_trigger", "player1", {"rule_id": "r1"}),
        ]
        es.append_events_batch(batch)
        es.update_state_cache("save1", batch)  # must not raise
        assert es.get_current_stats("save1", "player1") == {}

    def test_matches_full_rebuild(self, db: tuple) -> None:
        _, es = db
        # Seed turn 1 into the cache.
        es.append_event("save1", 1, "stat_change", "player1",
                        {"entity_id": "player1", "stat_key": "HP", "delta": 100})
        es.append_event("save1", 1, "stat_change", "npc1",
                        {"entity_id": "npc1", "stat_key": "HP", "delta": 40})
        es.rebuild_state_cache("save1")

        # Turn 2: incremental update.
        batch = [
            ("save1", 2, "stat_change", "player1",
             {"entity_id": "player1", "stat_key": "HP", "delta": -25}),
            ("save1", 2, "stat_change", "npc1",
             {"entity_id": "npc1", "stat_key": "HP", "delta": -40}),
        ]
        es.append_events_batch(batch)
        es.update_state_cache("save1", batch)
        incremental = {
            "player1": es.get_current_stats("save1", "player1"),
            "npc1": es.get_current_stats("save1", "npc1"),
        }

        # A full replay must agree with the incremental result.
        es.rebuild_state_cache("save1", force_full=True)
        assert es.get_current_stats("save1", "player1") == incremental["player1"]
        assert es.get_current_stats("save1", "npc1") == incremental["npc1"]
