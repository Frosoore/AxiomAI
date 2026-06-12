"""
axiom/universe.py

Headless representation of an Axiom universe (a `.axiom` file = SQLite database).

Exposes the metadata (name, system prompt) and the list of saves, with no Qt
dependency whatsoever. Entry point: `Universe.load(path)`.
"""

from __future__ import annotations

from pathlib import Path

from axiom.schema import get_connection


class Universe:
    """A loaded universe (read-only view of its metadata).

    Attributes:
        path:          Path of the universe file (.axiom / SQLite .db).
        name:          Display name of the universe.
        system_prompt: Founding system prompt handed to the narrator.
    """

    def __init__(self, path: str, name: str, system_prompt: str) -> None:
        self.path = str(path)
        self.name = name
        self.system_prompt = system_prompt

    @classmethod
    def load(cls, universe_path: str | Path) -> "Universe":
        """Load a universe from its SQLite file.

        Args:
            universe_path: Path to the existing universe file.

        Returns:
            A `Universe` instance populated from `Universe_Meta`.
        """
        path = str(universe_path)
        with get_connection(path) as conn:
            rows = conn.execute("SELECT key, value FROM Universe_Meta;").fetchall()
        meta = {row[0]: row[1] for row in rows}
        # `universe_name` est la clé canonique (db_helpers, Creator Studio, compile) ;
        # `name` est un repli legacy (TICKET-023).
        name = meta.get("universe_name") or meta.get("name") or Path(path).stem
        system_prompt = meta.get("system_prompt", "")
        return cls(path, name, system_prompt)

    def list_saves(self) -> list[dict]:
        """List this universe's saves (separate save files + embedded legacy ones)."""
        from axiom.savestore import list_saves
        return list_saves(self.path)
