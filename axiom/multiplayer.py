"""axiom.multiplayer — file de résolution séquentielle des tours (portage B4).

Logique extraite de `core/multiplayer_queue.py` : en multijoueur, les actions
des joueurs sont résolues **une à la fois** (FIFO) pour éviter toute course
sur la base. Pur threading, zéro Qt — la coquille Qt
(`core/multiplayer_queue.py::ArbitratorWorker`) ne fait que déporter
`run_loop` sur un QThread et traduire les callbacks en signaux.
"""

from __future__ import annotations

import queue
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from axiom.arbitrator import ArbitratorEngine
    from axiom.backends.base import LLMMessage


@dataclass
class PlayerAction:
    """Action de joueur en attente de résolution."""
    player_id: str
    text: str
    save_id: str
    turn_id: int
    universe_system_prompt: str
    history: list["LLMMessage"]
    temperature: float = 0.7
    top_p: float = 1.0
    verbosity_level: str = "balanced"


def _noop(*_args) -> None:
    pass


class ActionQueue:
    """File FIFO d'actions joueurs, résolues séquentiellement par l'arbitrator.

    `run_loop` est bloquant : l'appelant le fait tourner sur SON thread
    (QThread côté GUI, thread Python en headless). `enqueue` et `stop` sont
    thread-safe et appelables depuis n'importe où.
    """

    def __init__(self, arbitrator: "ArbitratorEngine") -> None:
        self._arbitrator = arbitrator
        self._queue: "queue.Queue[PlayerAction | None]" = queue.Queue()
        self._is_running = True

    def enqueue(self, action: PlayerAction) -> None:
        """Ajoute une action à résoudre."""
        self._queue.put(action)

    def stop(self) -> None:
        """Arrête proprement la boucle (débloque le `get` en attente)."""
        self._is_running = False
        self._queue.put(None)

    def run_loop(
        self,
        on_token: Callable[[str, str], None] = _noop,      # (token, player_id)
        on_complete: Callable[[object, str], None] = _noop,  # (ArbitratorResult, player_id)
        on_error: Callable[[str, str], None] = _noop,      # (message, player_id)
        on_status: Callable[[str], None] = _noop,
    ) -> None:
        """Boucle de résolution : une action à la fois, jusqu'à `stop()`."""
        while self._is_running:
            action = self._queue.get()  # bloque jusqu'à la prochaine action
            if action is None or not self._is_running:
                break

            try:
                on_status(f"Resolving action for {action.player_id}...")

                result = self._arbitrator.process_turn(
                    save_id=action.save_id,
                    turn_id=action.turn_id,
                    intents={action.player_id: action.text},
                    universe_system_prompt=action.universe_system_prompt,
                    history=action.history,
                    stream_token_callback=lambda tok: on_token(tok, action.player_id),
                    temperature=action.temperature,
                    top_p=action.top_p,
                    verbosity_level=action.verbosity_level,
                )
                on_complete(result, action.player_id)
                on_status("Ready.")
            except Exception as exc:  # noqa: BLE001 — la boucle ne doit jamais mourir
                on_error(str(exc), action.player_id)
                on_status("Error.")
            finally:
                self._queue.task_done()
