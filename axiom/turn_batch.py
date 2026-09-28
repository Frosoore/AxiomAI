"""
axiom/turn_batch.py

Transactional turn write batch for Axiom AI.
Stages all turn mutations in memory (events, timeline, lore, inventory,
modifiers, scheduled events, state cache) and commits them atomically
to SQLite at the very end of the turn.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import json
import sqlite3
from typing import Any
import uuid

from axiom.logger import logger


@dataclass
class TurnWriteBatch:
    """In-memory staging buffer for all mutations produced during a turn.

    Guarantees all-or-nothing execution: if any error or cancellation occurs
    before or during execution, the database remains in its pre-turn state.
    """

    events: list[Any] = field(default_factory=list)
    stat_changes: list[dict[str, Any]] = field(default_factory=list)
    inventory_mutations: list[Any] = field(default_factory=list)
    timeline_entries: list[Any] = field(default_factory=list)
    lore_entries: list[Any] = field(default_factory=list)
    modifier_mutations: list[dict[str, Any]] = field(default_factory=list)
    fired_scheduled_events: list[str] = field(default_factory=list)
    post_commit_callbacks: list[Callable[[], None]] = field(default_factory=list)
    committed: bool = False

    def commit_all(self, conn: sqlite3.Connection, save_id: str, turn_id: int) -> None:
        """Atomically commit all staged mutations inside a single transaction."""
        if self.committed:
            return

        with conn:
            # 1. Timeline entries
            for entry in self.timeline_entries:
                if isinstance(entry, dict):
                    conn.execute(
                        "INSERT INTO Timeline (save_id, turn_id, in_game_time, description) "
                        "VALUES (?, ?, ?, ?);",
                        (
                            entry.get("save_id", save_id),
                            entry.get("turn_id", turn_id),
                            entry["in_game_time"],
                            entry["description"],
                        ),
                    )
                elif isinstance(entry, (tuple, list)):
                    conn.execute(
                        "INSERT INTO Timeline (save_id, turn_id, in_game_time, description) "
                        "VALUES (?, ?, ?, ?);",
                        entry,
                    )

            # 2. Session_Lore entries
            for entry in self.lore_entries:
                if isinstance(entry, dict):
                    entry_id = entry.get("entry_id") or str(uuid.uuid4())
                    conn.execute(
                        "INSERT INTO Session_Lore "
                        "(entry_id, save_id, category, name, keywords, content, origin_turn) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?);",
                        (
                            entry_id,
                            entry.get("save_id", save_id),
                            entry.get("category", "General"),
                            entry.get("name", ""),
                            entry.get("keywords", ""),
                            entry.get("content", ""),
                            entry.get("origin_turn", turn_id),
                        ),
                    )
                elif isinstance(entry, (tuple, list)):
                    conn.execute(
                        "INSERT INTO Session_Lore "
                        "(entry_id, save_id, category, name, keywords, content, origin_turn) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?);",
                        entry,
                    )

            # 3. Inventory mutations
            if turn_id >= 1:
                from axiom.inventory import inventory_at, snapshot_inventory
                if inventory_at(conn, save_id, turn_id - 1) is None:
                    snapshot_inventory(conn, save_id, turn_id - 1)

            from axiom.inventory import (
                InventoryError,
                add_item,
                ensure_item_definition,
                move_item,
                remove_item,
                snapshot_inventory,
            )

            for change in self.inventory_mutations:
                if callable(change):
                    change(conn)
                    continue
                if not isinstance(change, dict):
                    continue
                action = change.get("action")
                item_id = change.get("item_id")
                quantity = int(change.get("quantity", 1))
                holder_kind = change.get("holder_kind") or "entity"
                holder_id = change.get("holder_id") or change.get("entity_id") or ""
                try:
                    pending = change.pop("_pending_container", None)
                    if pending:
                        inst = add_item(
                            conn,
                            save_id,
                            pending["item_id"],
                            quantity=1,
                            holder_kind=pending["holder_kind"],
                            holder_id=pending["holder_id"],
                            name=pending["name"],
                            is_container=True,
                        )
                        holder_kind, holder_id = "instance", inst
                        change["holder_kind"] = holder_kind
                        change["holder_id"] = holder_id
                    if action == "add":
                        add_item(
                            conn,
                            save_id,
                            item_id,
                            quantity=quantity,
                            holder_kind=holder_kind,
                            holder_id=holder_id,
                            name=str(change.get("name") or ""),
                            is_container=bool(change.get("is_container")),
                        )
                    elif action == "remove":
                        remove_item(
                            conn,
                            save_id,
                            item_id=item_id,
                            holder_kind=holder_kind,
                            holder_id=holder_id,
                            quantity=quantity,
                        )
                    elif action == "move":
                        dest_kind = str(change.get("dest_holder_kind") or holder_kind)
                        dest_id = str(change.get("dest_holder_id") or holder_id)
                        instance_id = change.get("instance_id")
                        if instance_id:
                            move_item(
                                conn,
                                save_id,
                                instance_id,
                                dest_kind,
                                dest_id,
                                quantity=quantity,
                            )
                except InventoryError as exc:
                    logger.warning("[TurnWriteBatch] Inventory apply failed: %s", exc)

            snapshot_inventory(conn, save_id, turn_id)

            # 4. Modifiers
            for mod in self.modifier_mutations:
                mtype = mod.get("type")
                if mtype == "clear":
                    stat_key = mod.get("stat_key")
                    entity_id = mod.get("entity_id")
                    if stat_key:
                        rows = conn.execute(
                            "SELECT modifier_id, stat_key FROM Active_Modifiers "
                            "WHERE save_id = ? AND entity_id = ?;",
                            (save_id, entity_id),
                        ).fetchall()
                        want = stat_key.lower()
                        ids = [r[0] for r in rows if str(r[1]).lower() == want]
                        if ids:
                            placeholders = ",".join("?" * len(ids))
                            conn.execute(
                                f"DELETE FROM Active_Modifiers WHERE modifier_id IN ({placeholders});",
                                ids,
                            )
                    else:
                        conn.execute(
                            "DELETE FROM Active_Modifiers WHERE save_id = ? AND entity_id = ?;",
                            (save_id, entity_id),
                        )
                elif mtype == "add":
                    mid = mod.get("modifier_id") or str(uuid.uuid4())
                    conn.execute(
                        """
                        INSERT INTO Active_Modifiers
                            (modifier_id, save_id, entity_id, stat_key, delta, minutes_remaining)
                        VALUES (?, ?, ?, ?, ?, ?);
                        """,
                        (
                            mid,
                            save_id,
                            mod["entity_id"],
                            mod["stat_key"],
                            mod["delta"],
                            mod["minutes"],
                        ),
                    )
                elif mtype == "tick":
                    elapsed = int(mod.get("elapsed_minutes", 1))
                    conn.execute(
                        """
                        UPDATE Active_Modifiers
                        SET minutes_remaining = minutes_remaining - ?
                        WHERE save_id = ?;
                        """,
                        (elapsed, save_id),
                    )
                    conn.execute(
                        """
                        DELETE FROM Active_Modifiers
                        WHERE minutes_remaining <= 0 AND save_id = ?;
                        """,
                        (save_id,),
                    )
                elif mtype == "snapshot":
                    from axiom.schema import ensure_modifier_snapshots_table
                    ensure_modifier_snapshots_table(conn)
                    rows = conn.execute(
                        """
                        SELECT modifier_id, entity_id, stat_key, delta, minutes_remaining
                        FROM Active_Modifiers
                        WHERE save_id = ?;
                        """,
                        (save_id,),
                    ).fetchall()
                    if rows:
                        state = [
                            {
                                "modifier_id": row[0],
                                "entity_id": row[1],
                                "stat_key": row[2],
                                "delta": row[3],
                                "minutes_remaining": row[4],
                            }
                            for row in rows
                        ]
                        conn.execute(
                            "INSERT OR REPLACE INTO Modifier_Snapshots (save_id, turn_id, state_json) "
                            "VALUES (?, ?, ?);",
                            (save_id, turn_id, json.dumps(state)),
                        )

            # 5. Fired scheduled events
            if self.fired_scheduled_events:
                from axiom.schema import ensure_fired_event_turn_column
                ensure_fired_event_turn_column(conn)
                for event_id in self.fired_scheduled_events:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO Fired_Scheduled_Events (save_id, event_id, fired_turn_id)
                        VALUES (?, ?, ?);
                        """,
                        (save_id, event_id, turn_id),
                    )

            # 6. Events batch into Event_Log & State_Cache update
            event_tuples: list[tuple[str, int, str, str, Any]] = []
            for ev in self.events:
                if isinstance(ev, (tuple, list)):
                    event_tuples.append(tuple(ev))
                elif isinstance(ev, dict):
                    event_tuples.append((
                        ev.get("save_id", save_id),
                        ev.get("turn_id", turn_id),
                        ev["event_type"],
                        ev.get("target_entity", "system"),
                        ev.get("payload", {}),
                    ))

            if event_tuples:
                rows = [
                    (
                        s,
                        t,
                        e,
                        tg,
                        json.dumps(p, default=str) if not isinstance(p, str) else p,
                    )

                    for s, t, e, tg, p in event_tuples
                ]
                conn.executemany(
                    "INSERT INTO Event_Log (save_id, turn_id, event_type, target_entity, payload) "
                    "VALUES (?, ?, ?, ?, ?);",
                    rows,
                )

                # Update State_Cache
                _apply_events_to_state_cache(conn, save_id, event_tuples)

        self.committed = True

        for cb in self.post_commit_callbacks:
            try:
                cb()
            except Exception as exc:
                logger.warning("[TurnWriteBatch] Post-commit callback error: %s", exc)


