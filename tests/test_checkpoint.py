"""
tests/test_checkpoint.py

Unit tests for database/checkpoint.py — verifies rewind correctness,
checkpoint listing, and Hardcore save deletion.
"""

import sqlite3
from pathlib import Path

import pytest

from axiom.schema import create_universe_db
from axiom.events import EventSourcer
from axiom.checkpoint import CheckpointManager
from axiom.modifiers import ModifierProcessor


# ---------------------------------------------------------------------------
# Helpers & Fixtures
# ---------------------------------------------------------------------------

def _setup_db(tmp_path: Path) -> tuple[str, EventSourcer, CheckpointManager]:
    db_path = str(tmp_path / "universe.db")
    create_universe_db(db_path)

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
        conn.commit()

    es = EventSourcer(db_path)
    cm = CheckpointManager(db_path)
    return db_path, es, cm


def _append_hp_events(es: EventSourcer, save_id: str, turns: int, delta: float = 10) -> None:
    """Append one stat_change event per turn (HP +=delta)."""
    for turn in range(1, turns + 1):
        es.append_event(
            save_id, turn, "stat_change", "player1",
            {"entity_id": "player1", "stat_key": "HP", "delta": delta},
        )


@pytest.fixture
def ctx(tmp_path: Path) -> tuple[str, EventSourcer, CheckpointManager]:
    return _setup_db(tmp_path)


# ---------------------------------------------------------------------------
# rewind
# ---------------------------------------------------------------------------

class TestRewind:
    def test_events_after_target_deleted(self, ctx: tuple) -> None:
        """Rewinding to turn N deletes every event with turn_id > N."""
        db_path, es, cm = ctx
        _append_hp_events(es, "save1", turns=10)

        cm.rewind("save1", target_turn_id=5)

        remaining = es.get_events("save1")
        assert all(ev["turn_id"] <= 5 for ev in remaining), (
            "Events with turn_id > 5 must be deleted"
        )

    def test_events_at_target_preserved(self, ctx: tuple) -> None:
        """Rewinding to turn N keeps all events with turn_id <= N."""
        db_path, es, cm = ctx
        _append_hp_events(es, "save1", turns=10)

        cm.rewind("save1", target_turn_id=5)

        remaining = es.get_events("save1")
        assert len(remaining) == 5

    def test_state_cache_reflects_rewound_state(self, ctx: tuple) -> None:
        """After a rewind the State_Cache is rebuilt to the target turn's values
        (HP=50 at turn 5)."""
        db_path, es, cm = ctx
        # Each turn adds 10 HP → after turn 5 HP=50, after turn 10 HP=100
        _append_hp_events(es, "save1", turns=10, delta=10)
        # Build the cache fully first
        es.rebuild_state_cache("save1")

        cm.rewind("save1", target_turn_id=5)

        stats = es.get_current_stats("save1", "player1")
        assert stats.get("HP") == "50"

    def test_summary_dict_structure(self, ctx: tuple) -> None:
        """rewind returns a summary with deleted_events and rebuilt_to_turn."""
        db_path, es, cm = ctx
        _append_hp_events(es, "save1", turns=10)

        result = cm.rewind("save1", target_turn_id=3)

        assert result["deleted_events"] == 7
        assert result["rebuilt_to_turn"] == 3

    def test_rewind_to_zero_clears_cache(self, ctx: tuple) -> None:
        """Rewinding to turn 0 removes all events and empties the State_Cache."""
        db_path, es, cm = ctx
        _append_hp_events(es, "save1", turns=5)

        cm.rewind("save1", target_turn_id=0)

        assert es.get_events("save1") == []
        stats = es.get_current_stats("save1", "player1")
        assert stats == {}

    def test_rewind_beyond_last_turn_is_noop(self, ctx: tuple) -> None:
        """Rewinding past the latest turn deletes nothing and keeps all events."""
        db_path, es, cm = ctx
        _append_hp_events(es, "save1", turns=5)

        result = cm.rewind("save1", target_turn_id=100)

        assert result["deleted_events"] == 0
        assert len(es.get_events("save1")) == 5


