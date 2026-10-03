"""
axiom/turn_batch.py

Transactional turn write batch for Axiom AI.
Stages all turn mutations in memory (events, session lore, the mods' own
writes via ``stage_op``, mods' key-values) and commits them atomically to
SQLite at the very end of the turn, followed by the end-of-turn snapshots of
every declared storage.
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
    lore_entries: list[Any] = field(default_factory=list)
    # Writes of mods into their own tables: fn(conn, save_id, turn_id), run in order
    # inside the turn's transaction (all-or-nothing with the rest of the turn).
    staged_ops: list[Callable[[sqlite3.Connection, str, int], None]] = field(default_factory=list)
    post_commit_callbacks: list[Callable[[], None]] = field(default_factory=list)
    # Mods' versioned key-values (ctx.store): (mod_id, key, value_json | None, step).
    kv_writes: list[tuple[str, str, str | None, int]] = field(default_factory=list)
    committed: bool = False

    def stage_op(self, op: Callable[[sqlite3.Connection, str, int], None]) -> None:
        """Stage a write ``op(conn, save_id, turn_id)``, run inside the turn's transaction."""
        self.staged_ops.append(op)

    def stage_kv(self, mod_id: str, key: str, value_json: str | None, step: int) -> None:
        """Stage a ``Mod_KV`` write (``value_json=None`` deletes), committed with the turn."""
        self.kv_writes.append((mod_id, key, value_json, int(step)))

    def get_staged_kv(self, mod_id: str, key: str) -> Any:
        """Last value staged for (mod, key) in this batch: JSON text, the deletion
        marker of :mod:`axiom.kernel.kv_store`, or None when nothing is staged."""
        from axiom.kernel.kv_store import _DELETED
        for m, k, value_json, _step in reversed(self.kv_writes):
            if m == mod_id and k == key:
                return _DELETED if value_json is None else value_json
        return None

    def stage_event(
        self,
        event_type: str,
        payload: Any = None,
        target_entity: str = "system",
        *,
        save_id: str | None = None,
        turn_id: int | None = None,
    ) -> None:
        """Stage an event to be written into Event_Log at commit time."""
        self.events.append({
            "save_id": save_id,
            "turn_id": turn_id,
            "event_type": event_type,
            "target_entity": target_entity,
            "payload": payload if payload is not None else {},
        })

    def commit_all(self, conn: sqlite3.Connection, save_id: str, turn_id: int) -> None:
        """Atomically commit all staged mutations inside a single transaction."""
        if self.committed:
            return

        with conn:
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

            # 5. Mods' own tables (timeline, fired events...), in staging order
            for op in self.staged_ops:
                op(conn, save_id, turn_id)

            # 6. Events batch into Event_Log & State_Cache update
            event_tuples: list[tuple[str, int, str, str, Any]] = []
            for ev in self.events:
                if isinstance(ev, (tuple, list)):
                    event_tuples.append(tuple(ev))
                elif isinstance(ev, dict):
                    s = ev.get("save_id") or save_id
                    t = ev.get("turn_id") if ev.get("turn_id") is not None else turn_id
                    event_tuples.append((
                        s,
                        t,
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

            # 7. Mods' versioned key-values (ctx.store), same transaction as the turn
            if self.kv_writes:
                from axiom.kernel.kv_store import _kv_write
                from axiom.schema import ensure_mod_kv_table
                ensure_mod_kv_table(conn)
                for mod_id, key, value_json, step in self.kv_writes:
                    _kv_write(conn, save_id, mod_id, key, value_json, step)

            # 8. End-of-turn captures of every declared storage (snapshots), the
            # disabled mods' included: a later rewind to this turn finds its state.
            from axiom.storage_registry import execute_snapshots
            execute_snapshots(conn, save_id, turn_id)

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

    # When a stat has not been materialized in State_Cache yet, seed it from
    # the universe base stats (Entity_Stats) so a delta starts from the base value.
    try:
        base_rows = conn.execute(
            f"SELECT entity_id, stat_key, stat_value FROM Entity_Stats "
            f"WHERE entity_id IN ({placeholders});",
            (*entity_ids,),
        ).fetchall()
        for r in base_rows:
            cache.setdefault(r["entity_id"], {}).setdefault(r["stat_key"], str(r["stat_value"]))
    except sqlite3.OperationalError:
        # Table Entity_Stats might not exist in some minimal test databases
        pass

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