def _apply_events_to_state_cache(
    conn: sqlite3.Connection,
    save_id: str,
    events: list[tuple[str, int, str, str, Any]],
) -> None:
    """Materialise event-sourced stat updates into State_Cache using connection conn."""
    from axiom.events import EventSourcer

    relevant = [
        {
            "event_type": etype,
            "target_entity": target,
            "payload": payload if isinstance(payload, dict) else json.loads(payload),
        }
        for (_sid, _tid, etype, target, payload) in events
        if etype in ("entity_create", "stat_change", "stat_set", "chronicler_update", "manual_edit")
    ]
    if not relevant:
        return

    entity_ids = {
        e["payload"].get("entity_id", e["target_entity"]) for e in relevant
    }
    entity_ids.discard("")
    if not entity_ids:
        return

    cache: dict[str, dict[str, str]] = {}
    placeholders = ",".join("?" * len(entity_ids))
    rows = conn.execute(
        f"SELECT entity_id, stat_key, stat_value FROM State_Cache "
        f"WHERE save_id = ? AND entity_id IN ({placeholders});",
        (save_id, *entity_ids),
    ).fetchall()
    for r in rows:
        cache.setdefault(r["entity_id"], {})[r["stat_key"]] = r["stat_value"]

    for event in relevant:
        cache = EventSourcer._apply_event(event, cache)

    upsert_data = [
        (save_id, eid, sk, sv)
        for eid, stats in cache.items()
        for sk, sv in stats.items()
    ]
    if not upsert_data:
        return

    conn.executemany(
        """
        INSERT INTO State_Cache (save_id, entity_id, stat_key, stat_value)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(save_id, entity_id, stat_key)
        DO UPDATE SET stat_value = excluded.stat_value;
        """,
        upsert_data,
    )
