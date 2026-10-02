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
    [[inventory]]         entity_id / item_id / quantity
    [[modifiers]]         entity_id / stat_key / delta / minutes_remaining
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

    Session_Lore and modifiers are reconstructed at the point too (TICKET-095):
    lore entries are filtered by `origin_turn <= turn_id`, and modifiers are
    read live from `Active_Modifiers` when `turn_id` is the save's present
    turn (nothing to reconstruct there), or otherwise from the same
    `Modifier_Snapshots` table rewind restores from (see
    `axiom.modifiers.modifiers_at`), read-only. Inventory at a past turn comes
    from `Inventory_Snapshots` (`axiom.inventory.inventory_at`, the source
    rewind restores from); a turn played before snapshots existed has none and
    shows the save's **current** inventory (`historical["inventory"]` False).
    The returned
    `historical` dict flags, per facet, whether the value shown is truly the
    point-in-time state (`True`) or the save's present state (`False`), so
    callers can warn the user.
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

        from axiom.inventory import list_instances

        inventory = list_instances(conn, save_id)
        # TICKET-095: a past turn reads the per-turn inventory snapshot (same
        # source rewind restores from); the present turn and turns captured
        # before snapshots existed show the live inventory.
        inventory_historical = turn_id >= _max_turn(conn, save_id)
        from_snapshot = False
        if not inventory_historical:
            from axiom.inventory import inventory_at

            past = inventory_at(conn, save_id, turn_id)
            if past is not None:
                inventory = [
                    {**it, "entity_id": it["holder_id"]} if it.get("holder_kind") == "entity" else it
                    for it in past
                ]
                inventory_historical = from_snapshot = True
        if not inventory and not from_snapshot:
            inventory = [
                {
                    "entity_id": r["entity_id"],
                    "item_id": r["item_id"],
                    "quantity": r["quantity"],
                    "holder_kind": "entity",
                    "holder_id": r["entity_id"],
                }
                for r in conn.execute(
                    "SELECT entity_id, item_id, quantity FROM Items_Inventory WHERE save_id = ? "
                    "ORDER BY entity_id, item_id;",
                    (save_id,),
                )
            ]

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
        # At the save's present turn, Active_Modifiers *is* the point-in-time
        # state (nothing to reconstruct) — read it live so modifiers added
        # outside a turn tick (e.g. `apply_correction`, an import, a GM
        # command) show up immediately, without waiting for the next
        # `snapshot_modifiers` call. Only a genuinely past turn needs the
        # snapshot-based reconstruction (TICKET-095).
        if turn_id >= _max_turn(conn, save_id):
            modifiers = [
                {
                    "entity_id": r["entity_id"],
                    "stat_key": r["stat_key"],
                    "delta": r["delta"],
                    "minutes_remaining": r["minutes_remaining"],
                }
                for r in conn.execute(
                    "SELECT entity_id, stat_key, delta, minutes_remaining FROM Active_Modifiers "
                    "WHERE save_id = ? ORDER BY entity_id, stat_key;",
                    (save_id,),
                )
            ]
        else:
            from axiom.modifiers import modifiers_at

            modifiers = sorted(
                modifiers_at(conn, save_id, turn_id),
                key=lambda m: (m["entity_id"], m["stat_key"]),
            )
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
        "inventory": inventory,
        "session_lore": session_lore,
        "modifiers": modifiers,
        "historical": {
            "entities": True,
            "session_lore": True,
            "modifiers": True,
            "inventory": inventory_historical,
        },
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

    if state["inventory"]:
        inv = tomlkit.aot()
        for it in state["inventory"]:
            t = tomlkit.table()
            if it.get("instance_id"):
                t["instance_id"] = it["instance_id"]
            t["item_id"] = it["item_id"]
            t["quantity"] = it["quantity"]
            t["holder_kind"] = it.get("holder_kind") or "entity"
            t["holder_id"] = it.get("holder_id") or it.get("entity_id") or ""
            if it.get("entity_id"):
                t["entity_id"] = it["entity_id"]
            if it.get("is_container"):
                t["is_container"] = True
            if it.get("name"):
                t["name"] = it["name"]
            inv.append(t)
        doc["inventory"] = inv

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

    if state["modifiers"]:
        mods = tomlkit.aot()
        for m in state["modifiers"]:
            t = tomlkit.table()
            t["entity_id"] = m["entity_id"]
            t["stat_key"] = m["stat_key"]
            t["delta"] = m["delta"]
            t["minutes_remaining"] = m["minutes_remaining"]
            mods.append(t)
        doc["modifiers"] = mods

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
    stat_set), then materialises State_Cache, the inventory, the modifiers and
    a Timeline entry. Empty vector memory. Returns the new save_id.
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
            from axiom.inventory import replace_inventory
            from axiom.schema import migrate_schema
            migrate_schema(db_path)
            replace_inventory(conn, save_id, list(data.get("inventory") or []))
            _replace_session_lore(conn, save_id, list(data.get("session_lore") or []), turn_id=0)
            for m in data.get("modifiers", []):
                conn.execute(
                    "INSERT INTO Active_Modifiers "
                    "(modifier_id, save_id, entity_id, stat_key, delta, minutes_remaining) "
                    "VALUES (?, ?, ?, ?, ?, ?);",
                    (str(uuid.uuid4()), save_id, m["entity_id"], m["stat_key"],
                     float(m["delta"]), int(m.get("minutes_remaining", 0))),
                )
            _snapshot_modifiers_now(conn, save_id, 0)
            from axiom.inventory import snapshot_inventory
            snapshot_inventory(conn, save_id, 0)
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
    preserved, and the edit is traceable. Inventory and modifiers (not
    event-sourced) are written directly.

    The `patch` dict has the shape::

        {
            "entities":  {entity_id: {stat_key: "value", ...}},
            "inventory": [{entity_id, item_id, quantity}, ...],
            "modifiers": [{entity_id, stat_key, delta, minutes_remaining}, ...],
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
            if patch.get("inventory_replace"):
                from axiom.inventory import replace_inventory
                replace_inventory(conn, save_id, list(patch.get("inventory") or []))
            else:
                for it in patch.get("inventory", []):
                    _apply_inventory_row(conn, save_id, it)
            if "session_lore" in patch:
                _replace_session_lore(
                    conn, save_id, list(patch.get("session_lore") or []), turn_id=turn_id
                )
            if patch.get("modifiers_replace"):
                conn.execute("DELETE FROM Active_Modifiers WHERE save_id = ?;", (save_id,))
            for m in patch.get("modifiers", []):
                conn.execute(
                    "INSERT INTO Active_Modifiers "
                    "(modifier_id, save_id, entity_id, stat_key, delta, minutes_remaining) "
                    "VALUES (?, ?, ?, ?, ?, ?);",
                    (str(uuid.uuid4()), save_id, m["entity_id"], m["stat_key"],
                     float(m["delta"]), int(m.get("minutes_remaining", 0))),
                )
            if patch.get("modifiers_replace") or "modifiers" in patch:
                _snapshot_modifiers_now(conn, save_id, turn_id)
            if patch.get("inventory_replace") or "inventory" in patch:
                # Inventory is written live, i.e. as the save's present state:
                # re-capture the present turn so a later rewind to it keeps the
                # edit (TICKET-095).
                from axiom.inventory import snapshot_present_inventory
                snapshot_present_inventory(conn, save_id)
            conn.commit()
    except (sqlite3.Error, KeyError) as exc:
        raise SaveError(f"Correction failed (invalid reference?): {exc}") from exc

    sourcer.rebuild_state_cache(save_id)
    return turn_id


def _apply_inventory_row(conn: sqlite3.Connection, save_id: str, it: dict[str, Any]) -> None:
    """Apply one inventory patch row. Quantity is absolute (0 = remove)."""
    from axiom.inventory import ensure_item_definition

    qty = int(it.get("quantity", 1) or 0)
    holder_kind = it.get("holder_kind") or "entity"
    holder_id = it.get("holder_id") or it.get("entity_id") or ""
    item_id = it.get("item_id") or ""
    instance_id = it.get("instance_id")
    has_instances = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='Item_Instances';"
    ).fetchone()

    if qty <= 0:
        if has_instances:
            if instance_id:
                conn.execute(
                    "DELETE FROM Item_Instances WHERE save_id = ? AND instance_id = ?;",
                    (save_id, instance_id),
                )
            elif item_id and holder_id:
                conn.execute(
                    "DELETE FROM Item_Instances WHERE save_id = ? AND item_id = ? "
                    "AND holder_kind = ? AND holder_id = ?;",
                    (save_id, item_id, holder_kind, holder_id),
                )
        if holder_id and item_id:
            conn.execute(
                "DELETE FROM Items_Inventory WHERE save_id = ? AND entity_id = ? AND item_id = ?;",
                (save_id, holder_id, item_id),
            )
        return

    if has_instances and holder_id and item_id:
        item_id = ensure_item_definition(
            conn, item_id,
            name=str(it.get("name") or ""),
            is_container=bool(it.get("is_container")),
        )
        if instance_id:
            exists = conn.execute(
                "SELECT 1 FROM Item_Instances WHERE instance_id = ?;", (instance_id,)
            ).fetchone()
            if exists:
                conn.execute(
                    "UPDATE Item_Instances SET quantity = ?, holder_kind = ?, holder_id = ?, "
                    "item_id = ? WHERE instance_id = ?;",
                    (qty, holder_kind, holder_id, item_id, instance_id),
                )
                return
        existing = conn.execute(
            "SELECT instance_id FROM Item_Instances WHERE save_id = ? AND item_id = ? "
            "AND holder_kind = ? AND holder_id = ? LIMIT 1;",
            (save_id, item_id, holder_kind, holder_id),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE Item_Instances SET quantity = ? WHERE instance_id = ?;",
                (qty, existing[0]),
            )
        else:
            conn.execute(
                "INSERT INTO Item_Instances "
                "(instance_id, save_id, item_id, quantity, holder_kind, holder_id) "
                "VALUES (?, ?, ?, ?, ?, ?);",
                (instance_id or str(uuid.uuid4()), save_id, item_id, qty, holder_kind, holder_id),
            )
        return
    if holder_id and item_id:
        conn.execute(
            "INSERT OR REPLACE INTO Items_Inventory (save_id, entity_id, item_id, quantity) "
            "VALUES (?, ?, ?, ?);",
            (save_id, holder_id, item_id, qty),
        )


