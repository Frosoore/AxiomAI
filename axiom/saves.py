"""axiom.saves — save editing (creatable/editable by humans or LLMs).

Design decisions:

- **D1**: the `Event_Log` journal stays the **source of truth** (it powers
  the rewind). Editing happens *on top of it*: the state is **materialised**
  at a point (replay), **forked** (truncated journal), and an edited state
  is **imported** as a **new** save ("genesis" events at turn 0). Derived
  data (State_Cache/Snapshots) is never edited directly.
- **D3**: an imported save starts with an **empty vector memory** (it fills
  up as you play).

Point selector: by **turn** (`at_turn`) or by **in-game time in minutes**
(`at_minute`, resolved through the `Timeline` table). Zero Qt dependency.

Editable text format, `save_state.toml`::

    [save]      player_name / difficulty / player_persona
    [point]     turn_id / in_game_minutes   (informative at export)
    [state.<entity_id>]   stat = "value"    (effective entity state)
    [[inventory]]         item_id / quantity / holder_kind / holder_id   (axiom.inventory)
    [[modifiers]]         entity_id / stat_key / delta / minutes_remaining   (core.stat_dynamics)
    (sections of the mods, written and read by their storage code)
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

import tomlkit

from axiom.db_helpers import create_new_save
from axiom.events import EventSourcer
from axiom.schema import get_connection


class SaveError(Exception):
    """Save editing/reading error."""


# ---------------------------------------------------------------------------
# Résolution d'un point (tour ou minute in-game)
# ---------------------------------------------------------------------------

def _max_turn(conn: sqlite3.Connection, save_id: str) -> int:
    row = conn.execute(
        "SELECT MAX(turn_id) FROM Event_Log WHERE save_id = ?;", (save_id,)
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def resolve_point(
    db_path: str,
    save_id: str,
    *,
    at_turn: int | None = None,
    at_minute: int | None = None,
) -> int:
    """Resolve a selector (turn or in-game minute) into a `turn_id`.

    - `at_turn`: used as-is.
    - `at_minute`: last turn whose `Timeline.in_game_time <= at_minute`.
    - neither: last turn of the save.
    """
    if at_turn is not None and at_minute is not None:
        raise SaveError("Specify either at_turn or at_minute, not both.")
    with get_connection(db_path) as conn:
        if at_turn is not None:
            return int(at_turn)
        if at_minute is not None:
            row = conn.execute(
                "SELECT MAX(turn_id) FROM Timeline WHERE save_id = ? AND in_game_time <= ?;",
                (save_id, int(at_minute)),
            ).fetchone()
            return int(row[0]) if row and row[0] is not None else 0
        return _max_turn(conn, save_id)


def _in_game_minutes_at(conn: sqlite3.Connection, save_id: str, turn_id: int) -> int:
    row = conn.execute(
        "SELECT in_game_time FROM Timeline WHERE save_id = ? AND turn_id <= ? "
        "ORDER BY turn_id DESC LIMIT 1;",
        (save_id, turn_id),
    ).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


# ---------------------------------------------------------------------------
# Matérialisation de l'état (lecture)
# ---------------------------------------------------------------------------

def _materialize_sections(
    conn: sqlite3.Connection, save_id: str, turn_id: int
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, bool]]:
    """{section: rows} and {section: historical} of the mods' data at ``turn_id``."""
    from axiom.storage_registry import _table_exists, get_state_sections

    present = turn_id >= _max_turn(conn, save_id)
    rows: dict[str, list[dict[str, Any]]] = {}
    historical: dict[str, bool] = {}
    for spec in get_state_sections():
        if spec.custom_state is None or not _table_exists(conn, spec.table_name):
            continue
        rows[spec.section], historical[spec.section] = spec.custom_state(conn, save_id, turn_id, present)
    return rows, historical


def _load_sections(
    conn: sqlite3.Connection, save_id: str, data: dict[str, Any], turn_id: int, *, replace_all: bool
) -> bool:
    """Hand each mod section of ``data`` to its storage code (import: replace; correction:
    ``<section>_replace`` flags). Then capture the present turn again, so a later
    rewind to it keeps the edit. Returns True if a section was written."""
    from axiom.storage_registry import _table_exists, execute_snapshots, get_state_sections

    written = False
    for spec in get_state_sections():
        if spec.custom_load is None or spec.section not in data or not _table_exists(conn, spec.table_name):
            continue
        replace = replace_all or bool(data.get(f"{spec.section}_replace"))
        spec.custom_load(conn, save_id, list(data.get(spec.section) or []), turn_id, replace)
        written = True
    if written:
        execute_snapshots(conn, save_id, _max_turn(conn, save_id))
    return written


