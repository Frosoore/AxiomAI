"""mods/axiom.inventory/main.py

Official mod: axiom.inventory (Emergent Nested Inventory & Item Trees)
Provides:
1. Nested item/container trees (entities, containers, locations up to depth 5).
2. Slot contribution to axiom.turn:prompt_sections (equipment & nested inventory overview).
3. Slot contribution to axiom.turn:output_fields ("inventory_changes").
4. Slot provision axiom.inventory:actions (extensibility for custom inventory actions).
5. Service "inventory" registration for UI and engine queries.
"""

from __future__ import annotations

from typing import Any
import sqlite3

from mods.axiom.inventory.inventory import (
    _holder_exists,
    _slug_item_id,
    add_item,
    ensure_item_definition,
    format_inventory_prompt,
    list_instances,
    load_inventory_tree,
    move_item,
    remove_item,
    snapshot_present_inventory,
)
from axiom.kernel.context import ModContext
from axiom.kernel.registry import SlotRule
from axiom.logger import logger
from axiom.schema import get_connection


class InventoryService:
    """Public service exposed by axiom.inventory to the engine and UIs."""

    @staticmethod
    def entity_items(db_path: str, save_id: str, entity_id: str) -> list[dict[str, Any]]:
        """Items carried by one entity (flat, on-person)."""
        from mods.axiom.inventory.inventory import entity_inventory
        return entity_inventory(db_path, save_id, entity_id)

    @staticmethod
    def load_tree(db_path: str, save_id: str) -> list[dict[str, Any]]:
        return load_inventory_tree(db_path, save_id)

    @staticmethod
    def format_prompt(tree: list[dict[str, Any]], names: dict[str, str] | None = None) -> str:
        return format_inventory_prompt(tree, names)

    @staticmethod
    def move(
        db_path: str,
        save_id: str,
        instance_id: str,
        dest_kind: str,
        dest_id: str,
        quantity: int = 1,
    ) -> None:
        with get_connection(db_path) as conn:
            move_item(conn, save_id, instance_id, dest_kind, dest_id, quantity=quantity)
            snapshot_present_inventory(conn, save_id)

    @staticmethod
    def add(
        db_path: str,
        save_id: str,
        item_id: str,
        quantity: int = 1,
        holder_kind: str = "entity",
        holder_id: str = "player",
        name: str = "",
        is_container: bool = False,
    ) -> str:
        with get_connection(db_path) as conn:
            inst = add_item(
                conn,
                save_id,
                item_id,
                quantity=quantity,
                holder_kind=holder_kind,
                holder_id=holder_id,
                name=name,
                is_container=is_container,
            )
            snapshot_present_inventory(conn, save_id)
            return inst


def _resolve_inventory_holder(change: dict[str, Any], default_entity_id: str) -> tuple[str, str]:
    if change.get("holder_kind") and change.get("holder_id"):
        return str(change["holder_kind"]), str(change["holder_id"])
    if change.get("location_id"):
        return "location", str(change["location_id"])
    if change.get("entity_id"):
        return "entity", str(change["entity_id"])
    return "entity", default_entity_id


