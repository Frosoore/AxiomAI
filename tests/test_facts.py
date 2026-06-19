"""tests/test_facts.py

Deterministic storage layer for living-mode facts: insert / query / rollback,
and the rewind integration that drops future facts atomically with events.
No LLM, no network.
"""

import tempfile
from pathlib import Path

import pytest

from axiom import facts
from axiom.config import AppConfig, memory_mode_is_living
from axiom.facts import Fact
from axiom.schema import create_universe_db


@pytest.fixture
def db_path() -> str:
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "universe.db")
        create_universe_db(path)
        # A save row is required for the FK (ON DELETE CASCADE) to hold.
        from axiom.schema import get_connection

        with get_connection(path) as conn:
            conn.execute(
                "INSERT INTO Saves (save_id, player_name, difficulty, last_updated) "
                "VALUES (?, ?, ?, ?);",
                ("s1", "Hero", "Normal", "2026-06-18"),
            )
            conn.commit()
        yield path


class TestInsertAndGet:
    def test_insert_returns_ids(self, db_path: str) -> None:
        ids = facts.insert_facts(
            db_path, "s1", 3,
            [Fact(statement="Kael swore an oath", fact_type="experience",
                  who="Kael", entities=["Kael"])],
        )
        assert len(ids) == 1 and ids[0] > 0

    def test_roundtrip_fields(self, db_path: str) -> None:
        facts.insert_facts(
            db_path, "s1", 5,
            [Fact(statement="The bridge collapsed", who="storm", what="collapse",
                  when="dawn", where="Voss", why="flood", entities=["Voss", "bridge"])],
        )
        got = facts.get_facts(db_path, "s1")
        assert len(got) == 1
        f = got[0]
        assert f.statement == "The bridge collapsed"
        assert f.where == "Voss"
        assert f.entities == ["Voss", "bridge"]
        assert f.turn_id == 5

    def test_blank_statements_skipped(self, db_path: str) -> None:
        ids = facts.insert_facts(
            db_path, "s1", 1,
            [Fact(statement="   "), Fact(statement="real fact")],
        )
        assert len(ids) == 1
        assert facts.count_facts(db_path, "s1") == 1

    def test_empty_list_is_noop(self, db_path: str) -> None:
        assert facts.insert_facts(db_path, "s1", 1, []) == []
        assert facts.count_facts(db_path, "s1") == 0

    def test_insert_stamps_id_and_turn_in_place(self, db_path: str) -> None:
        # TICKET-080: the inserted Fact objects carry their new id + turn, so the
        # caller never has to re-align a separate id list. Skipped (blank) facts
        # keep fact_id=None.
        blank = Fact(statement="   ")
        real = Fact(statement="real fact")
        ids = facts.insert_facts(db_path, "s1", 7, [blank, real])
        assert blank.fact_id is None
        assert real.fact_id == ids[0] and real.turn_id == 7

    def test_max_turn_id_filter(self, db_path: str) -> None:
        facts.insert_facts(db_path, "s1", 2, [Fact(statement="early")])
        facts.insert_facts(db_path, "s1", 8, [Fact(statement="late")])
        recent = facts.get_facts(db_path, "s1", max_turn_id=5)
        assert [f.statement for f in recent] == ["early"]

    def test_entity_filter_case_insensitive(self, db_path: str) -> None:
        facts.insert_facts(db_path, "s1", 1, [Fact(statement="a", entities=["Mira"])])
        facts.insert_facts(db_path, "s1", 1, [Fact(statement="b", entities=["Other"])])
        got = facts.get_facts(db_path, "s1", entity="mira")
        assert [f.statement for f in got] == ["a"]

    def test_ordered_recent_first(self, db_path: str) -> None:
        facts.insert_facts(db_path, "s1", 1, [Fact(statement="old")])
        facts.insert_facts(db_path, "s1", 9, [Fact(statement="new")])
        got = facts.get_facts(db_path, "s1")
        assert [f.statement for f in got] == ["new", "old"]

    def test_unknown_fact_type_defaults_world(self, db_path: str) -> None:
        facts.insert_facts(db_path, "s1", 1, [Fact(statement="x", fact_type="bogus")])
        assert facts.get_facts(db_path, "s1")[0].fact_type == "world"


