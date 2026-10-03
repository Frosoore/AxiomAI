"""axiom/kernel/kv_store.py

Per-mod versioned key-value storage (DOC §10.2, policy ``versioned_kv``), exposed as
``ctx.store``. Rows live in the kernel table ``Mod_KV`` with a validity interval
``[from_step, to_step)``: the storage registry rewinds and forks them like any other
save data, without a line of rewind code in the mod (D7).

Two ways to use it:

- **during a turn** (the turn context a hook or output-field handler receives)::

      hunger = ctx.store.get(turn_ctx, "hunger", 100)
      ctx.store.set(turn_ctx, "hunger", hunger - 5)

  The write is staged in the turn's write batch and committed with the turn, in the
  same transaction: a cancelled or failed turn leaves nothing behind (0d).
  ``get`` sees the values staged earlier in the same turn.

- **outside a turn** (UI, background job): ``get_at`` / ``set_at`` / ``delete_at`` /
  ``list_keys`` with an explicit save database, save id and step — the step is
  required, so a value never silently lands "since the beginning of the game".
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

#: Staged-write marker for a deletion.
_DELETED = object()


def _kv_write(
    conn: sqlite3.Connection,
    save_id: str,
    mod_id: str,
    key: str,
    value_json: str | None,
    step: int,
) -> None:
    """Write (or delete, ``value_json=None``) ``key`` valid from ``step``, on the caller's
    transaction. Steps must not go backwards: a value is never written before the
    current one (rewind first)."""
    step = int(step)
    active = conn.execute(
        "SELECT from_step FROM Mod_KV "
        "WHERE save_id = ? AND mod_id = ? AND key = ? AND to_step IS NULL;",
        (save_id, mod_id, key),
    ).fetchone()
    if active is not None and step < active[0]:
        raise ValueError(
            f"Mod_KV '{mod_id}:{key}': write at step {step} before the current value "
            f"(step {active[0]}); rewind the save first."
        )
    if value_json is None:
        if active is None:
            return
        if active[0] == step:
            # Created at this very step: deleting it leaves no trace.
            conn.execute(
                "DELETE FROM Mod_KV WHERE save_id = ? AND mod_id = ? AND key = ? AND from_step = ?;",
                (save_id, mod_id, key, step),
            )
        else:
            conn.execute(
                "UPDATE Mod_KV SET to_step = ? "
                "WHERE save_id = ? AND mod_id = ? AND key = ? AND to_step IS NULL;",
                (step, save_id, mod_id, key),
            )
        return
    if active is not None and active[0] == step:
        conn.execute(
            "UPDATE Mod_KV SET value = ? "
            "WHERE save_id = ? AND mod_id = ? AND key = ? AND from_step = ?;",
            (value_json, save_id, mod_id, key, step),
        )
        return
    if active is not None:
        conn.execute(
            "UPDATE Mod_KV SET to_step = ? "
            "WHERE save_id = ? AND mod_id = ? AND key = ? AND to_step IS NULL;",
            (step, save_id, mod_id, key),
        )
    conn.execute(
        "INSERT INTO Mod_KV (save_id, mod_id, key, value, from_step, to_step) "
        "VALUES (?, ?, ?, ?, ?, NULL);",
        (save_id, mod_id, key, value_json, step),
    )


def _decode(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


def _turn_fields(turn_ctx: Any) -> tuple[str, str, int, Any]:
    """(db_path, save_id, step, write_batch) of a turn context."""
    db_path = getattr(turn_ctx, "db_path", "")
    save_id = getattr(turn_ctx, "save_id", "")
    step = getattr(turn_ctx, "step_id", None)
    if step is None:
        step = getattr(turn_ctx, "turn_id", None)
    batch = getattr(turn_ctx, "write_batch", None)
    if not db_path or not save_id or step is None or batch is None:
        raise TypeError(
            "ctx.store.get/set/delete take the turn context a hook receives "
            "(db_path, save_id, step_id, write_batch); outside a turn use get_at/set_at."
        )
    return db_path, save_id, int(step), batch


class ModStore:
    """Versioned key-value store of one mod (``ctx.store``)."""

    def __init__(self, mod_id: str) -> None:
        self.mod_id = mod_id

    # ------------------------------------------------------------------
    # In a turn: staged in the turn's write batch
    # ------------------------------------------------------------------
    def get(self, turn_ctx: Any, key: str, default: Any = None) -> Any:
        """Current value of ``key`` for this turn (values staged this turn included)."""
        db_path, save_id, _step, batch = _turn_fields(turn_ctx)
        staged = batch.get_staged_kv(self.mod_id, key)
        if staged is not None:
            return default if staged is _DELETED else _decode(staged, default)
        return self.get_at(db_path, save_id, key, default)

    def set(self, turn_ctx: Any, key: str, value: Any) -> None:
        """Stage ``key = value`` from this turn's step (committed with the turn)."""
        _db, _save_id, step, batch = _turn_fields(turn_ctx)
        batch.stage_kv(self.mod_id, key, json.dumps(value, ensure_ascii=False), step)

    def delete(self, turn_ctx: Any, key: str) -> None:
        """Stage the deletion of ``key`` from this turn's step."""
        _db, _save_id, step, batch = _turn_fields(turn_ctx)
        batch.stage_kv(self.mod_id, key, None, step)

    # ------------------------------------------------------------------
    # Outside a turn: explicit save and step, written now
    # ------------------------------------------------------------------
    def get_at(
        self,
        db_path: str,
        save_id: str,
        key: str,
        default: Any = None,
        *,
        at_step: int | None = None,
    ) -> Any:
        """Latest value (``at_step=None``) or the value valid at step ``at_step``."""
        from axiom.schema import ensure_mod_kv_table, get_connection

        with get_connection(db_path) as conn:
            ensure_mod_kv_table(conn)
            if at_step is None:
                row = conn.execute(
                    "SELECT value FROM Mod_KV "
                    "WHERE save_id = ? AND mod_id = ? AND key = ? AND to_step IS NULL;",
                    (save_id, self.mod_id, key),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT value FROM Mod_KV "
                    "WHERE save_id = ? AND mod_id = ? AND key = ? "
                    "AND from_step <= ? AND (to_step IS NULL OR to_step > ?);",
                    (save_id, self.mod_id, key, at_step, at_step),
                ).fetchone()
        return _decode(row[0] if row else None, default)

    def set_at(self, db_path: str, save_id: str, key: str, value: Any, *, step: int) -> None:
        """Write ``key = value`` valid from ``step`` (required) and commit."""
        self._write_now(db_path, save_id, key, json.dumps(value, ensure_ascii=False), step)

    def delete_at(self, db_path: str, save_id: str, key: str, *, step: int) -> None:
        """Delete ``key`` from ``step`` (required) and commit."""
        self._write_now(db_path, save_id, key, None, step)

    def list_keys(self, db_path: str, save_id: str, *, at_step: int | None = None) -> list[str]:
        """Keys of this mod that have a value (now, or at step ``at_step``)."""
        from axiom.schema import ensure_mod_kv_table, get_connection

        with get_connection(db_path) as conn:
            ensure_mod_kv_table(conn)
            if at_step is None:
                rows = conn.execute(
                    "SELECT key FROM Mod_KV "
                    "WHERE save_id = ? AND mod_id = ? AND to_step IS NULL ORDER BY key;",
                    (save_id, self.mod_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT DISTINCT key FROM Mod_KV "
                    "WHERE save_id = ? AND mod_id = ? "
                    "AND from_step <= ? AND (to_step IS NULL OR to_step > ?) ORDER BY key;",
                    (save_id, self.mod_id, at_step, at_step),
                ).fetchall()
        return [r[0] for r in rows]

    def _write_now(self, db_path: str, save_id: str, key: str, value_json: str | None, step: int) -> None:
        from axiom.schema import ensure_mod_kv_table, get_connection

        with get_connection(db_path) as conn:  # commits (or rolls back) on exit
            ensure_mod_kv_table(conn)
            _kv_write(conn, save_id, self.mod_id, key, value_json, step)
