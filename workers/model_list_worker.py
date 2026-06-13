"""
workers/model_list_worker.py

Lightweight QThread worker that lists the models available on an LLM backend.

Used by the Settings dialog "Browse models" button (TICKET-062). Both
UniversalClient and GeminiClient expose list_models(); any backend without
it yields an empty list.

THREADING RULE: list_models() performs a network call — it MUST NOT run on
the main thread.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from axiom.backends.base import LLMBackend


class ModelListWorker(QThread):
    """Fetches the provider's model list off the main thread.

    Signals:
        models_ready(list): The model ids ([] when none or on any error).
    """

    models_ready = Signal(list)

    def __init__(self, llm: LLMBackend) -> None:
        super().__init__()
        self._llm = llm

    def run(self) -> None:
        """Call list_models() and emit models_ready. Never raises."""
        try:
            list_models = getattr(self._llm, "list_models", None)
            models = list_models() if callable(list_models) else []
        except Exception:
            models = []
        self.models_ready.emit(list(models))
