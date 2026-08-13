"""Nested play inventory — instance tree, not a Creator catalog.

Items appear from play (or the save editor). A holder is an entity, a
location, or another instance (a purse, a drawer). Max nesting is 5.
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from typing import Any

from axiom.schema import get_connection

MAX_NEST_DEPTH = 5
HOLDER_KINDS = frozenset({"entity", "location", "instance"})


class InventoryError(Exception):
    """Illegal inventory operation."""


def _slug_item_id(raw: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (raw or "").strip().lower()).strip("_")
    return slug or "item"


def ensure_item_definition(
    conn: sqlite3.Connection,
    item_id: str,
    *,
    name: str = "",
    is_container: bool = False,
    description: str = "",
    category: str = "misc",
) -> str:
    """Insert a play-emergent Item_Definitions row if missing."""
    item_id = _slug_item_id(item_id)
    row = conn.execute(
        "SELECT item_id FROM Item_Definitions WHERE item_id = ?;", (item_id,)
    ).fetchone()
    if row:
        if is_container:
            conn.execute(
                "UPDATE Item_Definitions SET is_container = 1 WHERE item_id = ?;",
                (item_id,),
            )
        return item_id
    pretty = (name or item_id).replace("_", " ").strip().title()
    cols = {r[1] for r in conn.execute("PRAGMA table_info(Item_Definitions);")}
    if "is_container" in cols:
        conn.execute(
            "INSERT INTO Item_Definitions "
            "(item_id, name, description, category, weight, rarity, is_container) "
            "VALUES (?, ?, ?, ?, 0, 'common', ?);",
            (item_id, pretty or item_id, description, category, 1 if is_container else 0),
        )
    else:
        conn.execute(
            "INSERT INTO Item_Definitions "
            "(item_id, name, description, category, weight, rarity) "
            "VALUES (?, ?, ?, ?, 0, 'common');",
            (item_id, pretty or item_id, description, category),
        )
    return item_id


def _is_container(conn: sqlite3.Connection, item_id: str) -> bool:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(Item_Definitions);")}
    if "is_container" not in cols:
        return False
    row = conn.execute(
        "SELECT is_container FROM Item_Definitions WHERE item_id = ?;", (item_id,)
    ).fetchone()
    return bool(row and row[0])


def _holder_exists(conn: sqlite3.Connection, kind: str, holder_id: str) -> bool:
    if kind == "entity":
        return conn.execute(
            "SELECT 1 FROM Entities WHERE entity_id = ?;", (holder_id,)
        ).fetchone() is not None
    if kind == "location":
        return conn.execute(
            "SELECT 1 FROM Locations WHERE location_id = ?;", (holder_id,)
        ).fetchone() is not None
    if kind == "instance":
        return conn.execute(
            "SELECT 1 FROM Item_Instances WHERE instance_id = ?;", (holder_id,)
        ).fetchone() is not None
    return False


def _depth_of(conn: sqlite3.Connection, kind: str, holder_id: str) -> int:
    depth = 0
    seen: set[str] = set()
    while kind == "instance":
        if holder_id in seen:
            raise InventoryError("Inventory nest cycle.")
        seen.add(holder_id)
        row = conn.execute(
            "SELECT holder_kind, holder_id FROM Item_Instances WHERE instance_id = ?;",
            (holder_id,),
        ).fetchone()
        if row is None:
            break
        kind, holder_id = row[0], row[1]
        depth += 1
        if depth > MAX_NEST_DEPTH:
            raise InventoryError(f"Inventory nest exceeds {MAX_NEST_DEPTH} levels.")
    return depth


def _would_cycle(conn: sqlite3.Connection, instance_id: str, dest_kind: str, dest_id: str) -> bool:
    if dest_kind != "instance":
        return False
    cursor = dest_id
    seen = {instance_id}
    while True:
        if cursor in seen:
            return True
        seen.add(cursor)
        row = conn.execute(
            "SELECT holder_kind, holder_id FROM Item_Instances WHERE instance_id = ?;",
            (cursor,),
        ).fetchone()
        if row is None or row[0] != "instance":
            return False
        cursor = row[1]


def add_item(
    conn: sqlite3.Connection,
    save_id: str,
    item_id: str,
    *,
    quantity: int = 1,
    holder_kind: str = "entity",
    holder_id: str = "",
    name: str = "",
    is_container: bool = False,
) -> str:
    """Add quantity of item_id to a holder. Merges non-container stacks. Returns instance_id."""
    if quantity < 1:
        raise InventoryError("Quantity must be at least 1.")
    if holder_kind not in HOLDER_KINDS:
        raise InventoryError(f"Unknown holder kind: {holder_kind}")
    if not holder_id:
        raise InventoryError("Missing holder_id.")
    item_id = ensure_item_definition(
        conn, item_id, name=name, is_container=is_container
    )
    if not _holder_exists(conn, holder_kind, holder_id):
        raise InventoryError(f"Unknown holder: {holder_kind}:{holder_id}")
    dest_depth = _depth_of(conn, holder_kind, holder_id)
    if dest_depth + 1 > MAX_NEST_DEPTH:
        raise InventoryError(f"Inventory nest exceeds {MAX_NEST_DEPTH} levels.")

    container = is_container or _is_container(conn, item_id)
    if not container:
        existing = conn.execute(
            "SELECT instance_id, quantity FROM Item_Instances "
            "WHERE save_id = ? AND item_id = ? AND holder_kind = ? AND holder_id = ?;",
            (save_id, item_id, holder_kind, holder_id),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE Item_Instances SET quantity = quantity + ? WHERE instance_id = ?;",
                (quantity, existing[0]),
            )
            return existing[0]

    instance_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO Item_Instances "
        "(instance_id, save_id, item_id, quantity, holder_kind, holder_id) "
        "VALUES (?, ?, ?, ?, ?, ?);",
        (instance_id, save_id, item_id, quantity, holder_kind, holder_id),
    )
    return instance_id


def remove_item(
    conn: sqlite3.Connection,
    save_id: str,
    *,
    instance_id: str | None = None,
    item_id: str | None = None,
    holder_kind: str = "entity",
    holder_id: str = "",
    quantity: int = 1,
) -> None:
    """Remove quantity from a specific instance or from a stack in a holder."""
    if quantity < 1:
        raise InventoryError("Quantity must be at least 1.")
    row = None
    if instance_id:
        row = conn.execute(
            "SELECT instance_id, quantity FROM Item_Instances "
            "WHERE save_id = ? AND instance_id = ?;",
            (save_id, instance_id),
        ).fetchone()
    elif item_id and holder_id:
        row = conn.execute(
            "SELECT instance_id, quantity FROM Item_Instances "
            "WHERE save_id = ? AND item_id = ? AND holder_kind = ? AND holder_id = ? "
            "ORDER BY quantity DESC LIMIT 1;",
            (save_id, _slug_item_id(item_id), holder_kind, holder_id),
        ).fetchone()
    if row is None:
        raise InventoryError("Item not found in that holder.")
    iid, current = row[0], int(row[1])
    if current < quantity:
        raise InventoryError(
            f"Insufficient quantity (has {current}, needs {quantity})."
        )
    children = conn.execute(
        "SELECT 1 FROM Item_Instances WHERE holder_kind = 'instance' AND holder_id = ?;",
        (iid,),
    ).fetchone()
    if children and current - quantity <= 0:
        raise InventoryError("Empty the container before removing it.")
    if current - quantity <= 0:
        conn.execute("DELETE FROM Item_Instances WHERE instance_id = ?;", (iid,))
    else:
        conn.execute(
            "UPDATE Item_Instances SET quantity = quantity - ? WHERE instance_id = ?;",
            (quantity, iid),
        )


def move_item(
    conn: sqlite3.Connection,
    save_id: str,
    instance_id: str,
    dest_kind: str,
    dest_id: str,
    *,
    quantity: int | None = None,
) -> str:
    """Move an instance (or split-off quantity) to a new holder. Returns instance_id."""
    if dest_kind not in HOLDER_KINDS:
        raise InventoryError(f"Unknown holder kind: {dest_kind}")
    if not dest_id:
        raise InventoryError("Missing destination holder.")
    row = conn.execute(
        "SELECT item_id, quantity, holder_kind, holder_id FROM Item_Instances "
        "WHERE save_id = ? AND instance_id = ?;",
        (save_id, instance_id),
    ).fetchone()
    if row is None:
        raise InventoryError("Unknown item instance.")
    item_id, current, src_kind, src_id = row[0], int(row[1]), row[2], row[3]
    if src_kind == dest_kind and src_id == dest_id:
        return instance_id
    if not _holder_exists(conn, dest_kind, dest_id):
        raise InventoryError(f"Unknown holder: {dest_kind}:{dest_id}")
    if _would_cycle(conn, instance_id, dest_kind, dest_id):
        raise InventoryError("Cannot move a container into itself.")
    dest_depth = _depth_of(conn, dest_kind, dest_id)
    extra = _subtree_height(conn, instance_id)
    if dest_depth + 1 + extra > MAX_NEST_DEPTH:
        raise InventoryError(f"Inventory nest exceeds {MAX_NEST_DEPTH} levels.")

    qty = current if quantity is None else int(quantity)
    if qty < 1 or qty > current:
        raise InventoryError("Invalid move quantity.")

    if qty < current:
        # split
        new_id = str(uuid.uuid4())
        conn.execute(
            "UPDATE Item_Instances SET quantity = quantity - ? WHERE instance_id = ?;",
            (qty, instance_id),
        )
        conn.execute(
            "INSERT INTO Item_Instances "
            "(instance_id, save_id, item_id, quantity, holder_kind, holder_id) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (new_id, save_id, item_id, qty, dest_kind, dest_id),
        )
        return _maybe_merge(conn, save_id, new_id)

    conn.execute(
        "UPDATE Item_Instances SET holder_kind = ?, holder_id = ? WHERE instance_id = ?;",
        (dest_kind, dest_id, instance_id),
    )
    return _maybe_merge(conn, save_id, instance_id)


def _subtree_height(conn: sqlite3.Connection, instance_id: str) -> int:
    kids = conn.execute(
        "SELECT instance_id FROM Item_Instances "
        "WHERE holder_kind = 'instance' AND holder_id = ?;",
        (instance_id,),
    ).fetchall()
    if not kids:
        return 0
    return 1 + max(_subtree_height(conn, k[0]) for k in kids)


def _maybe_merge(conn: sqlite3.Connection, save_id: str, instance_id: str) -> str:
    row = conn.execute(
        "SELECT item_id, quantity, holder_kind, holder_id FROM Item_Instances "
        "WHERE instance_id = ?;",
        (instance_id,),
    ).fetchone()
    if row is None or _is_container(conn, row[0]):
        return instance_id
    item_id, qty, kind, hid = row
    other = conn.execute(
        "SELECT instance_id, quantity FROM Item_Instances "
        "WHERE save_id = ? AND item_id = ? AND holder_kind = ? AND holder_id = ? "
        "AND instance_id != ?;",
        (save_id, item_id, kind, hid, instance_id),
    ).fetchone()
    if other is None:
        return instance_id
    conn.execute(
        "UPDATE Item_Instances SET quantity = quantity + ? WHERE instance_id = ?;",
        (qty, other[0]),
    )
    conn.execute("DELETE FROM Item_Instances WHERE instance_id = ?;", (instance_id,))
    return other[0]


def list_instances(conn: sqlite3.Connection, save_id: str) -> list[dict[str, Any]]:
    inst_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='Item_Instances';"
    ).fetchone()
    if not inst_exists:
        return []
    cols = {r[1] for r in conn.execute("PRAGMA table_info(Item_Definitions);")}
    container_sel = "COALESCE(d.is_container, 0)" if "is_container" in cols else "0"
    capacity_sel = "d.capacity" if "capacity" in cols else "NULL"
    try:
        rows = conn.execute(
            f"""
            SELECT i.instance_id, i.item_id, i.quantity, i.holder_kind, i.holder_id,
                   COALESCE(d.name, i.item_id) AS name,
                   COALESCE(d.description, '') AS description,
                   COALESCE(d.category, 'misc') AS category,
                   COALESCE(d.rarity, 'common') AS rarity,
                   {container_sel} AS is_container,
                   {capacity_sel} AS capacity
            FROM Item_Instances i
            LEFT JOIN Item_Definitions d ON d.item_id = i.item_id
            WHERE i.save_id = ?
            ORDER BY i.holder_kind, i.holder_id, name;
            """,
            (save_id,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for r in rows:
        if isinstance(r, sqlite3.Row):
            rec = {
                "instance_id": r["instance_id"],
                "item_id": r["item_id"],
                "quantity": int(r["quantity"]),
                "holder_kind": r["holder_kind"],
                "holder_id": r["holder_id"],
                "name": r["name"],
                "description": r["description"],
                "category": r["category"],
                "rarity": r["rarity"],
                "is_container": bool(r["is_container"]),
                "capacity": r["capacity"],
            }
        else:
            rec = {
                "instance_id": r[0], "item_id": r[1], "quantity": int(r[2]),
                "holder_kind": r[3], "holder_id": r[4], "name": r[5],
                "description": r[6], "category": r[7], "rarity": r[8],
                "is_container": bool(r[9]), "capacity": r[10],
            }
        if rec["holder_kind"] == "entity":
            rec["entity_id"] = rec["holder_id"]
        out.append(rec)
    return out


def build_tree(instances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group instances into a forest: entity/location roots with nested children."""
    by_id = {i["instance_id"]: {**i, "contents": []} for i in instances}
    roots: list[dict[str, Any]] = []
    hanging: list[dict[str, Any]] = []
    for node in by_id.values():
        if node["holder_kind"] == "instance":
            parent = by_id.get(node["holder_id"])
            if parent is not None:
                parent["contents"].append(node)
            else:
                hanging.append(node)
        else:
            hanging.append(node)

    buckets: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for node in hanging:
        if node["holder_kind"] == "instance":
            key = ("orphan", node["holder_id"])
        else:
            key = (node["holder_kind"], node["holder_id"])
        buckets.setdefault(key, []).append(node)

    for (kind, hid), children in buckets.items():
        roots.append({
            "holder_kind": kind,
            "holder_id": hid,
            "contents": children,
        })
    roots.sort(key=lambda r: (0 if r["holder_kind"] == "entity" else 1, r["holder_id"]))
    return roots


