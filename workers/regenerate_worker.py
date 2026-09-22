"""
workers/regenerate_worker.py

QThread worker for narrative variant regeneration.

Coquille fine (B4) : toute la logique vit dans `axiom.regenerate` — ce worker
ne fait que déporter l'appel hors du thread principal et traduire le streaming
et le résultat en signaux Qt.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from axiom.backends.base import LLMBackend
from axiom.regenerate import regenerate_variant


class RegenerateWorker(QThread):
    token_received = Signal(str)
    regenerate_complete = Signal(str)
    error_occurred = Signal(str)
    status_update = Signal(str)

    def __init__(self, llm: LLMBackend, db_path: str, save_id: str, turn_id: int,
                 history: list, system_prompt: str, user_message: str,
                 temperature: float = 0.7, top_p: float = 1.0,
                 verbosity_level: str = "balanced"):
        super().__init__()
        self._llm = llm
        self._db_path = db_path
        self._save_id = save_id
        self._turn_id = turn_id
        self._history = history
        self._system_prompt = system_prompt
        self._user_message = user_message
        self._temperature = temperature
        self._top_p = top_p
        self._verbosity_level = verbosity_level

    def run(self):
        try:
            self.status_update.emit("Generating new variant...")
            narrative_text = regenerate_variant(
                self._llm,
                self._db_path,
                self._save_id,
                self._turn_id,
                self._history,
                system_prompt=self._system_prompt,
                user_message=self._user_message,
                temperature=self._temperature,
                top_p=self._top_p,
                verbosity_level=self._verbosity_level,
                on_token=self.token_received.emit,
            )
            self.regenerate_complete.emit(narrative_text)
        except Exception as exc:
            self.error_occurred.emit(str(exc))