class TestRewindRestoresModifiers:
    """TICKET-074: rewind restores temporary modifiers to their end-of-turn-N
    state from the per-turn snapshot (they decay in minutes and aren't
    event-sourced, so they can't be replayed)."""

    def test_restores_decayed_state_at_target_turn(self, ctx: tuple) -> None:
        db_path, es, cm = ctx
        _append_hp_events(es, "save1", turns=10)
        mp = ModifierProcessor(db_path)
        mid = mp.add_modifier("save1", "player1", "HP", 5.0, minutes=60)
        mp.snapshot_modifiers("save1", 3)               # turn 3: 60 min remaining
        mp.tick_modifiers("save1", elapsed_minutes=10)  # decays to 50 min
        mp.snapshot_modifiers("save1", 5)               # turn 5: 50 min remaining

        cm.rewind("save1", target_turn_id=3)

        mods = mp._fetch_modifiers("save1", "player1")
        assert len(mods) == 1
        assert mods[0]["modifier_id"] == mid
        assert mods[0]["minutes_remaining"] == 60       # restored to turn-3 value

    def test_modifier_absent_at_target_is_cleared(self, ctx: tuple) -> None:
        """A modifier only present on turns after the target is removed by rewind
        (no snapshot at the target turn ⇒ no modifiers then)."""
        db_path, es, cm = ctx
        _append_hp_events(es, "save1", turns=10)
        mp = ModifierProcessor(db_path)
        mp.add_modifier("save1", "player1", "HP", 5.0, minutes=60)
        mp.snapshot_modifiers("save1", 7)               # only captured from turn 7

        cm.rewind("save1", target_turn_id=4)            # no snapshot at turn 4

        assert mp._fetch_modifiers("save1", "player1") == []

    def test_future_snapshot_rows_are_dropped(self, ctx: tuple) -> None:
        """Snapshot rows for turns after the target are purged so they can't leak
        back if the same turns are replayed."""
        db_path, es, cm = ctx
        _append_hp_events(es, "save1", turns=10)
        mp = ModifierProcessor(db_path)
        mp.add_modifier("save1", "player1", "HP", 5.0, minutes=60)
        mp.snapshot_modifiers("save1", 3)
        mp.snapshot_modifiers("save1", 8)

        cm.rewind("save1", target_turn_id=5)

        with sqlite3.connect(db_path) as conn:
            turns = {r[0] for r in conn.execute(
                "SELECT turn_id FROM Modifier_Snapshots WHERE save_id='save1';"
            ).fetchall()}
        assert turns == {3}   # turn 8 dropped, turn 3 kept


class TestRewindUnfiresScheduledEvents:
    """TICKET-075: a scheduled event fired *after* the target turn is un-fired by
    rewind so it can trigger again; one fired at/before the target is kept, and a
    legacy row with no recorded turn is conservatively kept fired."""

    def _add_event(self, db_path: str, event_id: str, minute: int) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO Scheduled_Events (event_id, trigger_minute, title, description) "
                "VALUES (?, ?, ?, ?);",
                (event_id, minute, "Title", "Desc"),
            )
            conn.commit()

    def _fire(self, db_path: str, event_id: str, turn: int) -> None:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO Fired_Scheduled_Events (save_id, event_id, fired_turn_id) "
                "VALUES (?, ?, ?);",
                ("save1", event_id, turn),
            )
            conn.commit()

    def _fired_ids(self, db_path: str) -> set:
        with sqlite3.connect(db_path) as conn:
            return {
                r[0] for r in conn.execute(
                    "SELECT event_id FROM Fired_Scheduled_Events WHERE save_id = 'save1';"
                ).fetchall()
            }

    def test_event_fired_after_target_is_unfired(self, ctx: tuple) -> None:
        db_path, es, cm = ctx
        _append_hp_events(es, "save1", turns=10)
        self._add_event(db_path, "ev_future", 500)
        self._add_event(db_path, "ev_past", 100)
        self._fire(db_path, "ev_future", turn=8)  # fired after the target
        self._fire(db_path, "ev_past", turn=3)    # fired before the target

        cm.rewind("save1", target_turn_id=5)

        fired = self._fired_ids(db_path)
        assert "ev_future" not in fired  # un-fired → can trigger again
        assert "ev_past" in fired         # kept

    def test_legacy_row_without_turn_is_kept(self, ctx: tuple) -> None:
        """A row fired before the column existed (fired_turn_id defaults to 0) is
        conservatively kept across a rewind to any non-negative turn."""
        db_path, es, cm = ctx
        _append_hp_events(es, "save1", turns=10)
        self._add_event(db_path, "ev_legacy", 100)
        with sqlite3.connect(db_path) as conn:  # omit fired_turn_id → default 0
            conn.execute(
                "INSERT INTO Fired_Scheduled_Events (save_id, event_id) VALUES (?, ?);",
                ("save1", "ev_legacy"),
            )
            conn.commit()

        cm.rewind("save1", target_turn_id=5)

        assert "ev_legacy" in self._fired_ids(db_path)


