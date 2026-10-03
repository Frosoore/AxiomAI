"""axiom/universe_format.py

Storage format of universe data that the kernel's universe compiler writes and the
mods read back: the calendar of `universe.toml` (kept in ``Universe_Meta['calendar_config']``)
and the temporary-stat profile of a stat definition (kept in its ``parameters``).

Only the FORMAT lives here (keys, defaults, folding): the calendar arithmetic is
the `axiom.time` mod, the stat dynamics engine is the `core.stat_dynamics` mod.
"""

from __future__ import annotations

import json
from typing import Any

DEFAULT_MONTHS = 12
CALENDAR_DEFAULTS: dict[str, Any] = {
    "minutes_per_hour": 60,
    "hours_per_day": 24,
    "days_per_month": [30] * DEFAULT_MONTHS,
    "month_names": [f"Month {i + 1}" for i in range(DEFAULT_MONTHS)],
    "start_day": 1,
    "start_hour": 0,
    "start_minute": 0,
}

# universe.toml [calendar] key -> compact key stored in Universe_Meta.
_CALENDAR_KEYS = {
    "minutes_per_hour": "mph",
    "hours_per_day": "hpd",
    "days_per_month": "dpm",
    "month_names": "months",
    "start_day": "sd",
    "start_hour": "sh",
    "start_minute": "sm",
}

_INT_FIELDS = ("minutes_per_hour", "hours_per_day", "start_day", "start_hour", "start_minute")


def calendar_fields(table: dict[str, Any] | None) -> dict[str, Any]:
    """A `[calendar]` table with every field, defaults filled in, normalised types."""
    table = table or {}
    out: dict[str, Any] = {}
    for key, default in CALENDAR_DEFAULTS.items():
        value = table.get(key, default)
        if key in _INT_FIELDS:
            value = int(value)
        else:
            value = list(value)
        out[key] = value
    return out


def calendar_to_meta(table: dict[str, Any] | None) -> str:
    """`[calendar]` table -> the JSON stored in ``Universe_Meta['calendar_config']``."""
    fields = calendar_fields(table)
    return json.dumps({_CALENDAR_KEYS[k]: fields[k] for k in _CALENDAR_KEYS})


def calendar_from_meta(raw: str | None) -> dict[str, Any]:
    """``Universe_Meta['calendar_config']`` JSON -> `[calendar]` fields (defaults if unreadable)."""
    try:
        data = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {k: data.get(short, CALENDAR_DEFAULTS[k]) for k, short in _CALENDAR_KEYS.items()}


# Keys of a stat definition that describe a temporary stat (TOML top level).
STAT_DYNAMICS_KEYS = (
    "kind", "pace", "resting", "heal_minutes", "peak_hold_minutes",
    "crash_on", "extend_on", "basis",
)


def parameters_as_dict(raw: Any) -> dict[str, Any]:
    """A stat definition's ``parameters`` (dict or JSON text) as a dict."""
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def fold_stat_parameters(entry: dict[str, Any]) -> dict[str, Any]:
    """Lift top-level TOML ``temporary`` / ``dynamics`` keys into ``parameters``."""
    params = parameters_as_dict(entry.get("parameters"))
    if "temporary" in entry:
        params["temporary"] = bool(entry["temporary"])
    dyn = params.get("dynamics")
    if not isinstance(dyn, dict):
        dyn = {}
    if isinstance(entry.get("dynamics"), dict):
        dyn = {**dyn, **entry["dynamics"]}
    for key in STAT_DYNAMICS_KEYS:
        if key in entry:
            dyn[key] = entry[key]
    if dyn:
        params["dynamics"] = dyn
        if "temporary" not in params:
            params["temporary"] = True
    return params
