"""
workers/narrative_worker.py

QThread shell around the headless engine's `Session.take_turn()` (Pilier 1, Étape 7).

The worker no longer drives the Arbitrator directly: it is a pure threading
*coquille* that runs `Session.take_turn()` off the main thread and re-emits the
session's progress callbacks as Qt signals.  All engine logic — Companion hero
decision, history reconstruction from the Event_Log, prompt building, LLM calls,
SQLite writes and VectorMemory embedding — now lives in `axiom.Session`, the
single turn machine shared by the GUI and the (headless) CLI.

THREADING RULE: ALL LLM calls, ALL SQLite writes, and ALL VectorMemory
embedding that occur during a turn happen here — inside `Session.take_turn`,
executed on this thread — never on the main thread.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from axiom.backends.base import LLMConnectionError
from axiom.session import Session


class NarrativeWorker(QThread):
    """Runs one complete `Session` turn off the main thread.

    The signal contract with the GUI is unchanged from the pre-Étape-7 worker,
    so `ui/tabletop_view.py` keeps the same connections.

    Signals:
        token_received(str):         Streamed narrative tokens (on_token).
        hero_decision_received(str): Companion Hero's decided action (on_hero_decision).
        turn_complete(object):       The ArbitratorResult dataclass instance.
        error_occurred(str):         Human-readable error string.
        status_update(str):          Short message for QStatusBar (on_status).
    """

    token_received = Signal(str)
    hero_decision_received = Signal(str)
    turn_complete = Signal(object)
    error_occurred = Signal(str)
    status_update = Signal(str)

    def __init__(
        self,
        session: Session,
        action: object,  # PlayerAction (.text, .player_id) — solo/Companion
        *,
        intents: dict[str, str] | None = None,  # Multiplayer: {player_id: text}
        temperature: float = 0.7,
        top_p: float = 1.0,
        verbosity: str = "balanced",
    ) -> None:
        super().__init__()
        self._session = session
        self._action = action
        self._intents = intents
        self._temperature = temperature
        self._top_p = top_p
        self._verbosity = verbosity

    def run(self) -> None:
        """Execute one Session turn.  Never raises.

        Solo/Companion: `Session.take_turn` decides the Companion hero action
        (when in Companion mode), rebuilds history from the Event_Log, streams
        tokens and emits its own "Ready." status. Multiplayer (`intents` given):
        `Session.take_turn_multiplayer` resolves every player's intent in a
        single simultaneous tick. We forward callbacks to Qt signals either way.
        """
        try:
            if self._intents is not None:
                result = self._session.take_turn_multiplayer(
                    self._intents,
                    on_token=self.token_received.emit,
                    on_status=self.status_update.emit,
                    temperature=self._temperature,
                    top_p=self._top_p,
                    verbosity_level=self._verbosity,
                )
            else:
                result = self._session.take_turn(
                    self._action.text,
                    player_id=self._action.player_id,
                    on_token=self.token_received.emit,
                    on_status=self.status_update.emit,
                    on_hero_decision=self.hero_decision_received.emit,
                    temperature=self._temperature,
                    top_p=self._top_p,
                    verbosity_level=self._verbosity,
                )
            self.turn_complete.emit(result)

        except LLMConnectionError as exc:
            self.error_occurred.emit(
                f"LLM unreachable — check your Ollama server or API key.\n\n{exc}"
            )
            self.status_update.emit("LLM connection error.")
        except Exception as exc:
            self.error_occurred.emit(f"Unexpected error during turn: {exc}")
            self.status_update.emit("Error.")
