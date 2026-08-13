"""Temporary-stat dynamics — authored profiles the engine ticks itself.

A stat is temporary when the author checks it, or when play-start inference
classifies it. The profile lives in ``Stat_Definitions.parameters`` (no new
columns). Kinds:

- **heal**     — value drifts toward ``resting`` over ``heal_minutes``
                 (a wound closing, health returning, fatigue fading).
- **buildup**  — scene/character raise it; engine clamps, tracks time at
                 peak, snaps to resting on a ``crash_on`` event (and can
                 extend the peak on ``extend_on``).
- **duration** — short overlay; Active_Modifiers still tick, and the base
                 also eases toward resting over ``heal_minutes``.

Nothing here names a particular world stat. Arousal, wounds, drugs, heat,
tension — they are just profiles.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from axiom.events import resolve_stat_key
from axiom.schema import get_connection

KINDS = ("heal", "buildup", "duration")
PACES = ("fast", "medium", "slow")
HIDDEN_PREFIX = "__dyn."
_DAY = 1440
_DEFAULT_HEAL = 7 * _DAY
_DEFAULT_PEAK = 8
_DEFAULT_DURATION = 120

# Fixed engine table — the LLM only picks a pace band, not raw minutes.
# Fast = scene / hours. Medium = a day. Slow = days–weeks.
PACE_MINUTES: dict[tuple[str, str], int] = {
    ("heal", "fast"): 4 * 60,
    ("heal", "medium"): _DAY,
    ("heal", "slow"): 14 * _DAY,
    ("buildup", "fast"): 8,
    ("buildup", "medium"): 30,
    ("buildup", "slow"): 4 * 60,
    ("duration", "fast"): 90,
    ("duration", "medium"): 8 * 60,
    ("duration", "slow"): _DAY,
}


def minutes_for_pace(kind: str, pace: str) -> int:
    k = kind if kind in KINDS else "heal"
    p = pace if pace in PACES else "medium"
    return PACE_MINUTES[(k, p)]


def is_hidden_stat_key(key: str) -> bool:
    return str(key).startswith(HIDDEN_PREFIX)


def peak_since_key(stat_key: str) -> str:
    return f"{HIDDEN_PREFIX}{stat_key}.peak_since"


def _as_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _num(raw: Any, default: float) -> float:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return float(default)


def _int(raw: Any, default: int) -> int:
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return int(default)


def _tags(raw: Any) -> list[str]:
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",")]
        return [p.lower() for p in parts if p]
    if isinstance(raw, (list, tuple)):
        return [str(p).strip().lower() for p in raw if str(p).strip()]
    return []


def fold_into_parameters(entry: dict[str, Any]) -> dict[str, Any]:
    """Lift top-level TOML ``temporary`` / ``dynamics`` into ``parameters``."""
    params = _as_dict(entry.get("parameters"))
    if "temporary" in entry:
        params["temporary"] = bool(entry["temporary"])
    dyn = params.get("dynamics")
    if not isinstance(dyn, dict):
        dyn = {}
    if isinstance(entry.get("dynamics"), dict):
        dyn = {**dyn, **entry["dynamics"]}
    for key in (
        "kind", "pace", "resting", "heal_minutes", "peak_hold_minutes",
        "crash_on", "extend_on", "basis",
    ):
        if key in entry:
            dyn[key] = entry[key]
    if dyn:
        params["dynamics"] = dyn
        if "temporary" not in params:
            params["temporary"] = True
    return params


def parse_dynamics(parameters: Any) -> dict[str, Any] | None:
    """Normalized profile, or None if the stat is not temporary."""
    params = _as_dict(parameters)
    dyn_raw = params.get("dynamics")
    dyn = dyn_raw if isinstance(dyn_raw, dict) else {}
    if "temporary" in params:
        temporary = bool(params["temporary"])
    elif dyn:
        temporary = True
    else:
        return None
    if not temporary:
        return None

    kind = str(dyn.get("kind") or "heal").strip().lower()
    if kind not in KINDS:
        kind = "heal"
    vmin = _num(dyn.get("min", params.get("min", 0)), 0)
    vmax = _num(dyn.get("max", params.get("max", 100)), 100)
    if vmax < vmin:
        vmin, vmax = vmax, vmin
    default_rest = vmax if kind == "heal" and str(dyn.get("resting", "")).lower() != "0" else vmin
    # heal toward max unless the author/inferrer set an explicit resting
    if "resting" in dyn:
        resting = _num(dyn.get("resting"), default_rest)
    elif kind == "heal":
        resting = vmax
    else:
        resting = vmin

    pace = str(dyn.get("pace") or "").strip().lower()
    if pace not in PACES:
        pace = ""
    heal_default = _DEFAULT_DURATION if kind == "duration" else _DEFAULT_HEAL
    if pace:
        mapped = minutes_for_pace(kind, pace)
        if kind == "buildup":
            heal_minutes = max(1, _int(dyn.get("heal_minutes"), heal_default))
            peak_hold = max(1, _int(dyn.get("peak_hold_minutes"), mapped))
        else:
            heal_minutes = max(1, _int(dyn.get("heal_minutes"), mapped))
            peak_hold = max(1, _int(dyn.get("peak_hold_minutes"), _DEFAULT_PEAK))
    else:
        heal_minutes = max(1, _int(dyn.get("heal_minutes"), heal_default))
        peak_hold = max(1, _int(dyn.get("peak_hold_minutes"), _DEFAULT_PEAK))
    return {
        "temporary": True,
        "kind": kind,
        "pace": pace or None,
        "min": vmin,
        "max": vmax,
        "resting": resting,
        "heal_minutes": heal_minutes,
        "peak_hold_minutes": peak_hold,
        "crash_on": _tags(dyn.get("crash_on")),
        "extend_on": _tags(dyn.get("extend_on")),
        "basis": str(dyn.get("basis") or "").strip(),
        "inferred": bool(dyn.get("inferred")),
    }


def needs_inference(parameters: Any) -> bool:
    """True when play-start should ask the LLM to classify this stat."""
    params = _as_dict(parameters)
    if "temporary" in params and not params["temporary"]:
        return False
    dyn = params.get("dynamics") if isinstance(params.get("dynamics"), dict) else {}
    if params.get("temporary") and dyn.get("kind") in KINDS:
        return False
    if dyn.get("kind") in KINDS and params.get("temporary") is not False:
        return False
    return True


def load_stat_rows(db_path: str) -> list[dict[str, Any]]:
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT stat_id, name, description, value_type, parameters "
            "FROM Stat_Definitions;"
        ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append({
            "stat_id": r["stat_id"],
            "name": r["name"],
            "description": r["description"] or "",
            "value_type": r["value_type"],
            "parameters": _as_dict(r["parameters"]),
        })
    return out


def dynamics_by_key(db_path: str) -> dict[str, dict[str, Any]]:
    """Map lowercased stat_id and name → parsed dynamics (temporary only)."""
    found: dict[str, dict[str, Any]] = {}
    for row in load_stat_rows(db_path):
        dyn = parse_dynamics(row["parameters"])
        if not dyn:
            continue
        payload = {**dyn, "stat_id": row["stat_id"], "name": row["name"]}
        if row["stat_id"]:
            found[str(row["stat_id"]).lower()] = payload
        if row["name"]:
            found[str(row["name"]).lower()] = payload
    return found


def lookup_dynamics(key: str, table: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if not key:
        return None
    return table.get(str(key).lower())


def format_dynamics_prompt(db_path: str) -> str:
    """Narrator block: generic, lists only stats that have a profile."""
    seen: set[str] = set()
    lines: list[str] = []
    for row in load_stat_rows(db_path):
        dyn = parse_dynamics(row["parameters"])
        if not dyn:
            continue
        sid = row["stat_id"]
        if sid in seen:
            continue
        seen.add(sid)
        label = row["name"] or sid
        parts = [f"- {label} (id {sid}): {dyn['kind']}"]
        if dyn.get("pace"):
            parts.append(f"pace {dyn['pace']}")
        parts.append(f"resting {dyn['resting']:g}")
        parts.append(f"range {dyn['min']:g}–{dyn['max']:g}")
        if dyn["kind"] in ("heal", "duration"):
            parts.append(f"recovers over {dyn['heal_minutes']} in-game minutes")
        if dyn["kind"] == "buildup":
            parts.append(f"holds peak ~{dyn['peak_hold_minutes']} min")
        if dyn["crash_on"]:
            parts.append("crash on " + ", ".join(dyn["crash_on"]))
        if dyn["extend_on"]:
            parts.append("extend peak on " + ", ".join(dyn["extend_on"]))
        if dyn["basis"]:
            parts.append("basis: " + dyn["basis"])
        lines.append("; ".join(parts))
    if not lines:
        return ""
    header = (
        "TEMPORARY STATS (engine-ticked — do not simulate their decay yourself)\n"
        "Heal/duration: only emit a change when something NEW happens "
        "(another injury, a potion, a fresh dose). The engine moves them "
        "toward resting with time.\n"
        "Buildup: emit a delta when the scene would raise or lower them; "
        "rate is character- and moment-specific. The engine clamps to max "
        "and tracks time at peak. When a listed crash event happens, emit "
        "stat_events [{entity_id, event}] — the engine snaps to resting. "
        "To hold a peak longer, emit the listed extend event.\n"
        "Duration overlays (drugs, adrenaline) may also use modifiers "
        "[{entity_id, stat_key, delta, minutes}] or {clear: true}.\n"
    )
    return header + "\n".join(lines)


def clamp_value(value: float, dyn: dict[str, Any]) -> float:
    return max(dyn["min"], min(dyn["max"], value))


def heal_toward(value: float, dyn: dict[str, Any], elapsed_minutes: int) -> float:
    if elapsed_minutes <= 0:
        return value
    span = max(1, int(dyn["heal_minutes"]))
    resting = float(dyn["resting"])
    if abs(value - resting) < 1e-9:
        return resting
    nxt = value + (resting - value) * (elapsed_minutes / span)
    # Do not overshoot resting
    if (resting - value) * (resting - nxt) <= 0:
        return resting
    return clamp_value(nxt, dyn)


def events_match(tags: list[str], fired: set[str]) -> bool:
    return bool(tags) and any(t in fired for t in tags)


CLASSIFY_SYSTEM = """\
You fill a classification form for one or more game stats.
Do not write prose. Do not invent new stat_ids.

