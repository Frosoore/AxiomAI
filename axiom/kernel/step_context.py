"""axiom/kernel/step_context.py

Unified execution context for turn/step pipelines dispatched by the kernel.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class NoTurnPipelineInstalledError(Exception):
    """Raised when take_turn is called but no mod provides 'axiom.kernel:execute_step'."""


@dataclass
class KernelStepContext:
    """Carries full turn/step execution parameters and returns step result."""

    save_id: str
    step: int
    input: str
    db_path: str = ""
    epoch: int = 0
    llm: Any = None
    time_llm: Any = None
    vector_memory: Any = None
    stream_token_callback: Callable[[str], None] | None = None
    temperature: float = 0.7
    top_p: float = 1.0
    verbosity_level: str = "balanced"
    mode: str = "Normal"
    hero_entity_id: str | None = None
    intents: dict[str, str] = field(default_factory=dict)
    auto_commit: bool = True
    session: Any = None
    result: Any = None

    @property
    def turn_id(self) -> int:
        return self.step

    @property
    def step_id(self) -> int:
        return self.step
