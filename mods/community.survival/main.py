"""community.survival - Main mod entry point.

Standard hook-based mod for Axiom AI.
"""

from __future__ import annotations

from typing import Any

from axiom.kernel.context import ModContext
from axiom.logger import logger


def on_gather_context(data: dict[str, Any]) -> None:
    """Hook invoked when context is assembled before prompting the LLM."""
    logger.debug("[community.survival] Gathering context")


def on_after_step(data: dict[str, Any]) -> None:
    """Hook invoked after step rules and narration have executed."""
    logger.debug("[community.survival] Step post-processing")


def init(ctx: ModContext) -> None:
    """Initialize the mod and register event hooks."""
    logger.info("Initializing hook mod '%s'", ctx.mod_id)
    ctx.register_hook("axiom.turn:gather_context", on_gather_context)
    ctx.register_hook("axiom.turn:after_step", on_after_step)
