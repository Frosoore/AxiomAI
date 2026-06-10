"""
core/multiplayer_queue.py

Qt shell for the multiplayer turn queue.

Coquille fine (B4) : la file FIFO et la résolution séquentielle vivent dans
`axiom.multiplayer.ActionQueue` (pur threading) — ce module ne fait que faire
tourner la boucle sur un QThread et traduire les callbacks en signaux Qt.
`PlayerAction` est ré-exporté depuis le moteur (import inchangé pour le GUI).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QThread, Signal, QObject

from axiom.multiplayer import ActionQueue, PlayerAction  # noqa: F401 — ré-export

if TYPE_CHECKING:
    from axiom.arbitrator import ArbitratorEngine


class MultiplayerQueueSignals(QObject):
    """Signals for the ArbitratorWorker to communicate with the UI."""
    token_received = Signal(str, str)    # token, player_id
    turn_complete = Signal(object, str)  # ArbitratorResult, player_id
    error_occurred = Signal(str, str)    # error_msg, player_id
    status_update = Signal(str)


class ArbitratorWorker(QThread):
    """Fait tourner la boucle de résolution séquentielle sur un QThread.

    Une seule action est résolue à la fois (pas de course sur la DB) — la
    garantie vit côté moteur, ce worker n'est que le véhicule de thread.
    """

    def __init__(self, arbitrator: "ArbitratorEngine"):
        super().__init__()
        self._engine_queue = ActionQueue(arbitrator)
        self.signals = MultiplayerQueueSignals()

    def enqueue(self, action: PlayerAction):
        """Add a new action to the processing queue."""
        self._engine_queue.enqueue(action)

    def stop(self):
        """Gracefully stop the worker loop."""
        self._engine_queue.stop()

    def run(self):
        self._engine_queue.run_loop(
            on_token=self.signals.token_received.emit,
            on_complete=self.signals.turn_complete.emit,
            on_error=self.signals.error_occurred.emit,
            on_status=self.signals.status_update.emit,
        )
