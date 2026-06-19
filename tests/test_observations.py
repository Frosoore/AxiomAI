"""tests/test_observations.py

Deterministic belief-storage layer (Phase 3): insert / query / count and the
turn-keyed rollback — including the acceptance test (beliefs over many turns,
rewind, only the surviving sources remain). No LLM, no network.
"""

import tempfile
from pathlib import Path

import pytest

from axiom import observations
from axiom.config import AppConfig, memory_beliefs_active, memory_mode_is_living
from axiom.observations import Observation
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
                ("s1", "Hero", "Normal", "2026-06-18"),
            )
            conn.commit()
        yield path


def _src(fact_id: int, turn_id: int) -> dict:
    return {"fact_id": fact_id, "turn_id": turn_id}


class TestInsertAndGet:
    def test_insert_returns_id(self, db_path: str) -> None:
        oid = observations.insert_observation(
            db_path, "s1",
            Observation(statement="The merchant distrusts the player", subject="Merchant",
                        sources=[_src(1, 3)], created_turn_id=3, updated_turn_id=3),
        )
        assert isinstance(oid, int) and oid > 0
        assert observations.count_observations(db_path, "s1") == 1

    def test_blank_statement_skipped(self, db_path: str) -> None:
        assert observations.insert_observation(db_path, "s1", Observation(statement="  ")) is None
        assert observations.count_observations(db_path, "s1") == 0

    def test_roundtrip_and_proof_count(self, db_path: str) -> None:
        observations.insert_observation(
            db_path, "s1",
            Observation(statement="Kael is hunted", subject="Kael",
                        sources=[_src(1, 5), _src(2, 8)], created_turn_id=5, updated_turn_id=8),
        )
        got = observations.get_observations(db_path, "s1")
        assert len(got) == 1
        o = got[0]
        assert o.statement == "Kael is hunted"
        assert o.proof_count == 2          # derived from sources
        assert {s["turn_id"] for s in o.sources} == {5, 8}

    def test_subject_filter_and_max_turn(self, db_path: str) -> None:
        observations.insert_observation(db_path, "s1", Observation(
            statement="World grows tense", subject="", sources=[_src(1, 2)],
            created_turn_id=2, updated_turn_id=2))
        observations.insert_observation(db_path, "s1", Observation(
            statement="Merchant holds a grudge", subject="Merchant", sources=[_src(2, 9)],
            created_turn_id=9, updated_turn_id=9))
        assert len(observations.get_observations(db_path, "s1", subject="Merchant")) == 1
        assert len(observations.get_observations(db_path, "s1", subject="")) == 1
        # created_turn_id bound excludes the turn-9 belief
        assert len(observations.get_observations(db_path, "s1", max_turn_id=5)) == 1


class TestRollback:
    def test_drops_beliefs_created_after_target(self, db_path: str) -> None:
        observations.insert_observation(db_path, "s1", Observation(
            statement="early belief", sources=[_src(1, 3)], created_turn_id=3, updated_turn_id=3))
        observations.insert_observation(db_path, "s1", Observation(
            statement="late belief", sources=[_src(2, 15)], created_turn_id=15, updated_turn_id=15))
        res = observations.rollback_observations_standalone(db_path, "s1", target_turn_id=10)
        assert res["deleted"] == 1
        remaining = observations.get_observations(db_path, "s1")
        assert [o.statement for o in remaining] == ["early belief"]

    def test_recomputes_proof_from_surviving_sources(self, db_path: str) -> None:
        # A belief created at turn 4, later reinforced by facts at turns 7 and 12.
        observations.insert_observation(db_path, "s1", Observation(
            statement="Merchant resents the player", subject="Merchant",
            sources=[_src(1, 4), _src(2, 7), _src(3, 12)],
            created_turn_id=4, updated_turn_id=12))
        observations.rollback_observations_standalone(db_path, "s1", target_turn_id=8)
        o = observations.get_observations(db_path, "s1")[0]
        assert {s["turn_id"] for s in o.sources} == {4, 7}   # turn-12 source dropped
        assert o.proof_count == 2
        assert o.updated_turn_id <= 8
        assert o.stale is True

    def test_acceptance_rewind_reflects_only_past(self, db_path: str) -> None:
        """Beliefs distilled across 20 turns; rewind to 10 → state reflects ≤ 10."""
        for t in range(1, 21):
            observations.insert_observation(db_path, "s1", Observation(
                statement=f"belief from turn {t}", sources=[_src(t, t)],
                created_turn_id=t, updated_turn_id=t))
        # A cross-turn belief spanning the boundary (created early, updated late).
        observations.insert_observation(db_path, "s1", Observation(
            statement="long-running grudge", subject="Merchant",
            sources=[_src(100, 6), _src(101, 18)], created_turn_id=6, updated_turn_id=18))

        observations.rollback_observations_standalone(db_path, "s1", target_turn_id=10)
        survivors = observations.get_observations(db_path, "s1")
        # Every surviving belief was created at a turn <= 10...
        assert all(o.created_turn_id <= 10 for o in survivors)
        # ...and no surviving source comes from a turn > 10.
        assert all(s["turn_id"] <= 10 for o in survivors for s in o.sources)
        # The cross-turn grudge survived but lost its turn-18 source.
        grudge = [o for o in survivors if o.statement == "long-running grudge"]
        assert len(grudge) == 1 and grudge[0].proof_count == 1