def _toml_value_rows(rows: list[dict[str, Any]]) -> Any:
    """A section as a TOML array of tables (empty / None / False values left out)."""
    aot = tomlkit.aot()
    for row in rows:
        t = tomlkit.table()
        for k, v in row.items():
            if v is None or v == "" or v is False:
                continue
            t[k] = v
        aot.append(t)
    return aot


def materialize_state(
    db_path: str,
    save_id: str,
    *,
    at_turn: int | None = None,
    at_minute: int | None = None,
) -> dict[str, Any]:
    """Materialise a save's state at a given point (by replaying the journal).

    Per-entity stats = the universe's base stats (`Entity_Stats`) overlaid
    with the state replayed up to the point (logical `State_Cache`).

    Session_Lore is reconstructed at the point too (TICKET-095): entries are
    filtered by `origin_turn <= turn_id`. The data of the mods (e.g.
    ``inventory``, ``modifiers``) are added as named sections by their storage
    code (``[storage]`` ``section`` / ``state``), from the same snapshots a rewind
    restores. The returned `historical` dict flags, per facet, whether the value
    shown is truly the point-in-time state (`True`) or the save's present state
    (`False`, e.g. an inventory turn played before snapshots existed), so callers
    can warn the user.
    """
    turn_id = resolve_point(db_path, save_id, at_turn=at_turn, at_minute=at_minute)
    sourcer = EventSourcer(db_path)
    replayed = sourcer.state_at(save_id, up_to_turn_id=turn_id)

    with get_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        save_row = conn.execute(
            "SELECT player_name, difficulty, player_persona FROM Saves WHERE save_id = ?;",
            (save_id,),
        ).fetchone()
        if save_row is None:
            raise SaveError(f"Save not found: {save_id}")

        # Stats de base (définition d'univers) par entité active.
        base: dict[str, dict[str, str]] = {}
        for r in conn.execute(
            "SELECT es.entity_id, es.stat_key, es.stat_value FROM Entity_Stats es "
            "JOIN Entities e ON e.entity_id = es.entity_id WHERE e.is_active = 1;"
        ):
            base.setdefault(r["entity_id"], {})[r["stat_key"]] = r["stat_value"]

        session_lore = []
        try:
            session_lore = [
                {
                    "entry_id": r["entry_id"],
                    "category": r["category"] or "",
                    "name": r["name"] or "",
                    "keywords": r["keywords"] or "",
                    "content": r["content"] or "",
                    "origin_turn": int(r["origin_turn"] or 0),
                }
                for r in conn.execute(
                    "SELECT entry_id, category, name, keywords, content, origin_turn "
                    "FROM Session_Lore WHERE save_id = ? AND origin_turn <= ? "
                    "ORDER BY name;",
                    (save_id, turn_id),
                )
            ]
        except sqlite3.Error:
            session_lore = []

        entity_meta: dict[str, dict[str, str]] = {}
        try:
            ent_cols = {c[1] for c in conn.execute("PRAGMA table_info(Entities);")}
            role_sel = "entity_role" if "entity_role" in ent_cols else "entity_type"
            for r in conn.execute(
                f"SELECT entity_id, name, entity_type, "
                f"{role_sel} AS entity_role "
                f"FROM Entities WHERE is_active = 1;"
            ):
                entity_meta[r["entity_id"]] = {
                    "name": r["name"] or r["entity_id"],
                    "entity_type": r["entity_type"] or "npc",
                    "entity_role": r["entity_role"] or "npc",
                }
        except sqlite3.Error:
            entity_meta = {}
        # Data sections of the mods (inventory, modifiers...): read by their
        # storage code, mod enabled or not (owner decision 2026-10-03).
        sections, sections_historical = _materialize_sections(conn, save_id, turn_id)
        in_game_minutes = _in_game_minutes_at(conn, save_id, turn_id)

    # Fusion base ⊕ état rejoué (le replay prévaut). Fold incoming keys onto
    # the authored ones so `arousal` does not sit beside `Arousal`.
    from axiom.events import resolve_stat_key

    entities: dict[str, dict[str, str]] = {eid: dict(stats) for eid, stats in base.items()}
    for eid, stats in replayed.items():
        dest = entities.setdefault(eid, {})
        for key, value in stats.items():
            dest[resolve_stat_key(key, dest)] = value

    return {
        "save": {
            "player_name": save_row["player_name"],
            "difficulty": save_row["difficulty"],
            "player_persona": save_row["player_persona"] or "",
        },
        "point": {"turn_id": turn_id, "in_game_minutes": in_game_minutes},
        "entities": entities,
        "entity_meta": entity_meta,
        "session_lore": session_lore,
        **sections,
        "historical": {"entities": True, "session_lore": True, **sections_historical},
    }