def validate_inventory_change(
    db_path: str,
    save_id: str,
    change: dict[str, Any],
    default_entity_id: str = "player",
) -> tuple[bool, str]:
    """Validates an inventory mutation and normalizes holders/containers."""
    item_id = change.get("item_id")
    action = change.get("action")
    if not item_id or action not in ("add", "remove", "move"):
        return False, "Malformed inventory change (missing item_id or invalid action)."

    change["item_id"] = _slug_item_id(str(item_id))
    item_id = change["item_id"]
    try:
        quantity = int(change.get("quantity", 1))
    except (ValueError, TypeError):
        return False, "Inventory quantity must be a whole number."
    if quantity <= 0:
        return False, "Inventory quantity must be a positive whole number."

    holder_kind, holder_id = _resolve_inventory_holder(change, default_entity_id)
    change["holder_kind"] = holder_kind
    change["holder_id"] = holder_id
    change["entity_id"] = holder_id if holder_kind == "entity" else change.get("entity_id") or holder_id

    container_target = str(
        change.get("container_id")
        or change.get("container_name")
        or change.get("container")
        or ""
    ).strip()

    # Read-only validation (0d, R2-I-7): a new Item_Definitions row for an
    # emergent item is created by add_item when the turn's write batch commits,
    # so an aborted turn leaves no definition behind.
    with get_connection(db_path) as conn:
        if action == "move":
            if container_target:
                cid = _slug_item_id(container_target)
                row = conn.execute(
                    "SELECT instance_id FROM Item_Instances "
                    "WHERE save_id = ? AND (instance_id = ? OR item_id = ?);",
                    (save_id, container_target, cid),
                ).fetchone()
                if row:
                    change["dest_holder_kind"] = "instance"
                    change["dest_holder_id"] = row[0]
                else:
                    return False, f"Target container not found: {container_target}"
            elif change.get("dest_holder_id"):
                change["dest_holder_kind"] = str(change.get("dest_holder_kind") or "entity")
                change["dest_holder_id"] = str(change["dest_holder_id"])
            else:
                return False, "Move action missing destination container or holder."

            if not change.get("instance_id"):
                inst_row = conn.execute(
                    "SELECT instance_id FROM Item_Instances "
                    "WHERE save_id = ? AND item_id = ? AND holder_kind = ? AND holder_id = ? "
                    "LIMIT 1;",
                    (save_id, item_id, holder_kind, holder_id),
                ).fetchone()
                if inst_row:
                    change["instance_id"] = inst_row[0]
                else:
                    return False, f"Item instance not found to move: {item_id}"

        elif action == "add":
            if container_target and holder_kind != "instance":
                cid = _slug_item_id(container_target)
                existing = conn.execute(
                    "SELECT instance_id FROM Item_Instances "
                    "WHERE save_id = ? AND item_id = ? AND holder_kind = ? AND holder_id = ? "
                    "LIMIT 1;",
                    (save_id, cid, holder_kind, holder_id),
                ).fetchone()
                if existing:
                    change["holder_kind"] = "instance"
                    change["holder_id"] = existing[0]
                else:
                    change["_pending_container"] = {
                        "item_id": cid,
                        "name": container_target,
                        "holder_kind": holder_kind,
                        "holder_id": holder_id,
                    }
            elif not _holder_exists(conn, holder_kind, holder_id):
                return False, f"Unknown holder: {holder_kind}:{holder_id}"

        elif action == "remove":
            row = conn.execute(
                "SELECT SUM(quantity) FROM Item_Instances "
                "WHERE save_id = ? AND item_id = ? AND holder_kind = ? AND holder_id = ?;",
                (save_id, item_id, holder_kind, holder_id),
            ).fetchone()
            current_qty = int(row[0] or 0) if row else 0
            if current_qty < quantity:
                return False, f"Insufficient quantity for {item_id} (has {current_qty}, needs {quantity})."

    return True, ""