class TestRewindIntegration:
    def test_checkpoint_rewind_rolls_back_beliefs(self, db_path: str) -> None:
        """CheckpointManager.rewind rolls beliefs back atomically with events."""
        from axiom.checkpoint import CheckpointManager
        # Minimal event so rewind has something to delete and a turn to rebuild to.
        with get_connection(db_path) as conn:
            conn.execute(
                "INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) "
                "VALUES (?, ?, ?, ?, ?);",
                ("s1", 12, "narrative_text", "system", "{}"))
            conn.commit()
        observations.insert_observation(db_path, "s1", Observation(
            statement="belief after target", sources=[_src(1, 12)],
            created_turn_id=12, updated_turn_id=12))
        observations.insert_observation(db_path, "s1", Observation(
            statement="belief before target", sources=[_src(2, 4)],
            created_turn_id=4, updated_turn_id=4))

        CheckpointManager(db_path).rewind("s1", target_turn_id=8)
        remaining = [o.statement for o in observations.get_observations(db_path, "s1")]
        assert remaining == ["belief before target"]


class TestArbitratorBeliefInjection:
    """Item 3: living-mode belief selection for the Arbitrator prompt."""

    def _arb(self, db_path: str):
        from axiom.arbitrator import ArbitratorEngine
        return ArbitratorEngine(db_path, [])

    def test_prioritises_on_scene_then_recent_and_bounds_turn(self, db_path: str) -> None:
        observations.insert_observation(db_path, "s1", Observation(
            statement="Merchant resents the player", subject="Merchant",
            sources=[_src(1, 4)], created_turn_id=4, updated_turn_id=4))
        observations.insert_observation(db_path, "s1", Observation(
            statement="The city is on edge", subject="", sources=[_src(2, 6)],
            created_turn_id=6, updated_turn_id=6))
        observations.insert_observation(db_path, "s1", Observation(
            statement="future belief", subject="Merchant", sources=[_src(3, 12)],
            created_turn_id=12, updated_turn_id=12))

        arb = self._arb(db_path)
        lines = arb._fetch_relevant_beliefs(
            "s1", max_turn_id=10, on_scene=["Merchant"], limit=5)
        # On-scene subject first; future (turn 12) belief excluded by the bound.
        assert lines[0] == "Merchant resents the player"
        assert "The city is on edge" in lines
        assert "future belief" not in lines

    def test_empty_when_no_beliefs(self, db_path: str) -> None:
        assert self._arb(db_path)._fetch_relevant_beliefs(
            "s1", max_turn_id=10, on_scene=["Merchant"], limit=5) == []

    def test_annotates_directional_trend(self, db_path: str) -> None:
        # A belief whose only evidence is far in the past → stale at turn 100.
        observations.insert_observation(db_path, "s1", Observation(
            statement="An old debt to the smith", subject="Smith",
            sources=[_src(1, 5)], created_turn_id=5, updated_turn_id=5))
        lines = self._arb(db_path)._fetch_relevant_beliefs(
            "s1", max_turn_id=100, on_scene=["Smith"], limit=5)
        assert lines == ["An old debt to the smith (stale)"]


class TestConfigGate:
    def test_beliefs_require_living_and_opt_in(self) -> None:
        assert memory_beliefs_active(AppConfig()) is False  # lite default
        living = AppConfig(memory_mode="living")
        assert memory_mode_is_living(living) is True
        assert memory_beliefs_active(living) is False       # opt-in still off
        on = AppConfig(memory_mode="living", memory_beliefs_enabled=True)
        assert memory_beliefs_active(on) is True
        # Beliefs never fire in lite even if the flag is set.
        assert memory_beliefs_active(AppConfig(memory_beliefs_enabled=True)) is False


# ----------------------------------------------------------- compute_trend (081)

class TestComputeTrend:
    def test_no_sources_or_no_now_is_stable(self) -> None:
        from axiom.observations import compute_trend, TREND_STABLE
        assert compute_trend([], now_turn=100) == TREND_STABLE
        assert compute_trend([5, 6], now_turn=None) == TREND_STABLE

    def test_all_recent_is_new(self) -> None:
        from axiom.observations import compute_trend, TREND_NEW
        # now=100, recent window = last 15 turns → all sources in [86, 100].
        assert compute_trend([95, 98, 100], now_turn=100) == TREND_NEW

    def test_no_recent_is_stale(self) -> None:
        from axiom.observations import compute_trend, TREND_STALE
        # All sources older than the recent cutoff (100 - 15 = 85).
        assert compute_trend([10, 30, 50], now_turn=100) == TREND_STALE

    def test_denser_recent_is_strengthening(self) -> None:
        from axiom.observations import compute_trend, TREND_STRENGTHENING
        # now=100: recent=[90..100] dense (4), older band sparse (1 at turn 60).
        trend = compute_trend([60, 90, 95, 98, 100], now_turn=100)
        assert trend == TREND_STRENGTHENING

    def test_sparser_recent_is_weakening(self) -> None:
        from axiom.observations import compute_trend, TREND_WEAKENING
        # Many old sources, a single faint recent one → fading.
        trend = compute_trend([50, 52, 54, 56, 58, 60, 95], now_turn=100)
        assert trend == TREND_WEAKENING

    def test_observation_method_uses_sources(self) -> None:
        from axiom.observations import Observation, TREND_STALE
        o = Observation(statement="An old grudge",
                        sources=[{"fact_id": 1, "turn_id": 5}])
        assert o.trend(now_turn=100) == TREND_STALE
        assert o.trend(now_turn=8) != TREND_STALE  # fresh when "now" is near
