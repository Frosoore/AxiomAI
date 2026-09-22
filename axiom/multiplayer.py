"""axiom.multiplayer — player actions and a sequential turn-resolution queue.

`PlayerAction` is the action payload used by every front-end (GUI tabletop,
headless callers).

Multiplayer turns are resolved **simultaneously** by
`axiom.session.Session.take_turn_multiplayer` (every player intent in a single
tick) — that is what the GUI uses. `ActionQueue` is the older alternative that
resolves actions **one at a time** (FIFO) on the caller's thread; it is kept as
public engine API for headless embedders but no longer used by the app (its Qt
shell `core/multiplayer_queue.py` was removed). Pure threading, zero Qt.
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
    """A player action awaiting resolution."""
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
    """FIFO queue of player actions, resolved sequentially by the arbitrator.

    `run_loop` is blocking: the caller runs it on ITS thread (QThread on the
    GUI side, plain Python thread headless). `enqueue` and `stop` are
    thread-safe and callable from anywhere.
    """

    def __init__(self, arbitrator: "ArbitratorEngine") -> None:
        self._arbitrator = arbitrator
        self._queue: "queue.Queue[PlayerAction | None]" = queue.Queue()
        self._is_running = True

    def enqueue(self, action: PlayerAction) -> None:
        """Add an action to resolve."""
        self._queue.put(action)

    def stop(self) -> None:
        """Stop the loop cleanly (unblocks the pending `get`)."""
        self._is_running = False
        self._queue.put(None)

    def run_loop(
        self,
        on_token: Callable[[str, str], None] = _noop,      # (token, player_id)
        on_complete: Callable[[object, str], None] = _noop,  # (ArbitratorResult, player_id)
        on_error: Callable[[str, str], None] = _noop,      # (message, player_id)
        on_status: Callable[[str], None] = _noop,
    ) -> None:
        """Resolution loop: one action at a time, until `stop()`."""
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
