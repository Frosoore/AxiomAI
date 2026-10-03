"""Per-character belief missions (Phase 4, B-3).

A *belief mission* is a memory style for the consolidator: what a character
tends to remember and dwell on (a rancorous NPC remembers betrayals, a merchant
remembers transactions, a loyal guard remembers favours). It biases which
beliefs :mod:`axiom.consolidate` forms about each subject, so NPCs "remember
differently" according to their nature.

Stored in ``Universe_Meta`` (no schema change; it round-trips losslessly through
the Universe-as-Code ``[extra]`` mechanism, is copied into saves, and is
packaged):

- ``belief_mission``  — the universe-wide default mission (one string);
- ``belief_missions`` — JSON ``{entity_name: mission}`` per-character overrides.

Keyed by entity *name* because a belief's ``subject`` is a name and authoring
"Name: mission" is natural. Reading degrades gracefully (missing/blank/malformed
→ sensible empties) so the consolidator always has something usable.
"""

from __future__ import annotations

import json

from axiom.schema import get_connection


def _read_meta(db_path: str, key: str) -> str:
    try:
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT value FROM Universe_Meta WHERE key = ?;", (key,)
            ).fetchone()
        return str(row[0]) if row and row[0] is not None else ""
    except Exception:
        return ""


def get_universe_mission(db_path: str) -> str:
    """The universe-wide default belief mission ("" when unset)."""
    return _read_meta(db_path, "belief_mission").strip()


def get_belief_missions_from_value(raw: str) -> dict[str, str]:
    """Parse a ``belief_missions`` JSON value into ``{entity_name: mission}``.

    Tolerates blank/malformed JSON or non-string values — anything unusable is
    dropped rather than raised. Used when the meta value is already in hand (e.g.
    the Studio's loaded meta dict).
    """
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, str] = {}
    for name, mission in data.items():
        name_s = str(name).strip()
        mission_s = str(mission).strip()
        if name_s and mission_s:
            out[name_s] = mission_s
    return out


def get_belief_missions(db_path: str) -> dict[str, str]:
    """Per-character missions as ``{entity_name: mission}`` read from the DB."""
    return get_belief_missions_from_value(_read_meta(db_path, "belief_missions"))


def parse_missions_text(text: str) -> dict[str, str]:
    """Parse a 'Name: mission' per-line block into ``{name: mission}``.

    The GUI Metadata field stores missions this way (one entity per line). Lines
    without a colon, or with an empty name/mission, are skipped. The first colon
    splits — a mission may itself contain colons.
    """
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        name, _, mission = line.partition(":")
        name, mission = name.strip(), mission.strip()
        if name and mission:
            out[name] = mission
    return out


def missions_to_text(missions: dict[str, str]) -> str:
    """Inverse of :func:`parse_missions_text` for displaying in the GUI field."""
    return "\n".join(f"{name}: {mission}" for name, mission in missions.items())
