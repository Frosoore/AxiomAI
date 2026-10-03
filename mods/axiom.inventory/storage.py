"""mods/axiom.inventory/storage.py

Save data of axiom.inventory: the live item instances (Item_Instances)
and their per-turn snapshots (Inventory_Snapshots). Declared in mod.toml and run
by the kernel even while the mod is disabled (owner decision 2026-10-03):
only this module is loaded then.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from mods.axiom.inventory.inventory import (
    inventory_at,
    rollback_inventory,
    snapshot_inventory as _snap_inv,
)


def rewind_inventory(conn: sqlite3.Connection, save_id: str, target_turn: int) -> None:
    """Restore Item_Instances to the snapshot of target_turn (rewind)."""
    rollback_inventory(conn, save_id, target_turn)


def snapshot_inventory(conn: sqlite3.Connection, save_id: str, turn_id: int) -> None:
    """End-of-turn capture of Item_Instances into Inventory_Snapshots."""
    _snap_inv(conn, save_id, turn_id)


def fork_item_instances(
    conn: sqlite3.Connection,
    src_save_id: str,
    dst_save_id: str,
    target_turn: int,
    *,
    id_maps: dict[str, dict[Any, Any]] | None = None,
) -> None:
    """Nested inventory at the fork point + Inventory_Snapshots <= N.

    Custom because instance ids are referenced by other instances (containers)
    and inside the snapshots' JSON: one mapping shared by rows and snapshots.
    """
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

    rows = inventory_at(conn, src_save_id, target_turn)
    if rows is None:
        rows = [
            {
                "instance_id": r[0],
                "item_id": r[1],
                "quantity": r[2],
                "holder_kind": r[3],
                "holder_id": r[4],
            }
            for r in conn.execute(
                "SELECT instance_id, item_id, quantity, holder_kind, holder_id "
                "FROM Item_Instances WHERE save_id = ?;",
                (src_save_id,),
            ).fetchall()
        ]

    conn.executemany(
        "INSERT INTO Item_Instances "
        "(instance_id, save_id, item_id, quantity, holder_kind, holder_id) "
        "VALUES (?, ?, ?, ?, ?, ?);",
        [
            (
                m["instance_id"],
                dst_save_id,
                m["item_id"],
                m["quantity"],
                m["holder_kind"],
                m["holder_id"],
            )
            for m in map(_remap, rows)
        ],
    )

    ensure_inventory_snapshots_table(conn)
    for snap in conn.execute(
        "SELECT turn_id, state_json FROM Inventory_Snapshots "
        "WHERE save_id = ? AND turn_id <= ?;",
        (src_save_id, target_turn),
    ).fetchall():
        conn.execute(
            "INSERT OR REPLACE INTO Inventory_Snapshots (save_id, turn_id, state_json) "
            "VALUES (?, ?, ?);",
            (
                dst_save_id,
                snap[0],
                json.dumps([_remap(r) for r in json.loads(snap[1] or "[]")]),
            ),
        )
    _snap_inv(conn, dst_save_id, target_turn)


def fork_legacy_inventory(
    conn: sqlite3.Connection, src_save_id: str, dst_save_id: str, target_turn: int,
    *, id_maps: dict[str, dict[Any, Any]] | None = None,
) -> None:
    """Legacy flat bag (Items_Inventory, old saves; not turn-keyed): copied as is."""
    rows = conn.execute(
        "SELECT entity_id, item_id, quantity FROM Items_Inventory WHERE save_id = ?;",
        (src_save_id,),
    ).fetchall()
    conn.executemany(
        "INSERT INTO Items_Inventory (save_id, entity_id, item_id, quantity) VALUES (?, ?, ?, ?);",
        [(dst_save_id, r[0], r[1], r[2]) for r in rows],
    )


# ---------------------------------------------------------------------------
# Save-editor section "inventory" (materialize, TOML export/import, corrections)
# ---------------------------------------------------------------------------

def _section_row(it: dict[str, Any]) -> dict[str, Any]:
    holder_kind = it.get("holder_kind") or "entity"
    holder_id = it.get("holder_id") or it.get("entity_id") or ""
    row = {
        "instance_id": it.get("instance_id") or "",
        "item_id": it.get("item_id") or "",
        "quantity": int(it.get("quantity", 1) or 0),
        "holder_kind": holder_kind,
        "holder_id": holder_id,
        "entity_id": holder_id if holder_kind == "entity" else "",
        "name": it.get("name") or "",
        "is_container": bool(it.get("is_container")),
    }
    return row


def state_inventory(
    conn: sqlite3.Connection, save_id: str, turn_id: int, present: bool
) -> tuple[list[dict[str, Any]], bool]:
    """Inventory at ``turn_id``: live at the present turn, else the turn's snapshot.
    A past turn played before snapshots existed shows the present inventory
    (historical = False); an old save without instances shows its flat bag."""
    from mods.axiom.inventory.inventory import list_instances

    if present:
        rows = [_section_row(it) for it in list_instances(conn, save_id)]
        historical = True
    else:
        past = inventory_at(conn, save_id, turn_id)
        historical = past is not None
        rows = [_section_row(it) for it in (past if past is not None else list_instances(conn, save_id))]
    if not rows and not (not present and historical):
        rows = [
            _section_row({"item_id": r[1], "quantity": r[2], "holder_kind": "entity", "holder_id": r[0]})
            for r in conn.execute(
                "SELECT entity_id, item_id, quantity FROM Items_Inventory WHERE save_id = ? "
                "ORDER BY entity_id, item_id;",
                (save_id,),
            )
        ]
    rows.sort(key=lambda r: (r["holder_kind"], r["holder_id"], r["item_id"]))
    return rows, historical


def _apply_inventory_row(conn: sqlite3.Connection, save_id: str, it: dict[str, Any]) -> None:
    """One correction row. Quantity is absolute (0 = remove)."""
    from mods.axiom.inventory.inventory import ensure_item_definition

    qty = int(it.get("quantity", 1) or 0)
    holder_kind = it.get("holder_kind") or "entity"
    holder_id = it.get("holder_id") or it.get("entity_id") or ""
    item_id = it.get("item_id") or ""
    instance_id = it.get("instance_id")
    if qty <= 0:
        if instance_id:
            conn.execute("DELETE FROM Item_Instances WHERE save_id = ? AND instance_id = ?;",
                         (save_id, instance_id))
        elif item_id and holder_id:
            conn.execute(
                "DELETE FROM Item_Instances WHERE save_id = ? AND item_id = ? "
                "AND holder_kind = ? AND holder_id = ?;",
                (save_id, item_id, holder_kind, holder_id),
            )
        if holder_id and item_id:
            conn.execute("DELETE FROM Items_Inventory WHERE save_id = ? AND entity_id = ? AND item_id = ?;",
                         (save_id, holder_id, item_id))
        return
    if not (holder_id and item_id):
        return
    item_id = ensure_item_definition(
        conn, item_id, name=str(it.get("name") or ""), is_container=bool(it.get("is_container"))
    )
    if instance_id and conn.execute(
        "SELECT 1 FROM Item_Instances WHERE instance_id = ?;", (instance_id,)
    ).fetchone():
        conn.execute(
            "UPDATE Item_Instances SET quantity = ?, holder_kind = ?, holder_id = ?, item_id = ? "
            "WHERE instance_id = ?;",
            (qty, holder_kind, holder_id, item_id, instance_id),
        )
        return
    existing = conn.execute(
        "SELECT instance_id FROM Item_Instances WHERE save_id = ? AND item_id = ? "
        "AND holder_kind = ? AND holder_id = ? LIMIT 1;",
        (save_id, item_id, holder_kind, holder_id),
    ).fetchone()
    if existing:
        conn.execute("UPDATE Item_Instances SET quantity = ? WHERE instance_id = ?;", (qty, existing[0]))
    else:
        conn.execute(
            "INSERT INTO Item_Instances (instance_id, save_id, item_id, quantity, holder_kind, holder_id) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (instance_id or str(uuid.uuid4()), save_id, item_id, qty, holder_kind, holder_id),
        )


def load_inventory(
    conn: sqlite3.Connection, save_id: str, rows: list[dict[str, Any]], turn_id: int, replace: bool
) -> None:
    """Import (replace=True) or correction rows (absolute quantities)."""
    from mods.axiom.inventory.inventory import replace_inventory

    if replace:
        replace_inventory(conn, save_id, list(rows))
        return
    for it in rows:
        _apply_inventory_row(conn, save_id, it)


def diff_inventory(before: list[dict[str, Any]], after: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Changed/added lines; a vanished line means quantity 0 (removal)."""
    def key(i: dict) -> tuple:
        if i.get("instance_id"):
            return ("id", i["instance_id"])
        return ("stack", i.get("holder_kind") or "entity", i.get("holder_id") or i.get("entity_id") or "",
                i.get("item_id"))

    inv_before = {key(i): i for i in before}
    inv_after = {key(i): i for i in after}
    out: list[dict[str, Any]] = []
    for k, it in inv_after.items():
        prior = inv_before.get(k)
        if prior is None or int(prior.get("quantity", 1)) != int(it.get("quantity", 1)) \
                or (prior.get("holder_id") or prior.get("entity_id")) != (it.get("holder_id") or it.get("entity_id")):
            out.append(it)
    for k, it in inv_before.items():
        if k not in inv_after:
            out.append({**it, "quantity": 0})
    return out
