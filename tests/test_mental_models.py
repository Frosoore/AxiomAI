"""tests/test_mental_models.py

Deterministic mental-model storage layer (§7.8): upsert / query / count, the
stale-subject lookup and the turn-keyed rollback, plus the Arbitrator's selection
of model summaries for the living-mode prompt. No LLM, no network.
"""

import tempfile
from pathlib import Path

import pytest

from axiom import mental_models as mm
from axiom.config import (
    AppConfig,
    memory_beliefs_active,
    memory_mental_models_active,
)
from axiom.mental_models import MentalModel
from axiom.schema import create_universe_db, get_connection


@pytest.fixture
def db_path() -> str:
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "universe.db")
        create_universe_db(path)
        with get_connection(path) as conn:
            conn.execute(
                "INSERT INTO Saves (save_id, player_name, difficulty, last_updated) "
                "VALUES (?, ?, ?, ?);",
                ("s1", "Hero", "Normal", "2026-06-19"),
            )
            conn.commit()
        yield path


class TestUpsertAndGet:
    def test_insert_then_update_in_place(self, db_path: str) -> None:
        mid = mm.upsert_mental_model(db_path, "s1", "Merchant", "Wary of the player.", 4, sources=[1])
        assert mid is not None
        # Same subject → UPDATE in place (created_turn_id preserved, one row only).
        mid2 = mm.upsert_mental_model(db_path, "s1", "Merchant", "Now openly hostile.", 9, sources=[1, 2])
        assert mid2 == mid
        models = mm.get_mental_models(db_path, "s1")
        assert len(models) == 1
        m = models[0]
        assert m.summary == "Now openly hostile."
        assert m.created_turn_id == 4 and m.updated_turn_id == 9
        assert m.stale is False
        assert m.sources == [1, 2]

    def test_blank_summary_skipped(self, db_path: str) -> None:
        assert mm.upsert_mental_model(db_path, "s1", "X", "   ", 1) is None
        assert mm.count_mental_models(db_path, "s1") == 0

    def test_world_model_uses_empty_subject(self, db_path: str) -> None:
        mm.upsert_mental_model(db_path, "s1", "", "The realm is at war.", 3)
        got = mm.get_mental_models(db_path, "s1", subject="")
        assert len(got) == 1 and got[0].subject == ""

    def test_max_turn_bound(self, db_path: str) -> None:
        mm.upsert_mental_model(db_path, "s1", "A", "early", 2)
        mm.upsert_mental_model(db_path, "s1", "B", "late", 12)
        got = mm.get_mental_models(db_path, "s1", max_turn_id=10)
        assert [m.subject for m in got] == ["A"]


class TestRollback:
    def test_drops_models_created_after_target(self, db_path: str) -> None:
        mm.upsert_mental_model(db_path, "s1", "A", "kept", 3)
        mm.upsert_mental_model(db_path, "s1", "B", "future", 8)
        res = mm.rollback_mental_models_standalone(db_path, "s1", 5)
        assert res["deleted"] == 1
        subjects = [m.subject for m in mm.get_mental_models(db_path, "s1")]
        assert subjects == ["A"]

    def test_survivor_refreshed_after_target_is_flagged_stale(self, db_path: str) -> None:
        # created early but last refreshed at turn 9 → rewind to 5 clamps + stales.
        mm.upsert_mental_model(db_path, "s1", "A", "v1", 3)
        mm.upsert_mental_model(db_path, "s1", "A", "v2", 9)
        res = mm.rollback_mental_models_standalone(db_path, "s1", 5)
        assert res["deleted"] == 0 and res["updated"] == 1
        m = mm.get_mental_models(db_path, "s1")[0]
        assert m.stale is True and m.updated_turn_id == 5

    def test_untouched_model_left_alone(self, db_path: str) -> None:
        mm.upsert_mental_model(db_path, "s1", "A", "v1", 3)
        res = mm.rollback_mental_models_standalone(db_path, "s1", 5)
        assert res == {"deleted": 0, "updated": 0}
        assert mm.get_mental_models(db_path, "s1")[0].stale is False


class TestStaleSubjects:
    def test_lists_only_stale_capped_and_bounded(self, db_path: str) -> None:
        mm.upsert_mental_model(db_path, "s1", "A", "a", 3)
        mm.upsert_mental_model(db_path, "s1", "B", "b", 9)
        # Make A stale via a rewind that clamps it.
        mm.upsert_mental_model(db_path, "s1", "A", "a2", 9)
        mm.rollback_mental_models_standalone(db_path, "s1", 5)  # A → stale
        stale = mm.stale_subjects(db_path, "s1", max_turn_id=100)
        assert stale == ["A"]


class TestRewindIntegration:
    def test_rewind_rolls_models_back(self, db_path: str) -> None:
        from axiom.checkpoint import CheckpointManager
        mm.upsert_mental_model(db_path, "s1", "A", "kept", 3)
        mm.upsert_mental_model(db_path, "s1", "B", "future", 8)
        CheckpointManager(db_path).rewind("s1", 5)
        assert [m.subject for m in mm.get_mental_models(db_path, "s1")] == ["A"]


class TestArbitratorModelInjection:
    def _arb(self, db_path: str):
        from axiom.arbitrator import ArbitratorEngine
        return ArbitratorEngine(db_path, [])

    def test_prioritises_on_scene_then_recent_and_bounds_turn(self, db_path: str) -> None:
        mm.upsert_mental_model(db_path, "s1", "Merchant", "Resents the player.", 4)
        mm.upsert_mental_model(db_path, "s1", "", "The city is tense.", 6)
        mm.upsert_mental_model(db_path, "s1", "Guard", "Loyal future profile.", 12)
        lines = self._arb(db_path)._fetch_relevant_mental_models(
            "s1", max_turn_id=10, on_scene=["Merchant"], limit=5)
        assert lines[0] == "Merchant: Resents the player."
        assert "The city is tense." in lines  # world model has no label
        assert all("Loyal future profile." not in s for s in lines)  # turn 12 bound

    def test_empty_when_none(self, db_path: str) -> None:
        assert self._arb(db_path)._fetch_relevant_mental_models(
            "s1", max_turn_id=10, on_scene=["X"], limit=5) == []


class TestConfigGate:
    def test_models_require_beliefs_and_opt_in(self) -> None:
        assert memory_mental_models_active(AppConfig()) is False
        living = AppConfig(memory_mode="living", memory_beliefs_enabled=True)
        assert memory_beliefs_active(living) is True
        assert memory_mental_models_active(living) is False  # model opt-in still off
        full = AppConfig(
            memory_mode="living",
            memory_beliefs_enabled=True,
            memory_mental_models_enabled=True,
        )
        assert memory_mental_models_active(full) is True
        # Never fires without beliefs, even if the model flag is on.
        no_beliefs = AppConfig(memory_mode="living", memory_mental_models_enabled=True)
        assert memory_mental_models_active(no_beliefs) is False