# ---------------------------------------------------------------------------
# Export / import TOML
# ---------------------------------------------------------------------------

def export_save_state(
    db_path: str,
    save_id: str,
    out_path: str | Path,
    *,
    at_turn: int | None = None,
    at_minute: int | None = None,
) -> Path:
    """Export a save's materialised state to an editable `save_state.toml`."""
    state = materialize_state(db_path, save_id, at_turn=at_turn, at_minute=at_minute)
    doc = tomlkit.document()

    save_tbl = tomlkit.table()
    save_tbl["player_name"] = state["save"]["player_name"]
    save_tbl["difficulty"] = state["save"]["difficulty"]
    save_tbl["player_persona"] = state["save"]["player_persona"]
    doc["save"] = save_tbl

    point_tbl = tomlkit.table()
    point_tbl["turn_id"] = state["point"]["turn_id"]
    point_tbl["in_game_minutes"] = state["point"]["in_game_minutes"]
    doc["point"] = point_tbl

    state_tbl = tomlkit.table()
    for eid, stats in state["entities"].items():
        ent = tomlkit.table()
        for k, v in stats.items():
            ent[k] = v
        state_tbl[eid] = ent
    doc["state"] = state_tbl

    if state.get("session_lore"):
        lore = tomlkit.aot()
        for entry in state["session_lore"]:
            t = tomlkit.table()
            t["entry_id"] = entry.get("entry_id") or ""
            t["category"] = entry.get("category") or ""
            t["name"] = entry.get("name") or ""
            t["keywords"] = entry.get("keywords") or ""
            t["content"] = entry.get("content") or ""
            lore.append(t)
        doc["session_lore"] = lore

    from axiom.storage_registry import get_state_sections
    for spec in get_state_sections():
        if state.get(spec.section):
            doc[spec.section] = _toml_value_rows(state[spec.section])

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(tomlkit.dumps(doc), encoding="utf-8", newline="")
    return out_path


def _load_state_toml(path: str | Path) -> dict[str, Any]:
    import tomllib
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise SaveError(f"Invalid save_state.toml: {exc}") from exc


def import_save_state(
    db_path: str,
    state_path: str | Path,
    *,
    player_name: str | None = None,
) -> str:
    """Create a **new** playable save from a `save_state.toml`.

    Seeds the state through "genesis" events at turn 0 (entity_create +
    stat_set), then materialises State_Cache, the mods' sections (inventory,
    modifiers...) and a Timeline entry. Empty vector memory. Returns the new save_id.
    """
    data = _load_state_toml(state_path)
    save_meta = data.get("save", {})
    name = player_name or save_meta.get("player_name", "Hero")
    difficulty = save_meta.get("difficulty", "Normal")
    persona = save_meta.get("player_persona", "")

    save_id = create_new_save(db_path, name, difficulty, persona)
    sourcer = EventSourcer(db_path)

    # Events genesis au tour 0.
    events: list[tuple[str, int, str, str, dict]] = []
    for eid, stats in data.get("state", {}).items():
        events.append((save_id, 0, "entity_create", eid, {"entity_id": eid}))
        for stat_key, value in stats.items():
            events.append((
                save_id, 0, "stat_set", eid,
                {"entity_id": eid, "stat_key": stat_key, "value": str(value)},
            ))
    if events:
        sourcer.append_events_batch(events)
    sourcer.rebuild_state_cache(save_id)

    in_game_minutes = int(data.get("point", {}).get("in_game_minutes", 0))
    try:
        with get_connection(db_path) as conn:
            from axiom.schema import migrate_schema
            migrate_schema(db_path)
            _replace_session_lore(conn, save_id, list(data.get("session_lore") or []), turn_id=0)
            _load_sections(conn, save_id, data, 0, replace_all=True)
            conn.execute(
                "INSERT INTO Timeline (save_id, turn_id, in_game_time, description) "
                "VALUES (?, ?, ?, ?);",
                (save_id, 0, in_game_minutes, "Save imported"),
            )
            conn.commit()
    except (sqlite3.Error, KeyError) as exc:
        raise SaveError(f"Import failed (invalid reference?): {exc}") from exc

    sourcer.take_snapshot(save_id, 0)
    return save_id