def load_inventory_tree(db_path: str, save_id: str) -> list[dict[str, Any]]:
    with get_connection(db_path) as conn:
        return build_tree(list_instances(conn, save_id))


def replace_inventory(
    conn: sqlite3.Connection,
    save_id: str,
    items: list[dict[str, Any]],
) -> None:
    """Replace a save's inventory with the given instance (or flat) rows."""
    conn.execute("DELETE FROM Item_Instances WHERE save_id = ?;", (save_id,))
    for it in items:
        qty = int(it.get("quantity", 1) or 0)
        if qty <= 0:
            continue
        item_id = it.get("item_id") or it.get("name") or ""
        is_container = bool(it.get("is_container"))
        holder_kind = it.get("holder_kind") or "entity"
        holder_id = it.get("holder_id") or it.get("entity_id") or ""
        instance_id = it.get("instance_id") or str(uuid.uuid4())
        item_id = ensure_item_definition(
            conn, str(item_id),
            name=str(it.get("name") or ""),
            is_container=is_container,
        )
        if holder_kind not in HOLDER_KINDS or not holder_id:
            continue
        conn.execute(
            "INSERT INTO Item_Instances "
            "(instance_id, save_id, item_id, quantity, holder_kind, holder_id) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (instance_id, save_id, item_id, qty, holder_kind, holder_id),
        )


def format_inventory_prompt(tree: list[dict[str, Any]], names: dict[str, str] | None = None) -> str:
    """Human tree for the arbitrator prompt."""
    names = names or {}
    lines: list[str] = []

    def _walk(nodes: list[dict[str, Any]], indent: int) -> None:
        pad = "  " * indent
        for n in nodes:
            label = n.get("name") or n.get("item_id") or ""
            qty = n.get("quantity", 1)
            extra = " [container]" if n.get("is_container") else ""
            q = f" x{qty}" if qty and qty != 1 else ""
            lines.append(f"{pad}- {label}{q}{extra}")
            _walk(n.get("contents") or [], indent + 1)

    for root in tree:
        kind = root.get("holder_kind")
        hid = root.get("holder_id") or ""
        title = names.get(hid, hid)
        if kind == "entity":
            header = f"On {title}:"
        elif kind == "location":
            header = f"At {title}:"
        else:
            header = f"{title}:"
        lines.append(header)
        _walk(root.get("contents") or [], 1)
    return "\n".join(lines) if lines else "(empty)"
