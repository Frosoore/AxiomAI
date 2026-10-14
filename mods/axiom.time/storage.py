"""mods/axiom.time/storage.py

Save data and timeline queries for axiom.time: the in-game clock history (Timeline)
and fired scheduled events. Declared in mod.toml and run by the kernel even while
the mod is disabled: only this module is loaded then.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from axiom.schema import get_connection


class TimelineStorage:
    """Time storage provider registered via [storage.timeline]."""

    @staticmethod
    def get_current_time(db_path_or_conn: Any, save_id: str) -> int:
        if isinstance(db_path_or_conn, sqlite3.Connection):
            try:
                row = db_path_or_conn.execute(
                    "SELECT MAX(in_game_time) FROM Timeline WHERE save_id = ?;",
                    (save_id,),
                ).fetchone()
                return int(row[0]) if row and row[0] is not None else 0
            except (sqlite3.Error, Exception):
                return 0

        try:
            with get_connection(str(db_path_or_conn)) as conn:
                row = conn.execute(
                    "SELECT MAX(in_game_time) FROM Timeline WHERE save_id = ?;",
                    (save_id,),
                ).fetchone()
                return int(row[0]) if row and row[0] is not None else 0
        except (sqlite3.Error, FileNotFoundError, Exception):
            return 0

    @staticmethod
    def get_turn_at_minute(conn: sqlite3.Connection, save_id: str, minute: int) -> int:
        try:
            row = conn.execute(
                "SELECT MAX(turn_id) FROM Timeline WHERE save_id = ? AND in_game_time <= ?;",
                (save_id, int(minute)),
            ).fetchone()
            return int(row[0]) if row and row[0] is not None else 0
        except (sqlite3.Error, Exception):
            return 0

    @staticmethod
    def get_in_game_minutes_at(conn: sqlite3.Connection, save_id: str, turn_id: int) -> int:
        try:
            row = conn.execute(
                "SELECT in_game_time FROM Timeline WHERE save_id = ? AND turn_id <= ? "
                "ORDER BY turn_id DESC LIMIT 1;",
                (save_id, turn_id),
            ).fetchone()
            return int(row[0]) if row and row[0] is not None else 0
        except (sqlite3.Error, Exception):
            return 0

    @staticmethod
    def record_initial_time(
        conn: sqlite3.Connection,
        save_id: str,
        in_game_minutes: int,
        description: str = "Save imported",
    ) -> None:
        conn.execute(
            "INSERT INTO Timeline (save_id, turn_id, in_game_time, description) "
            "VALUES (?, 0, ?, ?);",
            (save_id, int(in_game_minutes), description),
        )


get_current_time = TimelineStorage.get_current_time
get_turn_at_minute = TimelineStorage.get_turn_at_minute
get_in_game_minutes_at = TimelineStorage.get_in_game_minutes_at
record_initial_time = TimelineStorage.record_initial_time