# ---------------------------------------------------------------------------
# Correction d'une save existante (édition en place, append-only)
# ---------------------------------------------------------------------------

def apply_correction(
    db_path: str,
    save_id: str,
    patch: dict[str, Any],
    *,
    at_turn: int | None = None,
) -> int:
    """Apply a correction to an **existing** save without rewriting the past.

    Stat changes become `manual_edit` events (at the chosen turn, default =
    last turn) — the journal stays consistent and append-only, the rewind is
    preserved, and the edit is traceable. The mods' sections (not
    event-sourced: inventory, modifiers...) are written by their storage code.

    The `patch` dict has the shape::

        {
            "entities":  {entity_id: {stat_key: "value", ...}},
            "session_lore": [...],              # replaces the session lore
            "<section>": [rows...],             # e.g. inventory, modifiers
            "<section>_replace": True,          # replace the section instead of patching
        }

    Returns:
        The `turn_id` the correction was appended at.
    """
    turn_id = resolve_point(db_path, save_id, at_turn=at_turn)
    sourcer = EventSourcer(db_path)

    with get_connection(db_path) as conn:
        if conn.execute("SELECT 1 FROM Saves WHERE save_id = ?;", (save_id,)).fetchone() is None:
            raise SaveError(f"Save not found: {save_id}")

    from axiom.events import resolve_stat_key, stat_key_aliases_from_definitions

    current = materialize_state(db_path, save_id, at_turn=turn_id)
    current_entities: dict[str, dict[str, str]] = current.get("entities") or {}
    aliases: dict[str, str] = {}
    with get_connection(db_path) as conn:
        aliases = stat_key_aliases_from_definitions(conn)

    events: list[tuple[str, int, str, str, dict]] = []
    for eid, stats in patch.get("entities", {}).items():
        existing = current_entities.get(eid, {})
        written: dict[str, str] = {}
        for stat_key, value in stats.items():
            canon = resolve_stat_key(str(stat_key), existing, aliases)
            written[canon] = str(value)
        for stat_key, value in written.items():
            if str(existing.get(stat_key, "")) == value:
                continue
            events.append((
                save_id, turn_id, "manual_edit", eid,
                {"entity_id": eid, "stat_key": stat_key, "value": value},
            ))
    if events:
        sourcer.append_events_batch(events)

    try:
        with get_connection(db_path) as conn:
            if "session_lore" in patch:
                _replace_session_lore(
                    conn, save_id, list(patch.get("session_lore") or []), turn_id=turn_id
                )
            _load_sections(conn, save_id, patch, turn_id, replace_all=False)
            conn.commit()
    except (sqlite3.Error, KeyError) as exc:
        raise SaveError(f"Correction failed (invalid reference?): {exc}") from exc

    sourcer.rebuild_state_cache(save_id)
    return turn_id


def _replace_session_lore(
    conn: sqlite3.Connection,
    save_id: str,
    entries: list[dict[str, Any]],
    *,
    turn_id: int = 0,
) -> None:
    """Replace this save's Session_Lore with the given entries."""
    try:
        conn.execute("DELETE FROM Session_Lore WHERE save_id = ?;", (save_id,))
    except sqlite3.Error:
        return
    for entry in entries:
        name = str(entry.get("name") or "").strip()
        content = str(entry.get("content") or "").strip()
        if not name and not content:
            continue
        entry_id = str(entry.get("entry_id") or "").strip() or str(uuid.uuid4())
        conn.execute(
            "INSERT INTO Session_Lore "
            "(entry_id, save_id, category, name, keywords, content, origin_turn) "
            "VALUES (?, ?, ?, ?, ?, ?, ?);",
            (
                entry_id,
                save_id,
                str(entry.get("category") or ""),
                name,
                str(entry.get("keywords") or ""),
                content,
                int(entry.get("origin_turn") or turn_id or 0),
            ),
        )