# ---------------------------------------------------------------------------
# list_checkpoints
# ---------------------------------------------------------------------------

class TestListCheckpoints:
    def test_returns_sorted_unique_turns(self, ctx: tuple) -> None:
        """list_checkpoints returns the distinct turn ids in ascending order."""
        db_path, es, cm = ctx
        for turn in [3, 1, 2, 3, 1]:  # duplicates intentional
            es.append_event("save1", turn, "dialogue", "player1", {"text": "hi"})

        checkpoints = cm.list_checkpoints("save1")
        assert checkpoints == [1, 2, 3]

    def test_empty_for_no_events(self, ctx: tuple) -> None:
        """A save with no events has no checkpoints."""
        db_path, es, cm = ctx
        assert cm.list_checkpoints("save1") == []

    def test_empty_for_unknown_save(self, ctx: tuple) -> None:
        """An unknown save id yields an empty checkpoint list."""
        db_path, es, cm = ctx
        assert cm.list_checkpoints("ghost_save") == []

    def test_list_after_rewind_reflects_deletion(self, ctx: tuple) -> None:
        """After a rewind, checkpoints beyond the target turn are gone."""
        db_path, es, cm = ctx
        _append_hp_events(es, "save1", turns=10)

        cm.rewind("save1", target_turn_id=5)
        checkpoints = cm.list_checkpoints("save1")

        assert max(checkpoints) == 5
        assert 6 not in checkpoints


# ---------------------------------------------------------------------------
# delete_save (Hardcore mode)
# ---------------------------------------------------------------------------

class TestDeleteSave:
    def test_deletes_directory(self, ctx: tuple, tmp_path: Path) -> None:
        """delete_save removes the save's universe directory from disk."""
        db_path, es, cm = ctx
        universe_dir = tmp_path / "my_universe"
        universe_dir.mkdir()
        (universe_dir / "some_file.txt").write_text("data")

        cm.delete_save("save1", str(universe_dir))

        assert not universe_dir.exists()

    def test_removes_save_from_db(self, ctx: tuple, tmp_path: Path) -> None:
        """delete_save removes the save row from the database."""
        db_path, es, cm = ctx
        universe_dir = tmp_path / "my_universe"
        universe_dir.mkdir()

        cm.delete_save("save1", str(universe_dir))

        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT * FROM Saves WHERE save_id = 'save1';").fetchone()
        assert row is None

    def test_succeeds_even_if_dir_not_found(self, ctx: tuple) -> None:
        """A missing universe directory doesn't raise; the DB row is still removed."""
        db_path, es, cm = ctx
        # Should not raise FileNotFoundError, but should still delete from DB
        cm.delete_save("save1", "/nonexistent/path/universe")
        
        with sqlite3.connect(db_path) as conn:
            row = conn.execute("SELECT * FROM Saves WHERE save_id = 'save1';").fetchone()
        assert row is None
