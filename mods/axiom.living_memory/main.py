"""mods/axiom.living_memory/main.py

Official mod: axiom.living_memory (Living Memory: Facts, Beliefs, Mental Models)
Provides:
1. Symbolic knowledge distillation (facts, observations, mental models).
2. Slot contribution to axiom.turn:prompt_sections (injects recent facts and on-scene entity mental models).
3. Hook axiom.step:after_step (triggers asynchronous living memory distillation with session epoch guard).
4. Service 'living_memory' registration for UI and engine queries.
"""

from __future__ import annotations

from typing import Any, Callable

from axiom.kernel.context import ModContext
from axiom.logger import logger
from mods.axiom.living_memory.facts import get_facts
from mods.axiom.living_memory.living_memory import get_living_memory_accumulator
from mods.axiom.living_memory.mental_models import get_mental_models
from mods.axiom.living_memory.observations import get_observations


class LivingMemoryService:
    """Public service exposed by axiom.living_memory."""

    def __init__(self) -> None:
        self.accumulator = get_living_memory_accumulator()

    def set_context(self, ctx: Any) -> None:
        if hasattr(self.accumulator, "set_context"):
            self.accumulator.set_context(ctx)

    def get_facts(self, db_path: str, save_id: str, max_turn_id: int | None = None) -> list[Any]:
        return get_facts(db_path, save_id, max_turn_id=max_turn_id)

    def get_observations(self, db_path: str, save_id: str, max_turn_id: int | None = None) -> list[Any]:
        return get_observations(db_path, save_id, max_turn_id=max_turn_id)

    def get_models(self, db_path: str, save_id: str, max_turn_id: int | None = None) -> list[Any]:
        return get_mental_models(db_path, save_id, max_turn_id=max_turn_id)

    def extract_now(
        self,
        db_path: str,
        save_id: str,
        turn_id: int,
        llm: Any = None,
        force_catchup: bool = False,
    ) -> dict[str, Any]:
        return self.accumulator.run_extract_now(
            db_path,
            save_id,
            turn_id,
            force_catchup=force_catchup,
            llm=llm,
        )

    def reset(self) -> None:
        self.accumulator.reset()

    def record_turn(
        self,
        db_path: str,
        save_id: str,
        turn_id: int,
        narrative_text: str,
        *,
        llm: Any = None,
        epoch: int | None = None,
        epoch_checker: Callable[[], int] | None = None,
    ) -> Any:
        return self.accumulator.record_turn(
            db_path,
            save_id,
            turn_id,
            narrative_text,
            llm=llm,
            epoch=epoch,
            epoch_checker=epoch_checker,
        )


_LM_SERVICE: LivingMemoryService | None = None


def get_living_memory_service() -> LivingMemoryService:
    global _LM_SERVICE
    if _LM_SERVICE is None:
        _LM_SERVICE = LivingMemoryService()
    return _LM_SERVICE


def build_living_memory_prompt_section(ctx: Any) -> dict[str, Any] | None:
    """Slot handler for axiom.turn:prompt_sections: in living mode, the character
    profiles, beliefs (with trend) and facts relevant to this scene join the memory
    block of the prompt (see recall.py). Errors are reported by the turn (the mod is
    disabled), never hidden."""
    if not getattr(ctx, "db_path", "") or not getattr(ctx, "save_id", ""):
        return None
    from axiom.config import load_config
    from mods.axiom.living_memory.recall import recall_lines

    lines = recall_lines(ctx, load_config())
    if not lines:
        return None
    return {"position": "rag", "text": "\n".join(lines)}


def on_after_step(ctx: Any) -> None:
    """Hook: axiom.step:after_step.
    Records the turn into LivingMemoryAccumulator with session epoch guard.
    """
    db_path = getattr(ctx, "db_path", "")
    save_id = getattr(ctx, "save_id", "")
    turn_id = getattr(ctx, "turn_id", 0)
    narrative = getattr(ctx, "narrative_text", "") or ""
    epoch = getattr(ctx, "epoch", None)
    epoch_checker = getattr(ctx, "epoch_checker", None)

    if not db_path or not save_id or not narrative.strip():
        return

    svc = get_living_memory_service()

    def _accumulate() -> None:
        if epoch is not None and epoch_checker is not None:
            curr_epoch = epoch_checker()
            if epoch != curr_epoch:
                logger.warning(
                    "[axiom.living_memory] Époque de session périmée (%d vs %d). Accumulation ignorée.",
                    epoch,
                    curr_epoch,
                )
                return
        svc.record_turn(
            db_path,
            save_id,
            turn_id,
            narrative,
            llm=getattr(ctx, "llm", None),
            epoch=epoch,
            epoch_checker=epoch_checker,
        )

    if hasattr(ctx, "write_batch") and hasattr(ctx.write_batch, "post_commit_callbacks"):
        ctx.write_batch.post_commit_callbacks.append(_accumulate)
    else:
        _accumulate()


def init(ctx: ModContext) -> None:
    """Entry point for axiom.living_memory mod."""
    svc = get_living_memory_service()
    svc.set_context(ctx)
    ctx.register_service("living_memory", svc)

    # Register prompt section contribution
    ctx.contribute_slot("axiom.turn:prompt_sections", build_living_memory_prompt_section)

    # Register turn hook
    ctx.register_hook("axiom.step:after_step", on_after_step)

    # Register settings tab contribution
    try:
        from mods.axiom.living_memory.ui.memory_settings_tab import MemorySettingsTab
        ctx.contribute_slot("axiom.ui.qt:settings_tab", MemorySettingsTab)
    except Exception as exc:
        logger.debug("[axiom.living_memory] Could not load MemorySettingsTab: %s", exc)

