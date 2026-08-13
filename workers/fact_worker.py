"""
workers/fact_worker.py

QThread shell around ``axiom.living_memory.distil_narrative_to_memory``.

THREADING RULE: the LLM extraction call is blocking and MUST NOT run on the
main thread. The view builds the (cheap, network-free) LLM object and the text
slice, then hands them here; ``run()`` does the costly work off the UI thread.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from axiom.backends.base import LLMBackend
from axiom.living_memory import distil_narrative_to_memory


class FactExtractWorker(QThread):
    """Extracts facts from a narrative slice and persists them.

    Signals:
        facts_extracted(int): Number of facts stored this run (0 is normal).
        error_occurred(str):  Human-readable error message (storage failure).
        status_update(str):   Short status for the QStatusBar.
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
        self._consolidate_beliefs = consolidate_beliefs
        self._refresh_mental_models = refresh_mental_models

    def run(self) -> None:
        """Extract then store. Never raises (background, non-blocking)."""
        try:
            self.status_update.emit("Distilling memory...")
            result = distil_narrative_to_memory(
                self._llm,
                self._db_path,
                self._save_id,
                self._turn_id,
                self._narrative_text,
                known_entities=self._known_entities,
                when_hint=self._when_hint,
                max_facts=self._max_facts,
                consolidate_beliefs=self._consolidate_beliefs,
                refresh_mental_models=self._refresh_mental_models,
            )
            # Signal still carries fact count (GUI status string); dict is new.
            n = (
                int(result.get("facts_stored", 0))
                if isinstance(result, dict)
                else int(result or 0)
            )
            self.facts_extracted.emit(n)
        except Exception as exc:
            self.error_occurred.emit(f"Fact extraction failed: {exc}")