def _snapshot_modifiers_now(conn: sqlite3.Connection, save_id: str, turn_id: int) -> None:
    """Write a Modifier_Snapshots row for `turn_id` from the current Active_Modifiers.

    `materialize_state`/`axiom.modifiers.modifiers_at` (TICKET-095) reconstruct
    past modifiers from `Modifier_Snapshots`, same as rewind. Import and
    correction write `Active_Modifiers` directly (not through
    `ModifierProcessor.add_modifier`/`snapshot_modifiers`), so without this the
    edited modifiers would have no snapshot at their turn and look like "no
    modifiers then" once read back through `materialize_state`. Called on the
    caller's open transaction, after the Active_Modifiers writes, so it sees
    them uncommitted.
    """
    from axiom.schema import ensure_modifier_snapshots_table

    ensure_modifier_snapshots_table(conn)
    rows = conn.execute(
        "SELECT modifier_id, entity_id, stat_key, delta, minutes_remaining "
        "FROM Active_Modifiers WHERE save_id = ?;",
        (save_id,),
    ).fetchall()
    if rows:
        state = [
            {
                "modifier_id": r[0],
                "entity_id": r[1],
                "stat_key": r[2],
                "delta": r[3],
                "minutes_remaining": r[4],
            }
            for r in rows
        ]
        conn.execute(
            "INSERT OR REPLACE INTO Modifier_Snapshots (save_id, turn_id, state_json) "
            "VALUES (?, ?, ?);",
            (save_id, turn_id, json.dumps(state)),
        )
    else:
        conn.execute(
            "DELETE FROM Modifier_Snapshots WHERE save_id = ? AND turn_id = ?;",
            (save_id, turn_id),
        )


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
    """Apply a structured save-editor payload (full inventory / lore replace)."""
    from axiom.schema import migrate_schema

    migrate_schema(db_path)
    patch: dict[str, Any] = {}
    if payload.get("entities"):
        patch["entities"] = payload["entities"]
    if "inventory" in payload:
        patch["inventory"] = payload["inventory"]
        patch["inventory_replace"] = True
    if "session_lore" in payload:
        patch["session_lore"] = payload["session_lore"]
    if "modifiers" in payload:
        patch["modifiers"] = payload["modifiers"]
        patch["modifiers_replace"] = True
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
    - inventory: changed/added quantities; a vanished line means quantity 0
      (= removal);
    - modifiers: only **new** ones are kept (a correction can only add
      modifiers).
    """
    entities: dict[str, dict[str, str]] = {}
    state_before = before.get("state", {})
    for eid, stats in after.get("state", {}).items():
        prior = state_before.get(eid, {})
        changed = {k: v for k, v in stats.items() if str(prior.get(k)) != str(v)}
        if changed:
            entities[eid] = changed

    def _inv_key(i: dict) -> tuple:
        if i.get("instance_id"):
            return ("id", i["instance_id"])
        holder = i.get("holder_id") or i.get("entity_id") or ""
        kind = i.get("holder_kind") or "entity"
        return ("stack", kind, holder, i.get("item_id"))

    inv_before = {_inv_key(i): i for i in before.get("inventory", [])}
    inv_after = {_inv_key(i): i for i in after.get("inventory", [])}
    inventory: list[dict[str, Any]] = []
    for key, it in inv_after.items():
        prior = inv_before.get(key)
        if prior is None or int(prior.get("quantity", 1)) != int(it.get("quantity", 1)) \
                or (prior.get("holder_id") or prior.get("entity_id")) != (
                    it.get("holder_id") or it.get("entity_id")):
            inventory.append(it)
    for key, it in inv_before.items():
        if key not in inv_after:
            gone = dict(it)
            gone["quantity"] = 0
            inventory.append(gone)

    def _mod_key(m: dict) -> tuple:
        return (m["entity_id"], m["stat_key"], float(m["delta"]),
                int(m.get("minutes_remaining", 0)))

    known = {_mod_key(m) for m in before.get("modifiers", [])}
    modifiers = [m for m in after.get("modifiers", []) if _mod_key(m) not in known]

    lore_before = before.get("session_lore") or []
    lore_after = after.get("session_lore") or []
    patch: dict[str, Any] = {"entities": entities, "inventory": inventory, "modifiers": modifiers}
    if lore_before != lore_after:
        patch["session_lore"] = lore_after
    return patch


def apply_correction_file(db_path: str, save_id: str, patch_path: str | Path, *, at_turn: int | None = None) -> int:
    """Load a TOML file (same sections as save_state.toml) and apply it as a correction."""
    data = _load_state_toml(patch_path)
    patch = {
        "entities": data.get("state", {}),
        "inventory": data.get("inventory", []),
        "modifiers": data.get("modifiers", []),
    }
    if "session_lore" in data:
        patch["session_lore"] = data.get("session_lore") or []
    return apply_correction(db_path, save_id, patch, at_turn=at_turn)


# ---------------------------------------------------------------------------
# Fork (découpe du journal à un point)
# ---------------------------------------------------------------------------

def _fork_item_instances(
    conn: sqlite3.Connection, src_id: str, new_id: str, turn_id: int
) -> None:
    """Copy the nested inventory into a forked save (TICKET-095).

    Uses the source's inventory snapshot at the fork turn when there is one
    (else the present inventory, as before), and copies the snapshots up to
    that turn so rewind keeps working inside the fork. Instance ids are
    regenerated through ONE mapping shared by rows, holders and snapshots, so
    a container's contents still point at the forked container.
    """
    from axiom.inventory import inventory_at, snapshot_inventory
    from axiom.schema import ensure_inventory_snapshots_table

    id_map: dict[str, str] = {}

    def _new(old: str) -> str:
        if old not in id_map:
            id_map[old] = str(uuid.uuid4())
        return id_map[old]

    def _remap(row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        out["instance_id"] = _new(str(row["instance_id"]))
        if row.get("holder_kind") == "instance":
            out["holder_id"] = _new(str(row["holder_id"]))
        return out

    rows = inventory_at(conn, src_id, turn_id)
    if rows is None:
        rows = [
            dict(r) for r in conn.execute(
                "SELECT instance_id, item_id, quantity, holder_kind, holder_id "
                "FROM Item_Instances WHERE save_id = ?;",
                (src_id,),
            ).fetchall()
        ]
    conn.executemany(
        "INSERT INTO Item_Instances "
        "(instance_id, save_id, item_id, quantity, holder_kind, holder_id) "
        "VALUES (?, ?, ?, ?, ?, ?);",
        [(m["instance_id"], new_id, m["item_id"], m["quantity"], m["holder_kind"],
          m["holder_id"]) for m in map(_remap, rows)],
    )

    ensure_inventory_snapshots_table(conn)
    for snap in conn.execute(
        "SELECT turn_id, state_json FROM Inventory_Snapshots "
        "WHERE save_id = ? AND turn_id <= ?;",
        (src_id, turn_id),
    ).fetchall():
        conn.execute(
            "INSERT OR REPLACE INTO Inventory_Snapshots (save_id, turn_id, state_json) "
            "VALUES (?, ?, ?);",
            (new_id, snap[0], json.dumps([_remap(r) for r in json.loads(snap[1] or "[]")])),
        )
    snapshot_inventory(conn, new_id, turn_id)


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