def handle_inventory_changes(raw_changes: Any, ctx: Any) -> None:
    """Slot handler for axiom.turn:output_fields 'inventory_changes'."""
    if not isinstance(raw_changes, list):
        return
    db_path = getattr(ctx, "db_path", "")
    save_id = getattr(ctx, "save_id", "")
    default_player = getattr(ctx, "player_entity_id", "player")

    rejections: list[str] = []
    valid_changes: list[dict[str, Any]] = []
    for change in raw_changes:
        if not isinstance(change, dict):
            continue
        valid, reason = validate_inventory_change(db_path, save_id, change, default_player)
        if valid:
            valid_changes.append(dict(change))
            ctx.inventory_changes.append(change)
            action = change.get("action", "")
            target = change.get("item_id", "")
            if hasattr(ctx, "write_batch") and hasattr(ctx.write_batch, "stage_event"):
                ctx.write_batch.stage_event(
                    f"inventory_{action}",
                    change,
                    target_entity=target or "system",
                )
            elif hasattr(ctx, "write_batch") and hasattr(ctx.write_batch, "events"):
                ctx.write_batch.events.append((ctx.save_id, ctx.turn_id, f"inventory_{action}", target, change))
        else:
            msg = f"Inventory change rejected: {reason}"
            rejections.append(msg)
            logger.debug("[axiom.inventory] Change rejected: %s (%s)", change, reason)

    if valid_changes and hasattr(ctx, "write_batch") and hasattr(ctx.write_batch, "stage_op"):
        def _apply_inventory_op(conn: sqlite3.Connection, sid: str, tid: int) -> None:
            from mods.axiom.inventory.inventory import (
                InventoryError,
                add_item,
                inventory_at,
                move_item,
                remove_item,
                snapshot_inventory,
            )
            if tid >= 1:
                if inventory_at(conn, sid, tid - 1) is None:
                    snapshot_inventory(conn, sid, tid - 1)
            for ch in valid_changes:
                action = ch.get("action")
                item_id = ch.get("item_id")
                quantity = int(ch.get("quantity", 1))
                holder_kind = ch.get("holder_kind") or "entity"
                holder_id = ch.get("holder_id") or ch.get("entity_id") or ""
                try:
                    pending = ch.pop("_pending_container", None)
                    if pending:
                        inst = add_item(
                            conn,
                            sid,
                            pending["item_id"],
                            quantity=1,
                            holder_kind=pending["holder_kind"],
                            holder_id=pending["holder_id"],
                            name=pending["name"],
                            is_container=True,
                        )
                        holder_kind, holder_id = "instance", inst
                        ch["holder_kind"] = holder_kind
                        ch["holder_id"] = holder_id
                    if action == "add":
                        add_item(
                            conn,
                            sid,
                            item_id,
                            quantity=quantity,
                            holder_kind=holder_kind,
                            holder_id=holder_id,
                            name=str(ch.get("name") or ""),
                            is_container=bool(ch.get("is_container")),
                        )
                    elif action == "remove":
                        remove_item(
                            conn,
                            sid,
                            item_id=item_id,
                            holder_kind=holder_kind,
                            holder_id=holder_id,
                            quantity=quantity,
                        )
                    elif action == "move":
                        dest_kind = str(ch.get("dest_holder_kind") or holder_kind)
                        dest_id = str(ch.get("dest_holder_id") or holder_id)
                        instance_id = ch.get("instance_id")
                        if instance_id:
                            move_item(
                                conn,
                                sid,
                                instance_id,
                                dest_kind,
                                dest_id,
                                quantity=quantity,
                            )
                except InventoryError as exc:
                    logger.warning("[axiom.inventory] Inventory apply failed: %s", exc)

        ctx.write_batch.stage_op(_apply_inventory_op)

    if rejections:
        queue = getattr(ctx, "queue_correction", None)
        if callable(queue):
            queue("; ".join(rejections))


def build_inventory_prompt_section(ctx: Any) -> dict[str, str] | None:
    """Dynamic prompt section builder providing the player's nested equipment/items."""
    db_path = getattr(ctx, "db_path", "")
    save_id = getattr(ctx, "save_id", "")
    if not db_path or not save_id:
        return None
    try:
        tree = load_inventory_tree(db_path, save_id)
        id_to_name = getattr(ctx, "id_to_name", None)
        text = format_inventory_prompt(tree, id_to_name)
        if text and text.strip() != "(empty)":
            return {
                "position": "system",
                "text": f"INVENTORY (nested: on person / in containers / at locations):\n{text}",
                "depth": 4,
            }
    except Exception as err:
        logger.debug("[axiom.inventory] Error building prompt section: %s", err)
    return None


def init(ctx: ModContext) -> None:
    """Mod entry point."""
    # Expose service
    ctx.register_service("inventory", InventoryService())

    # Declare slots
    ctx.declare_slot("axiom.inventory:actions", SlotRule.COLLECT)

    # Contribute to axiom.turn slots (M5 structured output)
    ctx.contribute_slot(
        "axiom.turn:output_fields",
        {
            "name": "inventory_changes",
            "schema": [
                {
                    "entity_id": "...",
                    "item_id": "...",
                    "action": "add",
                    "quantity": 1,
                    "container_name": "",
                    "location_id": "",
                    "is_container": False,
                }
            ],
            "instruction": (
                "When a character picks up, buys, is given, stores, or loses a physical object, "
                "emit inventory_changes. Use action \"add\", \"remove\", or \"move\", a snake_case item_id, "
                "and quantity. New items are allowed — invent a short item_id from the object name. "
                "Put carried items on the entity (entity_id). Put stashed items in a container "
                "(container_name like \"purse\" or \"nightstand_drawer\") and/or a location_id. "
                "Mark bags, purses, drawers, boxes with is_container true."
            ),
            "handler": handle_inventory_changes,
        },
    )
    ctx.contribute_slot("axiom.turn:prompt_sections", build_inventory_prompt_section)

    # Contribute sidebar widget to axiom.ui.qt
    try:
        from mods.axiom.inventory.ui.inventory_view import InventoryTreeView
        ctx.contribute_slot("axiom.ui.qt:sidebar_widget", InventoryTreeView)
    except Exception as exc:
        logger.debug("[axiom.inventory] Could not load InventoryTreeView: %s", exc)