INPUT per stat:
  STAT_ID, STAT_NAME, VALUE_TYPE, AUTHOR_NOTE
AUTHOR_NOTE is optional flavour from the human. Use the NAME even if the
note is empty. Never contradict a clear AUTHOR_NOTE. Never replace a
non-empty AUTHOR_NOTE.

QUESTIONS (answer in order):
1. Temporary? The number should move as in-game time passes without a new
   story decision (a meter that builds, fades, heals, or wears off).
   Lasting = cash, reputation, location, identity, inventory-like scores,
   flags that only change when the plot changes them.
2. If temporary: kind.
   heal     = drifts back toward a resting point (injury closing, vitality
              returning, fatigue fading).
   buildup  = rises with the scene; rate is character- and moment-specific;
              may sit at max briefly and snap down on an event.
   duration = short overlay that wears off (a dose, a rush).
3. If temporary: pace (pick one band — do not invent minutes).
   fast   = minutes to a few hours. Scene heat, a rush, a dose.
   medium = hours to about a day. Fatigue, hangover, lingering tension.
   slow   = days to weeks. A wound closing, illness, a broken bone.
4. resting: healthy max for a pool (e.g. vitality 100), or 0 for a problem
   or buildup meter.
5. crash_on / extend_on: ONLY when kind is buildup. They are story-event
   tags that snap the meter to resting (crash) or hold it at peak (extend).
   Invent tags from THIS stat's name/note. Heal, duration, and lasting
   stats MUST use empty lists — never copy tags from another stat.

