"""
tests/test_inventory_rewind.py

TICKET-095 — rewind restores the nested inventory from per-turn snapshots
(`Inventory_Snapshots`), `materialize_state` shows it at a past turn, and a
fork takes it at the fork point with container nesting preserved.
"""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from axiom.checkpoint import CheckpointManager
from axiom.events import EventSourcer
from mods.axiom.inventory.inventory import (
    add_item,
    inventory_at,
    list_instances,
    remove_item,
    rollback_inventory,
    snapshot_inventory,
)
from axiom.saves import fork_save, materialize_state
from axiom.schema import create_universe_db, get_connection


def _setup(tmp_path: Path) -> str:
    db_path = str(tmp_path / "universe.db")
    create_universe_db(db_path)
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            "INSERT INTO Saves (save_id, player_name, difficulty, last_updated) "
            "VALUES ('s1', 'Hero', 'Normal', '2026-01-01T00:00:00');"
        )
        conn.execute(
            "INSERT INTO Entities (entity_id, entity_type, name, is_active) "
            "VALUES ('player1', 'player', 'Aria', 1);"
        )
        conn.commit()
    es = EventSourcer(db_path)
    for turn in range(1, 6):
        es.append_event("s1", turn, "narrative_text", "system", {"text": f"turn {turn}"})
    return db_path


def _items(db_path: str) -> dict[str, int]:
    with get_connection(db_path) as conn:
        return {i["item_id"]: i["quantity"] for i in list_instances(conn, "s1")}


def _play(db_path: str, turn: int, fn) -> None:
    """Apply `fn(conn)` as turn `turn`'s inventory changes, then snapshot it."""
    with get_connection(db_path) as conn:
        fn(conn)
        snapshot_inventory(conn, "s1", turn)
        conn.commit()


@pytest.fixture
def db(tmp_path: Path) -> str:
    db_path = _setup(tmp_path)
    _play(db_path, 0, lambda c: None)                                           # empty start
    _play(db_path, 1, lambda c: add_item(c, "s1", "rope", holder_id="player1"))
    _play(db_path, 3, lambda c: add_item(c, "s1", "sword", holder_id="player1"))
    _play(db_path, 5, lambda c: remove_item(c, "s1", item_id="rope",
                                            holder_kind="entity", holder_id="player1"))
    return db_path


class TestRewindInventory:
    def test_item_gained_in_erased_future_is_removed(self, db: str) -> None:
        assert _items(db) == {"sword": 1}
        CheckpointManager(db).rewind("s1", target_turn_id=1)
        assert _items(db) == {"rope": 1}          # sword (turn 3) gone, rope (lost turn 5) back

    def test_rewind_to_turn_zero_empties_inventory(self, db: str) -> None:
        CheckpointManager(db).rewind("s1", target_turn_id=0)
        assert _items(db) == {}

    def test_future_snapshots_are_dropped(self, db: str) -> None:
        CheckpointManager(db).rewind("s1", target_turn_id=3)
        with get_connection(db) as conn:
            assert inventory_at(conn, "s1", 5) is None
            assert inventory_at(conn, "s1", 3) is not None

    def test_legacy_turn_without_snapshot_leaves_inventory(self, tmp_path: Path) -> None:
        """A turn played before snapshots existed: rewind doesn't touch items."""
        db_path = _setup(tmp_path)
        with get_connection(db_path) as conn:
            add_item(conn, "s1", "lamp", holder_id="player1")
            conn.commit()
        CheckpointManager(db_path).rewind("s1", target_turn_id=2)
        assert _items(db_path) == {"lamp": 1}

    def test_rollback_reports_missing_snapshot(self, tmp_path: Path) -> None:
        db_path = _setup(tmp_path)
        with get_connection(db_path) as conn:
            assert rollback_inventory(conn, "s1", 2) is False

    def test_container_contents_survive_rewind(self, tmp_path: Path) -> None:
        db_path = _setup(tmp_path)
        with get_connection(db_path) as conn:
            bag = add_item(conn, "s1", "bag", holder_id="player1", is_container=True)
            add_item(conn, "s1", "coin", quantity=3, holder_kind="instance", holder_id=bag)
            snapshot_inventory(conn, "s1", 1)
            add_item(conn, "s1", "gem", holder_kind="instance", holder_id=bag)
            snapshot_inventory(conn, "s1", 2)
            conn.commit()
        CheckpointManager(db_path).rewind("s1", target_turn_id=1)
        with get_connection(db_path) as conn:
            rows = list_instances(conn, "s1")
        by_item = {r["item_id"]: r for r in rows}
        assert set(by_item) == {"bag", "coin"}
        assert by_item["bag"]["instance_id"] == bag
        assert by_item["coin"]["holder_id"] == bag


class TestMaterializeAndFork:
    def test_materialize_past_turn_uses_snapshot(self, db: str) -> None:
        state = materialize_state(db, "s1", at_turn=1)
        assert {i["item_id"] for i in state["inventory"]} == {"rope"}
        assert state["historical"]["inventory"] is True

    def test_materialize_present_turn_is_live(self, db: str) -> None:
        state = materialize_state(db, "s1")
        assert {i["item_id"] for i in state["inventory"]} == {"sword"}
        assert state["historical"]["inventory"] is True

    def test_materialize_legacy_turn_flags_non_historical(self, tmp_path: Path) -> None:
        db_path = _setup(tmp_path)
        state = materialize_state(db_path, "s1", at_turn=2)
        assert state["historical"]["inventory"] is False

    def test_fork_takes_inventory_at_fork_point_with_nesting(self, tmp_path: Path) -> None:
        db_path = _setup(tmp_path)
        with get_connection(db_path) as conn:
            bag = add_item(conn, "s1", "bag", holder_id="player1", is_container=True)
            add_item(conn, "s1", "coin", holder_kind="instance", holder_id=bag)
            snapshot_inventory(conn, "s1", 2)
            add_item(conn, "s1", "sword", holder_id="player1")      # after the fork point
            snapshot_inventory(conn, "s1", 4)
            conn.commit()

        new_id = fork_save(db_path, "s1", at_turn=2)

        with get_connection(db_path) as conn:
            rows = {r["item_id"]: r for r in list_instances(conn, new_id)}
            assert set(rows) == {"bag", "coin"}                      # no sword
            assert rows["bag"]["instance_id"] != bag                 # fresh ids…
            assert rows["coin"]["holder_id"] == rows["bag"]["instance_id"]  # …nesting kept
            assert inventory_at(conn, new_id, 2) is not None         # rewind works in the fork
            assert inventory_at(conn, new_id, 4) is None
