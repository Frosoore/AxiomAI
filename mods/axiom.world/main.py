"""mods/axiom.world/main.py

Official mod: axiom.world
Handles persistent world model: entities, stats, entity types, spatial map, and RulesEngine.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from axiom.kernel.context import ModContext
from axiom.rules import RulesEngine
from axiom.schema import get_connection
from axiom.db_helpers import load_defined_stat_names, load_entity_meta, resolve_entity_id
from axiom.textfmt import fmt_num


NATIVE_ENTITY_TYPES = ["player", "npc", "faction", "world"]


def _load_rules(db_path: str) -> list[dict[str, Any]]:
    """Load active creator rules from the database."""
    if not db_path:
        return []
    try:
        from axiom.db_helpers import load_rules_for_session
        return load_rules_for_session(db_path)
    except Exception:
        return []


def _resolve_stat_key(raw_key: str, entity_stats: dict[str, str]) -> str:
    """Prefer the entity's authored key (Sample) over a definition id (sample)."""
    from axiom.events import resolve_stat_key
    return resolve_stat_key(str(raw_key or "").strip(), entity_stats)


# Alias resolution shared with the turn and the other mods (kernel helpers).
_load_defined_stats = load_defined_stat_names
_load_entity_meta = load_entity_meta
_resolve_entity_id = resolve_entity_id


def _stat_allowed_for_entity(db_path: str, entity_id: str, stat_key: str) -> bool:
    """True if the stat is unlinked (all types) or linked to this entity's type."""
    try:
        with get_connection(db_path) as conn:
            if not conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='Stat_Type_Links';"
            ).fetchone():
                return True
            links = [
                r[0] for r in conn.execute(
                    "SELECT type_id FROM Stat_Type_Links WHERE LOWER(stat_id) = LOWER(?);",
                    (stat_key,),
                )
            ]
            if not links:  # also match by Stat_Definitions.name (display vs id)
                row = conn.execute(
                    "SELECT stat_id FROM Stat_Definitions WHERE LOWER(name) = LOWER(?);",
                    (stat_key,),
                ).fetchone()
                if row:
                    links = [
                        r[0] for r in conn.execute(
                            "SELECT type_id FROM Stat_Type_Links WHERE stat_id = ?;", (row[0],)
                        )
                    ]
            if not links:
                return True
            etype = conn.execute(
                "SELECT entity_type FROM Entities WHERE entity_id = ?;", (entity_id,)
            ).fetchone()
            return True if not etype else etype[0] in links
    except sqlite3.Error:
        return True


def _travel_distance(db_path: str, source_id: str, target_id: str) -> int:
    """Distance in km between two connected locations (0 if unknown)."""
    try:
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT distance_km FROM Location_Connections WHERE source_id = ? AND target_id = ?;",
                (source_id, target_id),
            ).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _validate_change(
    db_path: str,
    entity_id: str,
    stat_key: str,
    delta: Any,
    value: Any,
    all_stats: dict[str, dict[str, str]],
    defined_stats: set[str],
    *,
    plot_armor: bool = False,
) -> tuple[bool, str]:
    """Validate one proposed state change (unknown entity, undefined or unlinked stat,
    numeric resource going below zero). `plot_armor`: the Companion hero may drop to
    zero without the change being rejected."""
    if not entity_id:
        return False, "Missing entity_id in state change."
    if all_stats and entity_id not in all_stats:
        return False, f"Unknown entity: {entity_id}"
    if stat_key.lower() not in ("description", "location"):
        if stat_key.lower() not in defined_stats:
            return False, f"Stat '{stat_key}' is not defined in this universe. Custom stats are forbidden."
        if not _stat_allowed_for_entity(db_path, entity_id, stat_key):
            return False, f"Stat '{stat_key}' is not linked to this entity's type."

    entity_stats = all_stats.get(entity_id, {})
    current_raw = entity_stats.get(stat_key)
    if current_raw is None:
        for k, v in entity_stats.items():
            if k.lower() == stat_key.lower():
                current_raw = v
                break
    try:
        current_val: float | None = float("0" if current_raw is None else current_raw)
    except ValueError:
        current_val = None  # non-numeric stat

    if delta is not None:
        if current_val is None:
            return False, f"Cannot apply numeric delta to non-numeric stat {entity_id}.{stat_key}."
        try:
            result_val: float | None = current_val + float(delta)
        except (TypeError, ValueError):
            return False, f"delta must be numeric, got {type(delta).__name__}"
    elif value is not None:
        try:
            result_val = float(value)
        except (ValueError, TypeError):
            result_val = None  # assigning a non-numeric string is always valid
    else:
        return False, f"State change for {entity_id}.{stat_key} has neither delta nor value."

    if current_val is not None and result_val is not None and current_val >= 0 and result_val < 0:
        if plot_armor:
            return True, ""
        return False, f"{entity_id} does not have enough {stat_key} (current: {current_val:.0f})"
    return True, ""


