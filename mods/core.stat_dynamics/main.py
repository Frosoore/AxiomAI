"""mods/core.stat_dynamics/main.py

Official mod: core.stat_dynamics — temporary stats and modifiers. Without this mod
no modifier is applied, ticked or shown, and no stat decays on its own.

- `axiom.step:gather_context`: active modifiers overlaid on the turn's stats; per-entity
  notes (modifiers, peak hold) and the TEMPORARY STATS block for the prompt.
- Output fields `modifiers` and `stat_events` (sub-schema + instruction contributed).
- `axiom.turn:arbitrate_stats`: LLM modifiers validated and staged; profiles ticked.
- `axiom.step:after_step`: modifiers tick by the turn's minutes (staged with the turn).
Save data (Active_Modifiers + snapshots): `storage.py`, run even while disabled.
"""

from __future__ import annotations

import uuid
from typing import Any

from axiom.db_helpers import load_defined_stat_names, load_entity_meta, resolve_entity_id
from axiom.events import resolve_stat_key
from axiom.kernel.context import ModContext
from axiom.logger import logger
from axiom.schema import get_connection
from axiom.textfmt import fmt_num
from mods.core.stat_dynamics.stat_dynamics import (
    apply_entity_tick,
    dynamics_by_key,
    ensure_stat_dynamics,
    format_dynamics_prompt,
    is_hidden_stat_key,
    lookup_dynamics,
    peak_hold_note,
)

def _active_modifiers(db_path: str, save_id: str) -> dict[str, list[dict[str, Any]]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT entity_id, stat_key, delta, minutes_remaining FROM Active_Modifiers WHERE save_id = ?;",
            (save_id,),
        ).fetchall()
    out: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        out.setdefault(r["entity_id"], []).append(
            {"stat_key": r["stat_key"], "delta": r["delta"], "minutes_remaining": r["minutes_remaining"]}
        )
    return out


def on_gather_context(ctx: Any) -> None:
    db_path = ctx.db_path
    mods_by_entity = _active_modifiers(db_path, ctx.save_id)
    for eid, mods in mods_by_entity.items():  # effective stats = base + modifiers
        stats = ctx.all_stats.get(eid)
        if stats is None:
            continue
        for m in mods:
            key = resolve_stat_key(str(m["stat_key"]), stats)
            try:
                stats[key] = fmt_num(float(stats.get(key, "0")) + m["delta"])
            except ValueError:
                continue
    dyn_table = dynamics_by_key(db_path)
    for eid, stats in ctx.relevant_stats.items():
        notes = {}
        for key in stats:
            dyn = lookup_dynamics(key, dyn_table) if dyn_table else None
            note = peak_hold_note(stats, key, dyn, ctx.total_mins) if dyn else ""
            if note:
                notes[key] = note
        ann = ctx.entity_annotations.setdefault(eid, {})
        ann["modifiers"] = mods_by_entity.get(eid, [])
        if notes:
            ann["dyn_notes"] = notes
    prompt = format_dynamics_prompt(db_path)
    if prompt:
        ctx.stats_prompt_notes.append(prompt)


def on_modifiers(value: Any, ctx: Any) -> None:
    ctx.raw_modifier_changes = value if isinstance(value, list) else []


def on_stat_events(value: Any, ctx: Any) -> None:
    ctx.stat_events = value if isinstance(value, list) else []


def _stage_clear(ctx: Any, entity_id: str, stat_key: str | None) -> None:
    def op(conn: Any, save_id: str, _turn: int) -> None:
        rows = conn.execute(
            "SELECT modifier_id, stat_key FROM Active_Modifiers WHERE save_id = ? AND entity_id = ?;",
            (save_id, entity_id),
        ).fetchall()
        ids = [r[0] for r in rows if stat_key is None or str(r[1]).lower() == stat_key.lower()]
        conn.executemany("DELETE FROM Active_Modifiers WHERE modifier_id = ?;", [(i,) for i in ids])
    ctx.write_batch.stage_op(op)


def _stage_add(ctx: Any, entity_id: str, stat_key: str, delta: float, minutes: int) -> None:
    def op(conn: Any, save_id: str, _turn: int) -> None:
        conn.execute(
            "INSERT INTO Active_Modifiers (modifier_id, save_id, entity_id, stat_key, delta, minutes_remaining) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (str(uuid.uuid4()), save_id, entity_id, stat_key, delta, minutes),
        )
    ctx.write_batch.stage_op(op)


def _arbitrate_modifiers(ctx: Any) -> None:
    raw = getattr(ctx, "raw_modifier_changes", None) or []
    if not raw:
        return
    defined = load_defined_stat_names(ctx.db_path)
    meta = load_entity_meta(ctx.db_path)
    for mod in raw:
        if not isinstance(mod, dict):
            continue
        entity_id = resolve_entity_id(mod.get("entity_id", ""), ctx.all_stats, meta)
        stat_key = resolve_stat_key(str(mod.get("stat_key", "")), ctx.all_stats.get(entity_id, {}))
        if mod.get("clear"):
            if not entity_id or not stat_key:
                ctx.queue_correction("Modifier clear missing entity_id or stat_key")
                continue
            _stage_clear(ctx, entity_id, stat_key)
            ctx.applied_modifiers.append({"entity_id": entity_id, "stat_key": stat_key, "clear": True})
            continue
        try:
            delta = float(mod.get("delta"))
        except (TypeError, ValueError):
            ctx.queue_correction(f"Modifier {entity_id}.{stat_key}: delta must be a number")
            continue
        try:
            minutes = int(mod.get("minutes", mod.get("minutes_remaining", 0)))
        except (TypeError, ValueError):
            minutes = 0
        if minutes < 1:
            ctx.queue_correction(f"Modifier {entity_id}.{stat_key}: minutes must be >= 1")
            continue
        if defined and stat_key.lower() not in defined:
            ctx.queue_correction(f"Modifier {entity_id}.{stat_key}: unknown stat")
            continue
        _stage_add(ctx, entity_id, stat_key, delta, minutes)
        ctx.applied_modifiers.append(
            {"entity_id": entity_id, "stat_key": stat_key, "delta": delta, "minutes": minutes}
        )