Respond ONLY with a ~~~json block:
{"stats":[{
  "stat_id": "<echo the id>",
  "temporary": false,
  "kind": null,
  "pace": null,
  "resting": null,
  "crash_on": [],
  "extend_on": [],
  "basis": "one sentence: why this pace/kind",
  "description": ""
}]}
description: write a short one ONLY if AUTHOR_NOTE is (none). Otherwise "".
Categorical / non-numeric stats are temporary=false unless the note is
clearly a decaying meter.
"""


def _classify_user_block(stat: dict[str, Any]) -> str:
    note = str(stat.get("description") or "").strip() or "(none)"
    return (
        f"STAT_ID: {stat.get('stat_id') or ''}\n"
        f"STAT_NAME: {stat.get('name') or stat.get('stat_id') or ''}\n"
        f"VALUE_TYPE: {stat.get('value_type') or 'numeric'}\n"
        f"AUTHOR_NOTE: {note}"
    )


def infer_stat_dynamics(
    stats: list[dict[str, Any]],
    llm: Any,
    *,
    world_hint: str = "",
) -> list[dict[str, Any]]:
    """Classify stats with the fixed name+note form. Merges into a copy."""
    if not stats or llm is None:
        return stats
    blocks = [_classify_user_block(s) for s in stats]
    user = "Classify each stat.\n"
    if world_hint:
        user += f"WORLD: {world_hint[:800]}\n\n"
    user += "\n\n".join(blocks)
    messages = [
        {"role": "system", "content": CLASSIFY_SYSTEM},
        {"role": "user", "content": user},
    ]
    try:
        resp = llm.complete(messages, max_tokens=1800, temperature=0.2)
    except Exception:
        return stats
    payload = getattr(resp, "tool_call", None)
    if not isinstance(payload, dict):
        text = getattr(resp, "narrative_text", "") or str(resp)
        payload = _extract_json(text)
    proposed = payload.get("stats") if isinstance(payload, dict) else None
    if not isinstance(proposed, list):
        # Single-stat replies sometimes omit the wrapper.
        if isinstance(payload, dict) and payload.get("stat_id"):
            proposed = [payload]
        else:
            return stats
    by_id = {str(p.get("stat_id") or "").lower(): p for p in proposed if isinstance(p, dict)}
    by_name = {str(p.get("name") or "").lower(): p for p in proposed if isinstance(p, dict)}
    merged: list[dict[str, Any]] = []
    for stat in stats:
        item = dict(stat)
        hit = by_id.get(str(item.get("stat_id") or "").lower()) or by_name.get(
            str(item.get("name") or "").lower()
        )
        if hit:
            apply_classification(item, hit)
        merged.append(item)
    return merged


def apply_classification(stat: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
    """Merge a classify-form reply onto one stat. Never overwrites a note."""
    stat["parameters"] = merge_inferred_parameters(stat.get("parameters"), proposal)
    existing = str(stat.get("description") or "").strip()
    if not existing:
        desc = str(proposal.get("description") or "").strip()
        if desc:
            stat["description"] = desc
    return stat


def merge_inferred_parameters(existing: Any, proposal: dict[str, Any]) -> dict[str, Any]:
    params = _as_dict(existing)
    temporary = bool(proposal.get("temporary"))
    params["temporary"] = temporary
    if not temporary:
        if isinstance(params.get("dynamics"), dict):
            params["dynamics"]["inferred"] = True
        return params
    dyn = params.get("dynamics") if isinstance(params.get("dynamics"), dict) else {}
    kind = str(proposal.get("kind") or dyn.get("kind") or "heal").lower()
    if kind not in KINDS:
        kind = "heal"
    pace = str(proposal.get("pace") or dyn.get("pace") or "").strip().lower()
    if pace not in PACES:
        pace = "medium"
    mapped = minutes_for_pace(kind, pace)
    nxt = {
        **dyn,
        "kind": kind,
        "pace": pace,
        "resting": proposal.get("resting", dyn.get("resting")),
        "min": proposal.get("min", params.get("min", dyn.get("min", 0))),
        "max": proposal.get("max", params.get("max", dyn.get("max", 100))),
        "crash_on": proposal.get("crash_on", dyn.get("crash_on") or []),
        "extend_on": proposal.get("extend_on", dyn.get("extend_on") or []),
        "basis": str(proposal.get("basis") or dyn.get("basis") or "").strip(),
        "inferred": True,
    }
    if kind == "buildup":
        nxt["peak_hold_minutes"] = proposal.get(
            "peak_hold_minutes", dyn.get("peak_hold_minutes", mapped)
        )
        nxt["heal_minutes"] = proposal.get("heal_minutes", dyn.get("heal_minutes"))
    else:
        nxt["heal_minutes"] = proposal.get(
            "heal_minutes", dyn.get("heal_minutes", mapped)
        )
        nxt["peak_hold_minutes"] = proposal.get(
            "peak_hold_minutes", dyn.get("peak_hold_minutes")
        )
        nxt["crash_on"] = []
        nxt["extend_on"] = []
    params["dynamics"] = {k: v for k, v in nxt.items() if v is not None}
    if "min" in params["dynamics"]:
        params.setdefault("min", params["dynamics"]["min"])
    if "max" in params["dynamics"]:
        params.setdefault("max", params["dynamics"]["max"])
    return params


def persist_parameters(db_path: str, stats: list[dict[str, Any]]) -> int:
    """Write parameters JSON back onto Stat_Definitions. Returns rows updated."""
    updated = 0
    with get_connection(db_path) as conn:
        for stat in stats:
            sid = str(stat.get("stat_id") or "").strip()
            if not sid:
                continue
            params = _as_dict(stat.get("parameters"))
            conn.execute(
                "UPDATE Stat_Definitions SET parameters = ? WHERE stat_id = ?;",
                (json.dumps(params), sid),
            )
            updated += conn.execute("SELECT changes();").fetchone()[0]
        conn.commit()
    return updated


def ensure_stat_dynamics(db_path: str, llm: Any | None) -> int:
    """Play-start: classify stats that have no profile yet. Best-effort."""
    rows = load_stat_rows(db_path)
    missing = [r for r in rows if needs_inference(r.get("parameters"))]
    if not missing or llm is None:
        return 0
    hint = ""
    try:
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT value FROM Universe_Meta WHERE key IN ('name', 'global_lore') "
                "ORDER BY key DESC LIMIT 1;"
            ).fetchone()
            hint = (row["value"] if row else "") or ""
    except sqlite3.Error:
        hint = ""
    merged = infer_stat_dynamics(rows, llm, world_hint=hint)
    # Only persist rows that were missing, so author-set profiles stay put.
    missing_ids = {str(r["stat_id"]).lower() for r in missing}
    to_write = [s for s in merged if str(s.get("stat_id") or "").lower() in missing_ids]
    return persist_parameters(db_path, to_write)


def _extract_json(text: str) -> dict[str, Any]:
    if not text:
        return {}
    import re
    match = re.search(r"~~~json\s*(\{.*?\})\s*~~~", text, re.DOTALL)
    blob = match.group(1) if match else None
    if not blob:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        blob = match.group(0) if match else None
    if not blob:
        return {}
    try:
        data = json.loads(blob)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def collect_fired_events(
    stat_events: list[Any],
    entity_id: str,
    stat_key: str,
) -> set[str]:
    fired: set[str] = set()
    for raw in stat_events or []:
        if not isinstance(raw, dict):
            continue
        ev = str(raw.get("event") or raw.get("name") or "").strip().lower()
        if not ev:
            continue
        eid = str(raw.get("entity_id") or "")
        sk = str(raw.get("stat_key") or "")
        if eid and eid.lower() != str(entity_id).lower():
            continue
        if sk and sk.lower() != str(stat_key).lower():
            continue
        fired.add(ev)
    return fired


def apply_entity_tick(
    stats: dict[str, str],
    dyn_table: dict[str, dict[str, Any]],
    *,
    elapsed_minutes: int,
    now_minutes: int,
    stat_events: list[Any],
    entity_id: str,
) -> list[tuple[str, str, str]]:
    """Return (stat_key, new_value, reason) pairs that changed.

    ``reason`` is ``crash``, ``heal``, ``clamp``, ``peak``, or ``clear_peak``.
    Hidden peak-clock keys are included when they change.
    """
    from axiom.textfmt import fmt_num

    changes: list[tuple[str, str, str]] = []
    # Copy keys first — we may add hidden peak keys.
    for key in list(stats.keys()):
        if is_hidden_stat_key(key):
            continue
        dyn = lookup_dynamics(key, dyn_table)
        if not dyn:
            continue
        try:
            current = float(stats.get(key, dyn["resting"]))
        except (TypeError, ValueError):
            continue
        fired = collect_fired_events(stat_events, entity_id, key)
        nxt = current
        reason = ""
        if events_match(dyn["crash_on"], fired):
            nxt = float(dyn["resting"])
            reason = "crash"
        elif dyn["kind"] in ("heal", "duration") and elapsed_minutes > 0:
            nxt = heal_toward(current, dyn, elapsed_minutes)
            if abs(nxt - current) > 1e-9:
                reason = "heal"
        clamped = clamp_value(nxt, dyn)
        if abs(clamped - nxt) > 1e-9:
            nxt = clamped
            reason = reason or "clamp"
        if abs(nxt - current) > 1e-9:
            changes.append((key, fmt_num(nxt), reason or "tick"))
            stats[key] = fmt_num(nxt)

        peak_key = peak_since_key(key)
        at_peak = abs(float(stats.get(key, nxt)) - float(dyn["max"])) < 1e-6
        if dyn["kind"] == "buildup" and at_peak:
            if events_match(dyn["extend_on"], fired) or not stats.get(peak_key):
                changes.append((peak_key, str(int(now_minutes)), "peak"))
                stats[peak_key] = str(int(now_minutes))
        elif stats.get(peak_key):
            changes.append((peak_key, "", "clear_peak"))
            stats.pop(peak_key, None)
    return changes


def peak_hold_note(stats: dict[str, str], stat_key: str, dyn: dict[str, Any], now_minutes: int) -> str:
    raw = stats.get(peak_since_key(stat_key))
    if raw is None:
        return ""
    try:
        held = max(0, int(now_minutes) - int(float(raw)))
    except (TypeError, ValueError):
        return ""
    return f"at peak {held} / ~{dyn['peak_hold_minutes']} min"