def on_gather_context(ctx: Any) -> None:
    """Hook: axiom.step:gather_context.

    Contributes persistent world entity context to the step.
    """
    db_path = getattr(ctx, "db_path", None)
    if not db_path or getattr(ctx, "spatial_context", None):
        return

    player_id = getattr(ctx, "player_entity_id", "player")
    stats = getattr(ctx, "all_stats", {}).get(player_id, {})
    loc = stats.get("Location")
    if loc:
        try:
            from axiom.db_helpers import get_spatial_context
            ctx.spatial_context = get_spatial_context(db_path, loc)
        except Exception:
            pass


def on_arbitrate_mutations(ctx: Any, custom_rules_provider: Any = None) -> None:
    """Hook: axiom.step:arbitrate_mutations.

    Validates raw state changes, applies them to all_stats and the write batch,
    queues a correction hint for the rejected ones and evaluates the RulesEngine
    cascade (creator rules + `axiom.world:custom_rules` contributions).
    """
    db_path = getattr(ctx, "db_path", "")
    all_stats = getattr(ctx, "all_stats", {})
    raw_changes = getattr(ctx, "raw_state_changes", None) or []
    defined_stats = _load_defined_stats(db_path) if raw_changes else set()
    entity_meta = _load_entity_meta(db_path) if raw_changes else {}
    write_batch = getattr(ctx, "write_batch", None)
    save_id = getattr(ctx, "save_id", "")
    turn_id = getattr(ctx, "turn_id", getattr(ctx, "step_id", 0))
    player_id = getattr(ctx, "player_entity_id", "player")
    hero_id = getattr(ctx, "hero_entity_id", None)
    companion = getattr(ctx, "mode", "Normal") == "Companion"

    mutated_entities: set[str] = set()
    rejection_messages: list[str] = []

    for change in raw_changes:
        if not isinstance(change, dict):
            continue
        entity_id = _resolve_entity_id(change.get("entity_id", ""), all_stats, entity_meta)
        stat_key = _resolve_stat_key(change.get("stat_key", ""), all_stats.get(entity_id, {}))
        change["entity_id"] = entity_id
        change["stat_key"] = stat_key
        delta = change.get("delta")
        value = change.get("value")

        valid, reason = _validate_change(
            db_path, entity_id, stat_key, delta, value, all_stats, defined_stats,
            plot_armor=companion and hero_id is not None and entity_id == hero_id,
        )
        if valid:
            payload: dict[str, Any] = {"entity_id": entity_id, "stat_key": stat_key}
            if delta is not None:
                payload["delta"] = delta
                event_type = "stat_change"
                try:
                    curr = float(all_stats.get(entity_id, {}).get(stat_key, 0))
                    all_stats.setdefault(entity_id, {})[stat_key] = fmt_num(curr + float(delta))
                except (ValueError, TypeError):
                    pass
            else:
                payload["value"] = value
                event_type = "stat_set"
                old_loc = all_stats.get(entity_id, {}).get("Location")
                all_stats.setdefault(entity_id, {})[stat_key] = str(value)
                if entity_id == player_id and stat_key == "Location" and value and old_loc != value:
                    dist = _travel_distance(db_path, old_loc, value) if old_loc else 0
                    if dist > 0:
                        ctx.travel_note = f"Traveled to {value} ({dist} km)"

            if write_batch is not None:
                write_batch.events.append((save_id, turn_id, event_type, entity_id, payload))
                write_batch.stat_changes.append(change)

            ctx.applied_changes.append(change)
            mutated_entities.add(entity_id)
        else:
            rejected = dict(change)
            rejected["reason"] = reason
            ctx.rejected_changes_detailed.append(rejected)
            msg = f"{entity_id}.{stat_key}: {reason}"
            ctx.rejected_changes.append(msg)
            rejection_messages.append(msg)

    # Correction loop: the narrator is told about the rejection on the next turn.
    if rejection_messages:
        queue = getattr(ctx, "queue_correction", None)
        if callable(queue):
            queue("; ".join(rejection_messages))

    # Rules Engine evaluation
    base_rules = _load_rules(db_path)
    custom_rules: list[dict[str, Any]] = []
    for extra in (custom_rules_provider() if callable(custom_rules_provider) else None) or []:
        if isinstance(extra, list):
            custom_rules.extend(extra)
        elif isinstance(extra, dict):
            custom_rules.append(extra)

    all_rules = base_rules + custom_rules
    if all_rules and mutated_entities:
        engine = RulesEngine(all_rules)
        seen_signatures: set[str] = set()

        for depth in range(5):
            new_mutations: set[str] = set()
            for entity_id in list(mutated_entities):
                stats = all_stats.get(entity_id, {})
                triggered_actions = engine.evaluate(entity_id, stats)

                for action in triggered_actions:
                    sig = f"{entity_id}_{action.get('type')}_{action.get('stat')}_{action.get('value')}"
                    if sig in seen_signatures:
                        continue
                    seen_signatures.add(sig)

                    stat_key = action.get("stat")
                    payload = {
                        "entity_id": entity_id,
                        "stat_key": stat_key,
                        "source_rule": action.get("rule_id"),
                    }
                    if action["type"] == "stat_change":
                        payload["delta"] = action.get("value")
                        event_type = "stat_change"
                        try:
                            curr = float(all_stats.get(entity_id, {}).get(stat_key, 0))
                            nxt = curr + float(action.get("value", 0))
                            all_stats.setdefault(entity_id, {})[stat_key] = fmt_num(nxt)
                        except (ValueError, TypeError):
                            pass
                    else:
                        payload["value"] = action.get("value")
                        event_type = "stat_set"
                        all_stats.setdefault(entity_id, {})[stat_key] = str(action.get("value"))

                    if write_batch is not None:
                        write_batch.events.append((save_id, turn_id, event_type, entity_id, payload))
                        write_batch.events.append((save_id, turn_id, "rule_trigger", entity_id, action))

                    ctx.triggered_rules.append(action)
                    new_mutations.add(entity_id)

            if not new_mutations:
                break
            if depth == 4:
                # Iteration limit reached: possible infinite loop in creator rules.
                ctx.rule_chain_warning = True
                if write_batch is not None:
                    write_batch.events.append((
                        save_id, turn_id, "rule_engine_warning", "system",
                        {"message": "Maximum rule chaining depth (5) reached. Possible infinite loop detected."},
                    ))
            mutated_entities = new_mutations


def init(ctx: ModContext) -> None:
    """Entry point for axiom.world mod."""
    # Declare and contribute official entity types
    for entity_type in NATIVE_ENTITY_TYPES:
        ctx.contribute_slot("axiom.world:entity_types", entity_type)

    ctx.register_hook("axiom.step:gather_context", on_gather_context)
    ctx.register_hook(
        "axiom.step:arbitrate_mutations",
        lambda turn_ctx: on_arbitrate_mutations(
            turn_ctx, lambda: ctx.get_slot("axiom.world:custom_rules")
        ),
    )
