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
                self._run_consolidation(facts, new_ids)
        except Exception as exc:  # storage failure — keep the game running
            self.error_occurred.emit(f"Fact extraction failed: {exc}")

    def _run_consolidation(self, facts, new_ids) -> None:
        """Distil the just-stored facts into evolving beliefs (Phase 3).

        Best-effort and isolated: a consolidation failure must not undo the
        facts already stored nor break the turn.
        """
        try:
            # insert_facts skips blank statements; extract_facts already dropped
            # those, so ids line up with the facts in order. Tag each fact with
            # its new id + this turn so the consolidator can cite real sources.
            stored = []
            for fact, fid in zip(facts, new_ids):
                fact.fact_id = fid
                fact.turn_id = self._turn_id
                stored.append(fact)
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
        except Exception as exc:
            self.error_occurred.emit(f"Belief consolidation failed: {exc}")
