"""mods/core.stat_dynamics/storage.py

Save data of core.stat_dynamics: the live temporary modifiers (Active_Modifiers)
and their per-turn snapshots (Modifier_Snapshots). Declared in mod.toml and run by
the kernel even while the mod is disabled (owner decision 2026-10-03): only this
module is loaded then.

Modifiers decay in minutes (not event-sourced): the state at turn N only exists in
the snapshot of turn N (no row = no modifiers then).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from mods.core.stat_dynamics.modifiers import rollback_modifiers


def _present_turn(conn: sqlite3.Connection, save_id: str) -> int:
    row = conn.execute("SELECT MAX(turn_id) FROM Event_Log WHERE save_id = ?;", (save_id,)).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def rewind_modifiers(conn: sqlite3.Connection, save_id: str, target_turn: int) -> None:
    rollback_modifiers(conn, save_id, target_turn)


def fork_modifiers(
    conn: sqlite3.Connection, src_save_id: str, dst_save_id: str, target_turn: int,
    *, id_maps: dict[str, dict[Any, Any]],
) -> None:
    """Active_Modifiers at the fork point + the Modifier_Snapshots <= N.

    Custom because modifiers decay in minutes (not event-sourced): the state at N
    only exists in the snapshot of turn N, and the snapshots store modifier ids
    (JSON) that must follow the regenerated ids (one mapping for both).
    """
    from axiom.schema import ensure_modifier_snapshots_table

    ensure_modifier_snapshots_table(conn)
    id_map: dict[str, str] = {}

    def _new(old: Any) -> str:
        key = str(old)
        if key not in id_map:
            id_map[key] = str(uuid.uuid4())
        return id_map[key]

    if target_turn < _present_turn(conn, src_save_id):
        # Same lookup as modifiers_at / rollback_modifiers. No snapshot row for
        # turn N means "no modifiers then": never fall back on the present
        # modifiers (they belong to later turns).
        row = conn.execute(
            "SELECT state_json FROM Modifier_Snapshots WHERE save_id = ? AND turn_id = ?;",
            (src_save_id, target_turn),
        ).fetchone()
        mod_rows = json.loads(row[0]) if row and row[0] else []
    else:
        mod_rows = [
            dict(r) for r in conn.execute(
                "SELECT modifier_id, entity_id, stat_key, delta, minutes_remaining "
                "FROM Active_Modifiers WHERE save_id = ?;",
                (src_save_id,),
            ).fetchall()
        ]

    conn.executemany(
        "INSERT INTO Active_Modifiers (modifier_id, save_id, entity_id, stat_key, delta, minutes_remaining) "
        "VALUES (?, ?, ?, ?, ?, ?);",
        [(_new(r["modifier_id"]), dst_save_id, r["entity_id"], r["stat_key"], r["delta"],
          r["minutes_remaining"]) for r in mod_rows],
    )
    for snap in conn.execute(
        "SELECT turn_id, state_json FROM Modifier_Snapshots WHERE save_id = ? AND turn_id <= ?;",
        (src_save_id, target_turn),
    ).fetchall():
        state = [{**m, "modifier_id": _new(m["modifier_id"])} for m in json.loads(snap[1] or "[]")]
        conn.execute(
            "INSERT OR REPLACE INTO Modifier_Snapshots (save_id, turn_id, state_json) VALUES (?, ?, ?);",
            (dst_save_id, snap[0], json.dumps(state)),
        )
    id_maps["Active_Modifiers"] = id_map


def snapshot_modifiers(conn: sqlite3.Connection, save_id: str, turn_id: int) -> None:
    """End-of-turn capture (kernel, every turn, mod enabled or not): the modifiers of
    the save at the end of ``turn_id``. No row when there are none (= "no modifiers")."""
    from axiom.schema import ensure_modifier_snapshots_table

    rows = conn.execute(
        "SELECT modifier_id, entity_id, stat_key, delta, minutes_remaining "
        "FROM Active_Modifiers WHERE save_id = ?;",
        (save_id,),
    ).fetchall()
    ensure_modifier_snapshots_table(conn)
    if not rows:
        conn.execute(
            "DELETE FROM Modifier_Snapshots WHERE save_id = ? AND turn_id = ?;", (save_id, turn_id)
        )
        return
    state = [
        {"modifier_id": r[0], "entity_id": r[1], "stat_key": r[2], "delta": r[3], "minutes_remaining": r[4]}
        for r in rows
    ]
    conn.execute(
        "INSERT OR REPLACE INTO Modifier_Snapshots (save_id, turn_id, state_json) VALUES (?, ?, ?);",
        (save_id, turn_id, json.dumps(state)),
    )


# ---------------------------------------------------------------------------
# Save-editor section "modifiers" (materialize, TOML export/import, corrections)
# ---------------------------------------------------------------------------

def _modifier_row(m: Any) -> dict[str, Any]:
    return {
        "entity_id": m["entity_id"],
        "stat_key": m["stat_key"],
        "delta": m["delta"],
        "minutes_remaining": m["minutes_remaining"],
    }


def state_modifiers(
    conn: sqlite3.Connection, save_id: str, turn_id: int, present: bool
) -> tuple[list[dict[str, Any]], bool]:
    """Modifiers at ``turn_id``: live at the present turn (edits made outside a turn
    show at once), else the turn's snapshot (no row = none then)."""
    if present:
        rows = [
            _modifier_row(r) for r in conn.execute(
                "SELECT entity_id, stat_key, delta, minutes_remaining FROM Active_Modifiers "
                "WHERE save_id = ?;",
                (save_id,),
            ).fetchall()
        ]
    else:
        from axiom.schema import ensure_modifier_snapshots_table
        ensure_modifier_snapshots_table(conn)
        row = conn.execute(
            "SELECT state_json FROM Modifier_Snapshots WHERE save_id = ? AND turn_id = ?;",
            (save_id, turn_id),
        ).fetchone()
        rows = [_modifier_row(m) for m in json.loads(row[0])] if row and row[0] else []
    rows.sort(key=lambda m: (m["entity_id"], m["stat_key"]))
    return rows, True


def load_modifiers(
    conn: sqlite3.Connection, save_id: str, rows: list[dict[str, Any]], turn_id: int, replace: bool
) -> None:
    """Import / correction: add the given modifiers (after clearing them all if ``replace``)."""
    if replace:
        conn.execute("DELETE FROM Active_Modifiers WHERE save_id = ?;", (save_id,))
    conn.executemany(
        "INSERT INTO Active_Modifiers (modifier_id, save_id, entity_id, stat_key, delta, minutes_remaining) "
        "VALUES (?, ?, ?, ?, ?, ?);",
        [
            (str(uuid.uuid4()), save_id, m["entity_id"], m["stat_key"],
             float(m["delta"]), int(m.get("minutes_remaining", 0)))
            for m in rows
        ],
    )


def diff_modifiers(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Only the new modifiers (a correction can only add modifiers)."""
    def key(m: dict) -> tuple:
        return (m["entity_id"], m["stat_key"], float(m["delta"]), int(m.get("minutes_remaining", 0)))

    known = {key(m) for m in before}
    return [m for m in after if key(m) not in known]
