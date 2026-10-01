"""mods/core.stat_dynamics/main.py

Official mod: core.stat_dynamics
Manages temporal decay, resting points, peak tracking, and active modifier expiration.
"""

from __future__ import annotations

from typing import Any

from axiom.kernel.context import ModContext
try:
    from mods.core.stat_dynamics.stat_dynamics import (
        apply_entity_tick,
        dynamics_by_key,
        is_hidden_stat_key,
    )
except (ImportError, ValueError):
    from axiom.stat_dynamics import (
        apply_entity_tick,
        dynamics_by_key,
        is_hidden_stat_key,
    )


def on_arbitrate_stats(ctx: Any) -> None:
    """Hook: axiom.turn:arbitrate_stats.

    Intercepts TurnContext during arbitration stage.
    Reads dynamic profiles (heal, buildup, duration).
    Calculates passive gauge adjustments based on elapsed minutes.
    Adjusts ctx.write_batch and ctx.applied_changes with calculated values.
    """
    db_path = getattr(ctx, "db_path", None)
    if not db_path:
        dyn_table = getattr(ctx, "dynamics_table", None)
        if dyn_table is None:
            return
    else:
        try:
            dyn_table = dynamics_by_key(db_path)
        except Exception:
            dyn_table = getattr(ctx, "dynamics_table", {})

    if not dyn_table:
        return

    elapsed_minutes = getattr(ctx, "in_game_minutes_elapsed", getattr(ctx, "elapsed_minutes", 1))
    now_minutes = getattr(ctx, "new_time", getattr(ctx, "total_mins", 0))
    stat_events = getattr(ctx, "stat_events", [])
    save_id = getattr(ctx, "save_id", "")
    turn_id = getattr(ctx, "turn_id", getattr(ctx, "step_id", 0))

    all_stats = getattr(ctx, "all_stats", {})
    applied_list = getattr(ctx, "applied_changes", None)
    write_batch = getattr(ctx, "write_batch", None)

    for entity_id, stats in list(all_stats.items()):
        changes = apply_entity_tick(
            stats,
            dyn_table,
            elapsed_minutes=elapsed_minutes,
            now_minutes=now_minutes,
            stat_events=stat_events,
            entity_id=entity_id,
        )
        for stat_key, value, reason in changes:
            payload = {
                "entity_id": entity_id,
                "stat_key": stat_key,
                "value": value,
                "source": "dynamics",
                "reason": reason,
            }
            if write_batch is not None:
                write_batch.events.append((save_id, turn_id, "stat_set", entity_id, payload))

            stats[stat_key] = value

            if applied_list is not None and not is_hidden_stat_key(stat_key):
                applied_list.append({
                    "entity_id": entity_id,
                    "stat_key": stat_key,
                    "value": value,
                    "reason": reason,
                })

            if reason == "crash" and write_batch is not None:
                write_batch.modifier_mutations.append({
                    "type": "clear",
                    "entity_id": entity_id,
                    "stat_key": stat_key,
                })


def on_after_step(ctx: Any) -> None:
    """Hook: axiom.step:after_step.

    Decrements remaining minutes on Active_Modifiers.
    Purges expired modifiers (minutes_remaining <= 0).
    Captures modifier snapshot via TurnWriteBatch.
    """
    write_batch = getattr(ctx, "write_batch", None)
    if write_batch is None:
        return

    elapsed = getattr(ctx, "in_game_minutes_elapsed", getattr(ctx, "elapsed_minutes", 1))
    turn_id = getattr(ctx, "turn_id", getattr(ctx, "step_id", 0))

    write_batch.modifier_mutations.append({
        "type": "tick",
        "elapsed_minutes": elapsed,
    })
    write_batch.modifier_mutations.append({
        "type": "snapshot",
        "turn_id": turn_id,
    })


def init(ctx: ModContext) -> None:
    """Entry point for core.stat_dynamics mod."""
    ctx.register_hook("axiom.turn:arbitrate_stats", on_arbitrate_stats)
    ctx.register_hook("axiom.step:after_step", on_after_step)