def apply_structured_state(
    db_path: str,
    save_id: str,
    payload: dict[str, Any],
) -> int:
    """Apply a structured save-editor payload (full replace of the given sections / lore)."""
    from axiom.schema import migrate_schema

    migrate_schema(db_path)
    patch: dict[str, Any] = {}
    if payload.get("entities"):
        patch["entities"] = payload["entities"]
    if "session_lore" in payload:
        patch["session_lore"] = payload["session_lore"]
    from axiom.storage_registry import get_state_sections
    for spec in get_state_sections():
        if spec.section in payload:
            patch[spec.section] = payload[spec.section]
            patch[f"{spec.section}_replace"] = True
    if not patch:
        return resolve_point(db_path, save_id)
    return apply_correction(db_path, save_id, patch)


def diff_save_states(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compute the correction patch between two parsed `save_state.toml` states.

    Supports the "edit the save" flow: the state is exported, the user edits
    the TOML, and only the **differences** are appended via `apply_correction`
    (otherwise every unchanged stat would become a spurious `manual_edit`
    event).

    - stats: changed or added values (removing a stat does not exist in the
      correction model — ignored);
    - the mods' sections: as their storage code's ``diff`` says (inventory:
      changed/added/removed lines; modifiers: only new ones).
    """
    entities: dict[str, dict[str, str]] = {}
    state_before = before.get("state", {})
    for eid, stats in after.get("state", {}).items():
        prior = state_before.get(eid, {})
        changed = {k: v for k, v in stats.items() if str(prior.get(k)) != str(v)}
        if changed:
            entities[eid] = changed

    lore_before = before.get("session_lore") or []
    lore_after = after.get("session_lore") or []
    patch: dict[str, Any] = {"entities": entities}
    from axiom.storage_registry import get_state_sections
    for spec in get_state_sections():
        if spec.custom_diff is not None and (spec.section in before or spec.section in after):
            patch[spec.section] = spec.custom_diff(
                list(before.get(spec.section) or []), list(after.get(spec.section) or [])
            )
    if lore_before != lore_after:
        patch["session_lore"] = lore_after
    return patch


def apply_correction_file(db_path: str, save_id: str, patch_path: str | Path, *, at_turn: int | None = None) -> int:
    """Load a TOML file (same sections as save_state.toml) and apply it as a correction."""
    data = _load_state_toml(patch_path)
    patch = {"entities": data.get("state", {})}
    # session_lore and the mods' sections (inventory, modifiers...) as written.
    patch.update({k: v for k, v in data.items() if k not in ("save", "point", "state")})
    return apply_correction(db_path, save_id, patch, at_turn=at_turn)


# ---------------------------------------------------------------------------
# Fork (découpe du journal à un point)
# ---------------------------------------------------------------------------

def fork_save(
    db_path: str,
    save_id: str,
    *,
    at_turn: int | None = None,
    at_minute: int | None = None,
    player_name: str | None = None,
) -> str:
    """Create a new save = `save_id`'s journal **truncated** at the chosen point.

    Every runtime table is copied through the storage registry
    (`axiom.storage_registry.execute_fork`): the journal and the step-keyed
    tables up to the point, and the snapshot-based state (inventory, modifiers,
    beliefs, mental models) as it was at the point. If the copy fails, the new
    save is deleted and the error propagates (no half-forked save).
    Returns the new save_id.
    """
    turn_id = resolve_point(db_path, save_id, at_turn=at_turn, at_minute=at_minute)

    with get_connection(db_path) as conn:
        conn.row_factory = sqlite3.Row
        src = conn.execute(
            "SELECT player_name, difficulty, player_persona FROM Saves WHERE save_id = ?;",
            (save_id,),
        ).fetchone()
        if src is None:
            raise SaveError(f"Save not found: {save_id}")

    new_id = create_new_save(
        db_path,
        player_name or src["player_name"],
        src["difficulty"],
        src["player_persona"] or "",
    )

    from axiom.storage_registry import execute_external_fork, execute_fork

    try:
        with get_connection(db_path) as conn:
            execute_fork(conn, save_id, new_id, turn_id, external=False)
            conn.commit()
    except Exception:
        with get_connection(db_path) as conn:
            conn.execute("DELETE FROM Saves WHERE save_id = ?;", (new_id,))
            conn.commit()
        raise
    execute_external_fork(save_id, new_id, turn_id)

    # The source's Snapshots <= turn were copied with the other step-keyed
    # tables: only the derived State_Cache is rebuilt.
    EventSourcer(db_path).rebuild_state_cache(new_id, up_to_turn_id=turn_id)
    return new_id