class TestRollback:
    def test_rollback_drops_future_facts(self, db_path: str) -> None:
        for t in (3, 6, 9):
            facts.insert_facts(db_path, "s1", t, [Fact(statement=f"turn {t}")])
        deleted = facts.rollback_facts(db_path, "s1", target_turn_id=5)
        assert deleted == 2
        remaining = facts.get_facts(db_path, "s1")
        assert all(f.turn_id <= 5 for f in remaining)
        assert {f.turn_id for f in remaining} == {3}

    def test_rollback_to_zero_clears_all(self, db_path: str) -> None:
        for t in (1, 2, 3):
            facts.insert_facts(db_path, "s1", t, [Fact(statement=f"t{t}")])
        assert facts.rollback_facts(db_path, "s1", 0) == 3
        assert facts.count_facts(db_path, "s1") == 0

    def test_rewind_deletes_future_facts(self, db_path: str) -> None:
        """CheckpointManager.rewind drops facts > target alongside events."""
        from axiom.checkpoint import CheckpointManager

        for t in (2, 4, 10):
            facts.insert_facts(db_path, "s1", t, [Fact(statement=f"turn {t}")])
        CheckpointManager(db_path).rewind("s1", target_turn_id=5)
        remaining = facts.get_facts(db_path, "s1")
        assert {f.turn_id for f in remaining} == {2, 4}


class TestArbitratorFactInjection:
    """Item 5: living-mode fact selection for the Arbitrator prompt."""

    def _arb(self, db_path: str):
        from axiom.arbitrator import ArbitratorEngine

        return ArbitratorEngine(db_path, [])

    def test_prioritises_on_scene_then_recent_and_bounds_turn(self, db_path: str) -> None:
        facts.insert_facts(db_path, "s1", 2, [Fact(statement="Mira owns the inn", entities=["Mira"])])
        facts.insert_facts(db_path, "s1", 4, [Fact(statement="A storm rolled in")])
        facts.insert_facts(db_path, "s1", 9, [Fact(statement="Mira leaves town", entities=["Mira"])])

        out = self._arb(db_path)._fetch_relevant_facts(
            "s1", max_turn_id=5, on_scene=["Mira"], limit=5
        )
        assert out[0] == "Mira owns the inn"          # on-scene first
        assert "A storm rolled in" in out             # recent filler
        assert "Mira leaves town" not in out          # turn 9 > max_turn_id 5

    def test_dedup_and_limit(self, db_path: str) -> None:
        facts.insert_facts(db_path, "s1", 1, [Fact(statement="Shared", entities=["Mira"])])
        facts.insert_facts(db_path, "s1", 2, [Fact(statement="Extra A")])
        facts.insert_facts(db_path, "s1", 3, [Fact(statement="Extra B")])
        out = self._arb(db_path)._fetch_relevant_facts(
            "s1", max_turn_id=3, on_scene=["Mira"], limit=2
        )
        assert len(out) == 2
        assert out[0] == "Shared"          # on-scene, not duplicated by the recent pass
        assert out.count("Shared") == 1

    def test_empty_when_no_facts(self, db_path: str) -> None:
        assert self._arb(db_path)._fetch_relevant_facts(
            "s1", max_turn_id=10, on_scene=["Mira"], limit=5
        ) == []

    def test_zero_limit_returns_empty(self, db_path: str) -> None:
        facts.insert_facts(db_path, "s1", 1, [Fact(statement="x")])
        assert self._arb(db_path)._fetch_relevant_facts(
            "s1", max_turn_id=10, on_scene=[], limit=0
        ) == []


class TestMemoryModeToggle:
    def test_default_is_lite(self) -> None:
        assert memory_mode_is_living(AppConfig()) is False

    def test_living_opt_in(self) -> None:
        assert memory_mode_is_living(AppConfig(memory_mode="living")) is True

    def test_unknown_value_resolves_lite(self) -> None:
        assert memory_mode_is_living(AppConfig(memory_mode="LIVING ")) is True
        assert memory_mode_is_living(AppConfig(memory_mode="bogus")) is False
