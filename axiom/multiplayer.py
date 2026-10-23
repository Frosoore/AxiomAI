"""axiom.multiplayer — player actions and a sequential turn-resolution queue.

`PlayerAction` is the action payload used by every front-end (GUI tabletop,
headless callers).

Multiplayer turns are resolved **simultaneously** by
`axiom.session.Session.take_turn_multiplayer` (every player intent in a single
tick) — that is what the GUI uses. `ActionQueue` is the older alternative that
resolves actions **one at a time** (FIFO) on the caller's thread; it is kept as
public engine API for headless embedders but no longer used by the app (its Qt
shell `core/multiplayer_queue.py` was removed). Pure threading, zero Qt.

Each action goes through `ArbitratorEngine.process_turn`, which dispatches to the
single turn orchestration (hook `axiom.kernel:execute_step` of the `axiom.turn`
mod) — the same path as `Session.take_turn`.
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
    temperature: float = 1.12
    top_p: float = 1.0
    verbosity_level: str = "balanced"
    min_p: float = 0.1
    dry_multiplier: float = 0.8


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
        try:
            import inspect
            sig = inspect.signature(arbitrator.process_turn)
            has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
            self._supports_min_p = has_var_kw or "min_p" in sig.parameters
            self._supports_dry = has_var_kw or "dry_multiplier" in sig.parameters
        except Exception:
            self._supports_min_p = True
            self._supports_dry = True

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

                turn_kwargs = {
                    "save_id": action.save_id,
                    "turn_id": action.turn_id,
                    "intents": {action.player_id: action.text},
                    "universe_system_prompt": action.universe_system_prompt,
                    "history": action.history,
                    "stream_token_callback": lambda tok: on_token(tok, action.player_id),
                    "temperature": action.temperature,
                    "top_p": action.top_p,
                    "verbosity_level": action.verbosity_level,
                }
                if self._supports_min_p:
                    turn_kwargs["min_p"] = action.min_p
                if self._supports_dry:
                    turn_kwargs["dry_multiplier"] = action.dry_multiplier

                result = self._arbitrator.process_turn(**turn_kwargs)
                on_complete(result, action.player_id)
                on_status("Ready.")
            except Exception as exc:  # noqa: BLE001 — la boucle ne doit jamais mourir
                on_error(str(exc), action.player_id)
                on_status("Error.")
            finally:
                self._queue.task_done()
