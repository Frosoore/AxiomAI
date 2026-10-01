"""community.survival - Main mod entry point.

Standard hook-based mod for Axiom AI.
"""

from __future__ import annotations

from typing import Any

from axiom.kernel.context import ModContext
from axiom.logger import logger


def build_survival_prompt_section(ctx: Any) -> dict[str, Any]:
    """Slot handler for axiom.turn:prompt_sections (survival guidelines)."""
    return {
        "position": "system",
        "text": (
            "SURVIVAL GUIDELINES: Pay attention to physical endurance, hunger, thirst, "
            "and fatigue. Prolonged heavy exertion or long elapsed travel should affect "
            "the character's stamina and state."
        ),
        "depth": 35,
    }


def on_gather_context(data: dict[str, Any]) -> None:
    """Hook invoked when context is assembled before prompting the LLM."""
    logger.debug("[community.survival] Gathering context")


def on_after_step(ctx: Any) -> None:
    """Hook invoked after step rules and narration have executed."""
    elapsed = getattr(ctx, "elapsed_minutes", 0) or 0
    if elapsed >= 120:
        write_batch = getattr(ctx, "write_batch", None)
        if write_batch is not None and hasattr(write_batch, "timeline_entries"):
            save_id = getattr(ctx, "save_id", "")
            turn_id = getattr(ctx, "turn_id", 0)
            new_time = getattr(ctx, "new_time", 0)
            write_batch.timeline_entries.append((
                save_id,
                turn_id,
                new_time,
                f"[Survival] Sustained physical exertion ({elapsed} mins elapsed) causes noticeable fatigue."
            ))


def init(ctx: ModContext) -> None:
    """Initialize the mod and register event hooks and slot contributions."""
    logger.info("Initializing hook mod '%s'", ctx.mod_id)
    ctx.contribute_slot("axiom.turn:prompt_sections", build_survival_prompt_section)
    ctx.register_hook("axiom.step:gather_context", on_gather_context)
    ctx.register_hook("axiom.step:after_step", on_after_step)