def on_arbitrate_stats(ctx: Any) -> None:
    """Hook: axiom.turn:arbitrate_stats — LLM modifiers, then the profiles' tick."""
    _arbitrate_modifiers(ctx)
    dyn_table = dynamics_by_key(ctx.db_path)
    if not dyn_table:
        return
    for entity_id, stats in list(ctx.all_stats.items()):
        for stat_key, value, reason in apply_entity_tick(
            stats, dyn_table,
            elapsed_minutes=ctx.elapsed_minutes,
            now_minutes=ctx.new_time,
            stat_events=getattr(ctx, "stat_events", []),
            entity_id=entity_id,
        ):
            payload = {"entity_id": entity_id, "stat_key": stat_key, "value": value,
                       "source": "dynamics", "reason": reason}
            ctx.write_batch.events.append((ctx.save_id, ctx.turn_id, "stat_set", entity_id, payload))
            stats[stat_key] = value
            if not is_hidden_stat_key(stat_key):
                ctx.applied_changes.append(
                    {"entity_id": entity_id, "stat_key": stat_key, "value": value, "reason": reason}
                )
            if reason == "crash":
                _stage_clear(ctx, entity_id, stat_key)


def on_after_step(ctx: Any) -> None:
    """Modifiers lose the turn's minutes; expired ones are removed (staged with the turn)."""
    elapsed = int(getattr(ctx, "elapsed_minutes", 0) or 0)

    def tick(conn: Any, save_id: str, _turn: int) -> None:
        conn.execute(
            "UPDATE Active_Modifiers SET minutes_remaining = minutes_remaining - ? WHERE save_id = ?;",
            (elapsed, save_id),
        )
        conn.execute("DELETE FROM Active_Modifiers WHERE minutes_remaining <= 0 AND save_id = ?;", (save_id,))

    ctx.write_batch.stage_op(tick)

MODIFIERS_FIELD = {
    "name": "modifiers",
    "schema": [{"entity_id": "...", "stat_key": "...", "delta": 0, "minutes": 20}],
    "instruction": "Short overlays on a stat: {delta, minutes} (or {clear: true}).",
    "handler": on_modifiers,
}
STAT_EVENTS_FIELD = {
    "name": "stat_events",
    "schema": [{"entity_id": "...", "event": "..."}],
    "instruction": (
        "Temporary stats are listed in TEMPORARY STATS with an engine profile: do not invent "
        "their decay. When a crash/extend event of a profile happens, emit it here."
    ),
    "handler": on_stat_events,
}


class StatDynamicsService:
    """Public service of core.stat_dynamics for the engine and the UIs."""

    @staticmethod
    def ensure_stat_dynamics(db_path: str, llm: Any | None = None) -> int:
        """Classify the universe's stats once (called at Session start)."""
        return ensure_stat_dynamics(db_path, llm)

    @staticmethod
    def get_active_modifiers(db_path: str, save_id: str) -> list[dict[str, Any]]:
        return [
            {"entity_id": eid, **m}
            for eid, mods in sorted(_active_modifiers(db_path, save_id).items())
            for m in sorted(mods, key=lambda m: m["stat_key"])
        ]

    @staticmethod
    def apply_modifiers(db_path: str, save_id: str, entity_id: str, stats: dict[str, str]) -> dict[str, str]:
        """Stats of one entity with its active modifiers overlaid (read-only)."""
        from mods.core.stat_dynamics.modifiers import ModifierProcessor
        return ModifierProcessor(db_path).apply_modifiers(save_id, entity_id, stats)

    @staticmethod
    def infer(stats: list[dict[str, Any]], llm: Any, world_hint: str = "") -> list[dict[str, Any]]:
        """Classify which stats are temporary and on what basis (Creator helper)."""
        from mods.core.stat_dynamics.stat_dynamics import infer_stat_dynamics
        return infer_stat_dynamics(stats, llm, world_hint=world_hint)

    @staticmethod
    def tick(db_path: str, save_id: str, elapsed_minutes: int) -> list[str]:
        """Out-of-turn tick of the modifiers (returns the expired ones)."""
        from mods.core.stat_dynamics.modifiers import ModifierProcessor
        return ModifierProcessor(db_path).tick_modifiers(save_id, elapsed_minutes)


def init(ctx: ModContext) -> None:
    """Entry point for core.stat_dynamics mod."""
    ctx.register_service("stat_dynamics", StatDynamicsService())
    ctx.contribute_slot("axiom.turn:output_fields", MODIFIERS_FIELD)
    ctx.contribute_slot("axiom.turn:output_fields", STAT_EVENTS_FIELD)
    ctx.register_hook("axiom.step:gather_context", on_gather_context)
    ctx.register_hook("axiom.turn:arbitrate_stats", on_arbitrate_stats)
    ctx.register_hook("axiom.step:after_step", on_after_step)
