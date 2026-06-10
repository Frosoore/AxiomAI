"""
workers/mini_dico_worker.py

QThread worker for the Mini-Dico (Lore Reference) encyclopedic queries.

Coquille fine (B4) : la logique (RAG save-scopé + prompt encyclopédique +
appel LLM) vit dans `axiom.mini_dico` — ce worker ne fait que déporter l'appel
hors du thread principal (règle : VectorMemory et LLM jamais sur le main
thread) et traduire la réponse en signaux Qt.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from axiom.backends.base import LLMBackend, LLMConnectionError
from axiom.memory import VectorMemory
from axiom.mini_dico import answer_lore_question


class MiniDicoWorker(QThread):
    """Handles a single Mini-Dico lore lookup off the main thread.

    Signals:
        token_received(str):     Response text (full in Phase 3; streamed in Phase 4).
        response_complete(str):  Full lore answer text.
        error_occurred(str):     Human-readable error message.
    """

    token_received = Signal(str)
    response_complete = Signal(str)
    error_occurred = Signal(str)

    def __init__(
        self,
        llm: LLMBackend,
        vector_memory: VectorMemory,
        question: str,
        universe_save_id: str,
        lore_book: list[dict] | None = None,
        global_lore: str | None = None,
        temperature: float = 0.7,
        top_p: float = 1.0,
    ) -> None:
        super().__init__()
        self._llm = llm
        self._vector_memory = vector_memory
        self._question = question
        self._universe_save_id = universe_save_id
        self._lore_book: list[dict] = lore_book or []
        self._global_lore = global_lore
        self._temperature = temperature
        self._top_p = top_p

    def run(self) -> None:
        """Execute the Mini-Dico query pipeline.  Never raises."""
        try:
            answer = answer_lore_question(
                self._llm,
                self._vector_memory,
                self._question,
                self._universe_save_id,
                lore_book=self._lore_book,
                global_lore=self._global_lore,
                temperature=self._temperature,
                top_p=self._top_p,
            )
            # Phase 3: emit full text; Phase 4 upgrades to streaming
            self.token_received.emit(answer)
            self.response_complete.emit(answer)
        except LLMConnectionError as exc:
            self.error_occurred.emit(
                f"LLM unreachable for lore query — check your connection.\n\n{exc}"
            )
        except Exception as exc:
            self.error_occurred.emit(f"Mini-Dico error: {exc}")
