"""
workers/fact_worker.py

QThread worker that distils a slice of narrative into structured facts and
stores them (living memory mode, Phase 2 item 4).

THREADING RULE: the LLM extraction call is blocking and MUST NOT run on the
main thread. The view builds the (cheap, network-free) LLM object and the text
slice, then hands them here; ``run()`` does the costly ``extract_facts`` +
``insert_facts`` off the UI thread.

Fire-and-forget: ``extract_facts`` already degrades to ``[]`` on any backend
failure, so a missing key / unreachable provider simply yields no facts — the
game keeps running and nothing pops up.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from axiom.backends.base import LLMBackend
from axiom.consolidate import consolidate
from axiom.factextract import extract_facts
from axiom.facts import insert_facts
from axiom.observations import apply_consolidation, get_observations

# Cap on how many subjects get a (costly LLM) mental-model refresh in one pass, so
# a turn that touches many beliefs never fans out into a burst of LLM calls.
_MAX_MODEL_REFRESH = 3


class FactExtractWorker(QThread):
    """Extracts facts from a narrative slice and persists them.

    Signals:
        facts_extracted(int): Number of facts stored this run (0 is normal).
        error_occurred(str):  Human-readable error message (storage failure).
        status_update(str):   Short status for the QStatusBar.

    Args:
        llm:            The backend used for extraction (already built).
        db_path:        Save database path.
        save_id:        The active save.
        turn_id:        Turn the extracted facts are tagged with (rollback key).
        narrative_text: The prose to distil (one or more turns concatenated).
        known_entities: Entity names to prefer for spelling (may be empty).
        when_hint:      In-game time string used for the facts' "when".
        max_facts:      Cap on facts produced this run.
    """

    facts_extracted = Signal(int)
    error_occurred = Signal(str)
    status_update = Signal(str)

    def __init__(
        self,
        llm: LLMBackend,
        db_path: str,
        save_id: str,
        turn_id: int,
        narrative_text: str,
        known_entities: list[str] | None = None,
        when_hint: str | None = None,
        max_facts: int = 8,
        consolidate_beliefs: bool = False,
        refresh_mental_models: bool = False,
    ) -> None:
        super().__init__()
        self._llm = llm
        self._db_path = db_path
        self._save_id = save_id
        self._turn_id = turn_id
        self._narrative_text = narrative_text
        self._known_entities = known_entities or []
        self._when_hint = when_hint
        self._max_facts = max_facts
        # Phase 3: also consolidate the new facts into evolving beliefs.
        self._consolidate_beliefs = consolidate_beliefs
        # §7.8: also refresh the curated mental models for changed subjects.
        self._refresh_mental_models = refresh_mental_models

    def run(self) -> None:
        """Extract then store. Never raises (background, non-blocking)."""
        try:
            self.status_update.emit("Distilling memory...")
            facts = extract_facts(
                self._llm,
                self._narrative_text,
                known_entities=self._known_entities,
                when_hint=self._when_hint,
                max_facts=self._max_facts,
            )
            if not facts:
                self.facts_extracted.emit(0)
                return
            new_ids = insert_facts(self._db_path, self._save_id, self._turn_id, facts)
            self.facts_extracted.emit(len(new_ids))
            if self._consolidate_beliefs and new_ids:
                self._run_consolidation(facts)
        except Exception as exc:  # storage failure — keep the game running
            self.error_occurred.emit(f"Fact extraction failed: {exc}")

    def _run_consolidation(self, facts) -> None:
        """Distil the just-stored facts into evolving beliefs (Phase 3).

        Best-effort and isolated: a consolidation failure must not undo the
        facts already stored nor break the turn.
        """
        try:
            # insert_facts stamped fact_id/turn_id in place on every fact it
            # actually wrote (skipped/blank ones keep fact_id=None), so the
            # consolidator only ever cites real, stored sources.
            stored = [f for f in facts if f.fact_id is not None]
            if not stored:
                return
            # get_observations returns most-recently-updated first; consolidate()
            # scopes this to the beliefs relevant to the batch + recent, capped,
            # so the LLM prompt stays bounded on long campaigns (TICKET-077).
            existing = get_observations(
                self._db_path, self._save_id, max_turn_id=self._turn_id
            )
            # B-3: each character remembers in its own style (universe default +
            # per-entity overrides), read from Universe_Meta.
            from axiom.missions import get_universe_mission, get_belief_missions
            mission = get_universe_mission(self._db_path) or None
            missions = get_belief_missions(self._db_path)
            actions = consolidate(
                self._llm, stored, existing, mission=mission, missions=missions
            )
            if not actions:
                return
            fact_turn_map = {int(f.fact_id): self._turn_id for f in stored}
            apply_consolidation(
                self._db_path, self._save_id, self._turn_id, actions, fact_turn_map
            )
            # §7.8: refresh the curated mental models of the subjects whose beliefs
            # just changed (isolated so a refresh failure never touches the beliefs).
            if self._refresh_mental_models:
                self._do_refresh_models(actions, mission)
        except Exception as exc:
            self.error_occurred.emit(f"Belief consolidation failed: {exc}")

    def _do_refresh_models(self, actions, mission) -> None:
        """Regenerate mental models for the changed subjects (+ any stale ones).

        Bounded per pass and best-effort: a reflection failure is swallowed (the
        existing profile simply isn't refreshed this turn).
        """
        try:
            from axiom.mental_models import stale_subjects, upsert_mental_model
            from axiom.observations import get_observations
            from axiom.reflect import affected_subjects, reflect

            subjects = affected_subjects(actions)
            seen = {s.strip().lower() for s in subjects}
            # Also regenerate models a rewind left stale, even if their beliefs
            # didn't change this pass.
            for s in stale_subjects(
                self._db_path, self._save_id, max_turn_id=self._turn_id
            ):
                if s.strip().lower() not in seen:
                    subjects.append(s)
                    seen.add(s.strip().lower())

            for subj in subjects[:_MAX_MODEL_REFRESH]:
                beliefs = get_observations(
                    self._db_path, self._save_id,
                    subject=subj, max_turn_id=self._turn_id,
                )
                summary = reflect(self._llm, subj, beliefs, mission=mission)
                if not summary:
                    continue
                src = [o.observation_id for o in beliefs if o.observation_id is not None]
                upsert_mental_model(
                    self._db_path, self._save_id, subj, summary,
                    self._turn_id, sources=src,
                )
        except Exception as exc:
            self.error_occurred.emit(f"Mental model refresh failed: {exc}")
