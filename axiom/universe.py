"""
axiom/universe.py

Représentation headless d'un univers Axiom (un fichier `.axiom` = base SQLite).

Expose les métadonnées (nom, system prompt) et la liste des sauvegardes, sans
aucune dépendance Qt. Point d'entrée : `Universe.load(path)`.
"""

from __future__ import annotations

from pathlib import Path

from axiom.schema import get_connection
from axiom.db_helpers import load_saves


class Universe:
    """Un univers chargé (lecture seule des métadonnées).

    Attributes:
        path:          Chemin du fichier univers (.axiom / .db SQLite).
        name:          Nom affiché de l'univers.
        system_prompt: Prompt système fondateur passé au narrateur.
    """

    def __init__(self, path: str, name: str, system_prompt: str) -> None:
        self.path = str(path)
        self.name = name
        self.system_prompt = system_prompt

    @classmethod
    def load(cls, universe_path: str | Path) -> "Universe":
        """Charge un univers depuis son fichier SQLite.

        Args:
            universe_path: Chemin vers le fichier univers existant.

        Returns:
            Une instance `Universe` peuplée depuis `Universe_Meta`.
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
        """Retourne la liste des sauvegardes de cet univers."""
        return load_saves(self.path)
