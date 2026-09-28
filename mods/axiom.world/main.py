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
from axiom.textfmt import fmt_num


NATIVE_ENTITY_TYPES = ["player", "npc", "faction", "world"]


def _load_defined_stats(db_path: str) -> set[str]:
    """Load canonical lowercase stat names and IDs defined in universe."""
    if not db_path:
        return set()
    try:
        with get_connection(db_path) as conn:
            rows = conn.execute("SELECT stat_id, name FROM Stat_Definitions;").fetchall()
        defined = set()
        for r in rows:
            if r["stat_id"]:
                defined.add(str(r["stat_id"]).lower())
            if r["name"]:
                defined.add(str(r["name"]).lower())
        return defined
    except Exception:
        return set()


def _load_rules(db_path: str) -> list[dict[str, Any]]:
    """Load active creator rules from the database."""
    if not db_path:
        return []
    try:
        from axiom.db_helpers import load_rules_for_session
        return load_rules_for_session(db_path)
    except Exception:
        return []


def _resolve_entity_id(raw_id: str, all_stats: dict[str, dict[str, str]]) -> str:
    """Case-insensitive entity ID resolver."""
    clean = str(raw_id).strip()
    if clean in all_stats:
        return clean
    low = clean.lower()
    for eid in all_stats:
        if eid.lower() == low:
            return eid
    return clean


def _resolve_stat_key(raw_key: str, entity_stats: dict[str, str]) -> str:
    """Case-insensitive stat key resolver."""
    clean = str(raw_key).strip()
    if clean in entity_stats:
        return clean
    low = clean.lower()
    for k in entity_stats:
        if k.lower() == low:
            return k
    return clean


def _validate_change(
    entity_id: str,
    stat_key: str,
    delta: float | None,
    value: Any,
    all_stats: dict[str, dict[str, str]],
    defined_stats: set[str],
) -> tuple[bool, str]:
    if not entity_id or entity_id not in all_stats:
        return False, f"entity '{entity_id}' not found"
    if not stat_key:
        return False, "missing stat_key"
    if defined_stats and stat_key.lower() not in defined_stats:
        return False, f"stat '{stat_key}' is not defined in universe rules"
    if delta is None and value is None:
        return False, "neither delta nor value provided"
    if delta is not None and not isinstance(delta, (int, float)):
        return False, f"delta must be numeric, got {type(delta).__name__}"
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


def on_arbitrate_mutations(ctx: Any) -> None:
    """Hook: axiom.step:arbitrate_mutations.

    Validates raw state changes, applies numerical stat deltas, updates
    all_stats and write_batch, and evaluates the RulesEngine cascade.
    """
    db_path = getattr(ctx, "db_path", "")
    all_stats = getattr(ctx, "all_stats", {})
    defined_stats = _load_defined_stats(db_path) if getattr(ctx, "raw_state_changes", None) else set()
    write_batch = getattr(ctx, "write_batch", None)
    save_id = getattr(ctx, "save_id", "")
    turn_id = getattr(ctx, "turn_id", getattr(ctx, "step_id", 0))

    mutated_entities: set[str] = set()
    rejection_messages: list[str] = []

    for change in getattr(ctx, "raw_state_changes", []):
        raw_eid = change.get("entity_id", "")
        entity_id = _resolve_entity_id(raw_eid, all_stats)
        stat_key = _resolve_stat_key(change.get("stat_key", ""), all_stats.get(entity_id, {}))
        change["entity_id"] = entity_id
        change["stat_key"] = stat_key
        delta = change.get("delta")
        value = change.get("value")

        valid, reason = _validate_change(entity_id, stat_key, delta, value, all_stats, defined_stats)
        if valid:
            payload: dict[str, Any] = {"entity_id": entity_id, "stat_key": stat_key}
            if delta is not None:
                payload["delta"] = delta
                event_type = "stat_change"
                try:
                    curr = float(all_stats.get(entity_id, {}).get(stat_key, 0))
                    nxt = curr + float(delta)
                    all_stats.setdefault(entity_id, {})[stat_key] = fmt_num(nxt)
                except (ValueError, TypeError):
                    pass
            else:
                payload["value"] = value
                event_type = "stat_set"
                all_stats.setdefault(entity_id, {})[stat_key] = str(value)

            if entity_id == getattr(ctx, "player_entity_id", "player") and stat_key == "Location" and value:
                ctx.travel_note = f"Traveled to {value}"

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

    # Rules Engine evaluation
    base_rules = _load_rules(db_path)
    custom_rules: list[dict[str, Any]] = []
    # If custom rules are contributed via slots
    reg = getattr(ctx, "kernel_registry", None)
    if reg is not None and hasattr(reg, "get_slot"):
        for extra in reg.get_slot("axiom.world:custom_rules") or []:
            if isinstance(extra, list):
                custom_rules.extend(extra)
            elif isinstance(extra, dict):
                custom_rules.append(extra)

    all_rules = base_rules + custom_rules
    if all_rules and mutated_entities:
        engine = RulesEngine(all_rules)
        seen_signatures: set[str] = set()

        for _ in range(5):
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
            mutated_entities = new_mutations


def init(ctx: ModContext) -> None:
    """Entry point for axiom.world mod."""
    # Declare and contribute official entity types
    for entity_type in NATIVE_ENTITY_TYPES:
        ctx.contribute_slot("axiom.world:entity_types", entity_type)

    ctx.register_hook("axiom.step:gather_context", on_gather_context)
    ctx.register_hook("axiom.step:arbitrate_mutations", on_arbitrate_mutations)
