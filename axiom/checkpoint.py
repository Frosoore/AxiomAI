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
from typing import Any, Callable

from axiom.schema import get_connection
from axiom.events import EventSourcer
from axiom.logger import logger


_REWIND_BACKUP: Callable[[str, str], Any] | None = None


def set_rewind_backup_handler(handler: Callable[[str, str], Any] | None) -> None:
    """Install the auto-backup made before every rewind: ``handler(db_path, reason)``.

    The application installs ``database.backup_manager.create_auto_backup``
    (the headless engine package cannot import it); without a handler the
    rewind runs without backup.
    """
    global _REWIND_BACKUP
    _REWIND_BACKUP = handler


def _auto_backup(db_path: str, reason: str) -> None:
    handler = _REWIND_BACKUP
    if handler is None:
        return
    if handler(db_path, reason) is None:
        logger.warning("Auto-backup failed before %s of %s; rewinding anyway.", reason, db_path)


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

    def rewind(self, save_id: str, target_turn_id: int, *, backup: bool = True) -> dict[str, int]:
        """Revert a save to its state at target_turn_id — the engine's single rewind path.

        Every frontend goes through here (``Session.rewind`` for web/CLI, the Qt
        ``RewindTask``), so the steps below happen exactly once, in this order:

          1. Bump the save's epoch (:mod:`axiom.epoch`) so a background job that
             captured the old epoch (living-memory distillation) discards its
             writes. Bumping waits for an in-flight guarded write to finish; that
             write is then removed by step 3 (TICKET-102).
          2. Auto-backup of the database file before the destructive change,
             through the handler the application installed with
             :func:`set_rewind_backup_handler` (``backup=False`` skips it).
          3. One SQL transaction through the storage registry
             (:func:`axiom.storage_registry.execute_rewind`): future
             ``Event_Log`` rows and every step-keyed table (Timeline, Snapshots,
             Facts, Session_Lore, fired scheduled events…) cut after the target,
             beliefs / mental models / modifiers / nested inventory restored to
             their turn-N state, ``Saves.last_updated`` touched. Then commit.
          4. Rebuild ``State_Cache`` from the surviving events.
          5. Only after the commit: the external stores registered by mods (the
             semantic memory of ``axiom.rag``, the illustrations of
             ``axiom.illustrations``) — :func:`axiom.storage_registry.execute_external_rewind`.
             If the SQL part failed, they are left untouched (TICKET-100).

        Args:
            save_id:        The save to rewind.
            target_turn_id: The turn to revert to (inclusive).  All events
                            with turn_id strictly greater than this value are
                            permanently removed.
            backup:         Create the auto-backup first (default True).

        Returns:
            A summary dict with keys deleted_events, rebuilt_to_turn and
            external_failures (number of external stores that failed to rewind;
            their errors are logged).

        Raises:
            sqlite3.Error: On any database failure (nothing is committed then).
        """
        from datetime import datetime, timezone

        from axiom.epoch import get_session_epoch_manager
        from axiom.storage_registry import execute_external_rewind, execute_rewind

        get_session_epoch_manager(save_id).bump()

        if backup:
            _auto_backup(self._db_path, f"rewind_to_turn_{target_turn_id}")

        with get_connection(self._db_path) as conn:
            summary = execute_rewind(conn, save_id, target_turn_id, external=False)
            conn.execute(
                "UPDATE Saves SET last_updated = ? WHERE save_id = ?;",
                (datetime.now(timezone.utc).isoformat(), save_id),
            )
            conn.commit()

        self._event_sourcer.rebuild_state_cache(save_id, up_to_turn_id=target_turn_id)

        failed = execute_external_rewind(save_id, target_turn_id)
        summary["external_failures"] = len(failed)
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
