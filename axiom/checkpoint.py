"""
database/checkpoint.py

Checkpoint and rewind management for Axiom AI saves.

The CheckpointManager exposes the rewind primitive (deleting future events
and rebuilding the State_Cache), a save listing helper, and the destructive
Hardcore-mode save deletion.
"""

import os
import shutil
import sqlite3
from pathlib import Path

from axiom.schema import get_connection
from axiom.events import EventSourcer


class CheckpointManager:
    """Manages save checkpoints, rewinds, and Hardcore deletion for one universe.

    Args:
        db_path: Filesystem path to an existing universe .db file created
                 by database.schema.create_universe_db().
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._event_sourcer = EventSourcer(db_path)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rewind(self, save_id: str, target_turn_id: int) -> dict[str, int]:
        """Revert a save to its state at target_turn_id.

        Comprehensive and atomic: in a single transaction it removes everything
        recorded after the target turn and rebuilds every derived view to its
        turn-N state:

          1. Count the future events to delete (for the summary).
          2. DELETE the future ``Event_Log`` rows, plus the ``Snapshots`` and
             ``Timeline`` rows for later turns.
          3. Roll back living-mode memory: future ``Facts`` are dropped and
             beliefs are recomputed from their surviving sources
             (:func:`axiom.observations.rollback_observations`).
          4. Restore temporary modifiers (buffs/debuffs) to their turn-N state
             from the per-turn snapshot
             (:func:`axiom.modifiers.rollback_modifiers`) — they decay in minutes
             and are not event-sourced, so they cannot be replayed.
          5. Un-fire scheduled events that fired after the target turn, so they
             can trigger again when the clock re-crosses their minute.
          6. Rebuild ``State_Cache`` from the surviving events.

        Note: the semantic memory store is a separate concern, rolled back by the
        caller via :meth:`axiom.memory.VectorMemory.rollback`.

        Args:
            save_id:        The save to rewind.
            target_turn_id: The turn to revert to (inclusive).  All events
                            with turn_id strictly greater than this value are
                            permanently removed.

        Returns:
            A summary dict: A dict with keys deleted_events and rebuilt_to_turn.

        Raises:
            sqlite3.Error: On any database failure.
        """
        with get_connection(self._db_path) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM Event_Log
                WHERE save_id = ? AND turn_id > ?;
                """,
                (save_id, target_turn_id),
            ).fetchone()
            deleted_count: int = row[0]

            conn.execute(
                """
                DELETE FROM Event_Log
                WHERE save_id = ? AND turn_id > ?;
                """,
                (save_id, target_turn_id),
            )
            
            # Clean up snapshots and timeline entries for future turns
            conn.execute(
                "DELETE FROM Snapshots WHERE save_id = ? AND turn_id > ?;",
                (save_id, target_turn_id)
            )
            conn.execute(
                "DELETE FROM Timeline WHERE save_id = ? AND turn_id > ?;",
                (save_id, target_turn_id)
            )

            # Living-mode structured facts are turn-tagged → drop the future ones
            # in this same transaction so events and derived facts roll back
            # atomically. ensure_ first: older save DBs may predate the table.
            from axiom.schema import ensure_facts_table
            ensure_facts_table(conn)
            conn.execute(
                "DELETE FROM Facts WHERE save_id = ? AND turn_id > ?;",
                (save_id, target_turn_id)
            )

            # Living-mode beliefs (Phase 3) derive from several turns, so they
            # cannot just be deleted by turn_id: drop those created after the
            # target and recompute the survivors from their sources at turns
            # <= target — in this same transaction as the facts they build on.
            from axiom.observations import rollback_observations
            rollback_observations(conn, save_id, target_turn_id)

            # Temporary modifiers (buffs/debuffs) decay in minutes and aren't
            # event-sourced, so they can't be replayed: restore them from the
            # per-turn snapshot captured at the target turn (TICKET-074).
            from axiom.modifiers import rollback_modifiers
            rollback_modifiers(conn, save_id, target_turn_id)

            # Scheduled events fired *after* the target turn must be un-fired so
            # they can trigger again once the in-game clock re-crosses their
            # minute (TICKET-075). Keyed by the turn they fired on; legacy rows
            # (fired_turn_id default 0) stay fired. ensure_ first: older save DBs
            # predate the column.
            from axiom.schema import ensure_fired_event_turn_column
            ensure_fired_event_turn_column(conn)
            conn.execute(
                "DELETE FROM Fired_Scheduled_Events WHERE save_id = ? AND fired_turn_id > ?;",
                (save_id, target_turn_id),
            )

            conn.commit()

        self._event_sourcer.rebuild_state_cache(save_id, up_to_turn_id=target_turn_id)

        return {"deleted_events": deleted_count, "rebuilt_to_turn": target_turn_id}

    def list_checkpoints(self, save_id: str) -> list[int]:
        """Return the distinct turn IDs present in Event_Log for a save, ascending.

        This list represents the turns the player could rewind to.  The UI
        can use it to populate a "rewind to turn …" selector.

        Args:
            save_id: The save whose checkpoint turns are requested.

        Returns:
            Sorted list of unique turn_id integers.  Empty list if the save
            has no recorded events.

        Raises:
            sqlite3.Error: On any database failure.
        """
        with get_connection(self._db_path) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT turn_id FROM Event_Log
                WHERE save_id = ?
                ORDER BY turn_id ASC;
                """,
                (save_id,),
            ).fetchall()
        return [row[0] for row in rows]

    def delete_save(self, save_id: str, universe_dir: str) -> None:
        """Irrevocably delete a save and its associated universe directory.

        Intended exclusively for Hardcore mode upon player death.  This method:
          1. Removes the save row from the database (cascades to Event_Log, etc).
          2. Attempts to delete the universe_dir from the filesystem.

        Args:
            save_id:      The save to erase from the database.
            universe_dir: Absolute path to the universe directory to delete.

        Raises:
            OSError: If the directory cannot be deleted after multiple retries.
            FileNotFoundError: If universe_dir does not exist.
            sqlite3.Error: On any database failure.
        """
        dir_path = Path(universe_dir)
        if not dir_path.exists():
            # If the dir is missing, we still want to clean up the DB
            pass

        # 1. Remove from database (cascades to Event_Log and State_Cache)
        # We do this FIRST because if the DB delete fails, we shouldn't delete files.
        with get_connection(self._db_path) as conn:
            conn.execute("DELETE FROM Saves WHERE save_id = ?;", (save_id,))
            conn.commit()

        # 2. Irrevocably delete the filesystem directory
        if dir_path.exists():
            import time
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    shutil.rmtree(str(dir_path))
                    break
                except OSError as exc:
                    if attempt == max_retries - 1:
                        raise OSError(
                            f"Failed to delete universe directory after {max_retries} attempts: {exc}. "
                            "Some files may be locked by another process."
                        ) from exc
                    time.sleep(0.5) # Wait for locks to release
