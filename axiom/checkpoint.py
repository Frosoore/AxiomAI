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
          3. Roll back living-mode memory: future ``Facts`` are dropped, beliefs
             are recomputed from their surviving sources
             (:func:`axiom.observations.rollback_observations`) and mental models
             created after the target are dropped / flagged stale
             (:func:`axiom.mental_models.rollback_mental_models`).
          4. Restore temporary modifiers (buffs/debuffs) to their turn-N state
             from the per-turn snapshot
             (:func:`axiom.modifiers.rollback_modifiers`) — they decay in minutes
             and are not event-sourced, so they cannot be replayed.
             Same for the nested inventory
             (:func:`axiom.inventory.rollback_inventory`, TICKET-095) — left
             untouched if the target turn predates inventory snapshots.
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
        from axiom.storage_registry import execute_rewind

        with get_connection(self._db_path) as conn:
            summary = execute_rewind(conn, save_id, target_turn_id)
            conn.commit()

        self._event_sourcer.rebuild_state_cache(save_id, up_to_turn_id=target_turn_id)

        return summary

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
