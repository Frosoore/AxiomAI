"""
workers/db_helpers.py

Synchronous database helper functions for one-time UI bootstrap reads.

These are small, fast, lightweight operations that are acceptable to run
on the main thread during view construction or session initialisation
(e.g. reading 1–2 rows of metadata at session start).

All SQL strings in the project are concentrated in database/ and workers/
modules — never in ui/ files — to satisfy the MVC separation mandate.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from axiom.logger import logger
from axiom.schema import get_connection
from axiom.kernel.patcher import patchable

def apply_stat_preset(db_path: str, preset_name: str) -> int:
    """Apply a stat preset to a universe database.

    Args:
        db_path: Path to the universe .db file.
        preset_name: Key in STAT_PRESETS.

    Returns:
        Number of stats successfully added.
    """
    from axiom.presets import STAT_PRESETS, generate_stat_id
    from axiom.schema import migrate_stat_definitions_table

    if preset_name not in STAT_PRESETS:
        return 0

    migrate_stat_definitions_table(db_path)
    stats_to_add = STAT_PRESETS[preset_name]
    added_count = 0

    with get_connection(db_path) as conn:
        for s in stats_to_add:
            try:
                # Check if a stat with the same name already exists
                existing = conn.execute(
                    "SELECT 1 FROM Stat_Definitions WHERE name = ?;",
                    (s["name"],)
                ).fetchone()
                if existing:
                    continue

                stat_id = generate_stat_id(s["name"])
                conn.execute(
                    "INSERT INTO Stat_Definitions (stat_id, name, description, value_type, parameters) "
                    "VALUES (?, ?, ?, ?, ?);",
                    (stat_id, s["name"], s["description"], s["value_type"], json.dumps(s["parameters"]))
                )
                added_count += 1
            except sqlite3.Error:
                continue
        conn.commit()

    return added_count

def read_universe_card_metadata(db_path: str) -> tuple[str, str, str, str]:
    """Read display metadata for a universe card widget.

    Args:
        db_path: Path to the universe .db file.

    Returns:
        Tuple of (universe_name, last_updated_str, difficulty_str, description_str).
        Returns sensible defaults on any error.
    """
    name = Path(db_path).stem.replace("_", " ").title()
    last_updated = "Never"
    difficulty = "Normal"
    description = ""
    try:
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT value FROM Universe_Meta WHERE key = 'universe_name';"
            ).fetchone()
            if row:
                name = str(row["value"]).strip()
            row = conn.execute(
                "SELECT value FROM Universe_Meta WHERE key = 'universe_description';"
            ).fetchone()
            if row:
                description = str(row["value"]).strip()
            row = conn.execute(
                "SELECT player_name, difficulty, last_updated FROM Saves "
                "ORDER BY last_updated DESC LIMIT 1;"
            ).fetchone()
            if row:
                last_updated = str(row["last_updated"])[:10].strip()
                difficulty = str(row["difficulty"]).strip()
    except (sqlite3.Error, FileNotFoundError):
        pass
    return name, last_updated, difficulty, description


def provision_blank_universe(db_path: str, name: str) -> None:
    """Insert default Universe_Meta rows into a freshly provisioned database.

    Args:
        db_path: Path to the universe .db file (already schema-provisioned).
        name:    Human-readable universe name.
    """
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES (?, ?);",
            ("universe_name", name),
        )
        conn.execute(
            "INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES (?, ?);",
            ("universe_description", ""),
        )
        conn.execute(
            "INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES (?, ?);",
            ("World_Tension_Level", "0.3"),
        )
        conn.execute(
            "INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES (?, ?);",
            ("system_prompt", f"You are the narrator of '{name}'."),
        )
        conn.commit()


def create_new_save(
    db_path: str,
    player_name: str,
    difficulty: str,
    player_persona: str = "",
) -> str:
    """Insert a new save row and return its save_id.

    Args:
        db_path:        Path to the universe .db file.
        player_name:    Player's chosen name.
        difficulty:     "Normal" or "Hardcore".
        player_persona: Optional background / persona text for the player.

    Returns:
        The newly created UUID save_id string.
    """
    from axiom.schema import (
        migrate_saves_table,
        migrate_lore_book_table,
        migrate_inventory_tables,
        migrate_saves_difficulty_constraint,
        migrate_active_modifiers_table,
        migrate_indexes,
        migrate_schema,
    )

    migrate_saves_table(db_path)
    migrate_saves_difficulty_constraint(db_path)
    migrate_lore_book_table(db_path)
    migrate_inventory_tables(db_path)
    migrate_active_modifiers_table(db_path)
    migrate_indexes(db_path)
    migrate_schema(db_path)
    save_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path) as conn:
        conn.execute(
            "INSERT INTO Saves (save_id, player_name, difficulty, last_updated, player_persona, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?);",
            (save_id, player_name, difficulty, now, player_persona, now),
        )
        conn.commit()
    return save_id


def load_saves(db_path: str) -> list[dict]:
    """Read all saves for a universe, sorted most-recent first.

    Runs the player_persona migration automatically so older databases
    remain compatible.

    Args:
        db_path: Path to the universe .db file.

    Returns:
        List of save dicts with keys: save_id, player_name, difficulty,
        last_updated, player_persona.
    """
    from axiom.schema import (
        migrate_saves_table,
        migrate_lore_book_table,
        migrate_inventory_tables,
        migrate_saves_difficulty_constraint,
        migrate_active_modifiers_table,
        migrate_indexes,
        migrate_schema,
    )

    try:
        migrate_saves_table(db_path)
        migrate_saves_difficulty_constraint(db_path)
        migrate_lore_book_table(db_path)
        migrate_inventory_tables(db_path)
        migrate_active_modifiers_table(db_path)
        migrate_indexes(db_path)
    except sqlite3.Error:
        logger.exception("Pre-list save migrations failed for %s", db_path)
    try:
        migrate_schema(db_path)
    except sqlite3.Error:
        # A failed upgrade must not hide the playthrough on the Hub.
        logger.exception("Schema migrate failed while listing %s", db_path)
    try:
        with get_connection(db_path) as conn:
            rows = conn.execute(
                "SELECT save_id, player_name, difficulty, last_updated, player_persona, created_at "
                "FROM Saves ORDER BY last_updated DESC;"
            ).fetchall()
        return [
            {
                "save_id": r["save_id"],
                "player_name": r["player_name"],
                "difficulty": r["difficulty"],
                "last_updated": r["last_updated"],
                "player_persona": r["player_persona"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    except (sqlite3.Error, FileNotFoundError):
        return []


def load_rules_for_session(db_path: str) -> list[dict]:
    """Read all rules from a universe database for session initialisation.

    Args:
        db_path: Path to the universe .db file.

    Returns:
        List of rule dicts in canonical Rules Engine schema.
        Empty list if the database cannot be read.
    """
    try:
        with get_connection(db_path) as conn:
            rows = conn.execute(
                "SELECT rule_id, priority, conditions, actions, target_entity "
                "FROM Rules;"
            ).fetchall()
        return [
            {
                "rule_id": r["rule_id"],
                "priority": r["priority"],
                "conditions": json.loads(r["conditions"]) if r["conditions"] else {},
                "actions": json.loads(r["actions"]) if r["actions"] else [],
                "target_entity": r["target_entity"],
            }
            for r in rows
        ]
    except (sqlite3.Error, FileNotFoundError):
        return []


def load_active_entities(db_path: str) -> list[dict]:
    """Read all active entities (with their stats) for session initialisation.

    Mirrors the shape produced by `workers/db_worker.load_entities_and_rules`
    (the list the GUI feeds to `NarrativeWorker`), so a headless `Session` can
    resolve the Companion Hero entity itself instead of relying on the UI.

    Args:
        db_path: Path to the universe .db file.

    Returns:
        List of entity dicts: `{entity_id, entity_type, name, description, stats}`.
        Empty list if the database cannot be read.
    """
    try:
        with get_connection(db_path) as conn:
            e_rows = conn.execute(
                "SELECT entity_id, entity_type, name, description "
                "FROM Entities WHERE is_active = 1;"
            ).fetchall()
            entities = []
            for r in e_rows:
                eid = r["entity_id"]
                stats = {
                    s["stat_key"]: s["stat_value"]
                    for s in conn.execute(
                        "SELECT stat_key, stat_value FROM Entity_Stats "
                        "WHERE entity_id = ?;",
                        (eid,),
                    )
                }
                entities.append(
                    {
                        "entity_id": eid,
                        "entity_type": r["entity_type"],
                        "name": r["name"],
                        "description": r["description"],
                        "stats": stats,
                    }
                )
        return entities
    except (sqlite3.Error, FileNotFoundError):
        return []


def load_definition_stats(db_path: str) -> dict[str, dict[str, str]]:
    """Initial stats from the universe definition (Entity_Stats).

    State_Cache only holds *changes* after play starts. The sidebar and
    ``rebuild_state_cache`` must overlay those changes on this base, or a
    player entity with six authored stats shows as empty / one random key.
    """
    try:
        with get_connection(db_path) as conn:
            rows = conn.execute(
                "SELECT es.entity_id, es.stat_key, es.stat_value "
                "FROM Entity_Stats es "
                "JOIN Entities e ON e.entity_id = es.entity_id "
                "WHERE e.is_active = 1;"
            ).fetchall()
        out: dict[str, dict[str, str]] = {}
        for r in rows:
            out.setdefault(r["entity_id"], {})[r["stat_key"]] = r["stat_value"]
        return out
    except (sqlite3.Error, FileNotFoundError):
        return {}


def get_max_turn_id(db_path: str, save_id: str) -> int:
    """Read the highest turn_id from Event_Log for a save (session resume).

    Args:
        db_path:  Path to the universe .db file.
        save_id:  The save to query.

    Returns:
        The maximum turn_id, or 0 if no events exist.
    """
    try:
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT MAX(turn_id) FROM Event_Log WHERE save_id = ?;",
                (save_id,),
            ).fetchone()
        if row and row[0] is not None:
            return int(row[0])
    except (sqlite3.Error, FileNotFoundError):
        pass
    return 0


def get_current_time(db_path: str, save_id: str) -> int:
    """Read the highest in_game_time from Timeline for a save.

    Args:
        db_path:  Path to the universe .db file.
        save_id:  The save to query.

    Returns:
        The maximum in_game_time in minutes, or 0 if no timeline exists.
    """
    try:
        with get_connection(db_path) as conn:
            row = conn.execute(
                "SELECT MAX(in_game_time) FROM Timeline WHERE save_id = ?",
                (save_id,)
            ).fetchone()
            return row[0] if row and row[0] is not None else 0
    except (sqlite3.Error, FileNotFoundError):
        return 0


@patchable("axiom.db_helpers:get_spatial_context")
def get_spatial_context(db_path: str, location_id: str) -> dict:
    """Fetch the breadcrumb path and immediate neighbors for a location.

    Args:
        db_path: Path to the universe .db file.
        location_id: The ID of the current location.

    Returns:
        Dict with 'breadcrumb' (str), 'description' (str), and 'neighbors' (list of dicts).
    """
    breadcrumb = []
    description = ""
    neighbors = []

    try:
        with get_connection(db_path) as conn:
            # 1. Trace breadcrumbs up to the root
            curr_id = location_id
            visited = set()
            while curr_id and curr_id not in visited:
                visited.add(curr_id)
                row = conn.execute(
                    "SELECT name, parent_id, description FROM Locations WHERE location_id = ?;",
                    (curr_id,)
                ).fetchone()
                if not row:
                    break
                
                if curr_id == location_id:
                    description = row["description"]
                
                breadcrumb.append(row["name"])
                curr_id = row["parent_id"]
            
            breadcrumb.reverse()
            
            # 2. Fetch direct neighbors
            n_rows = conn.execute(
                """
                SELECT l.location_id, l.name, c.distance_km 
                FROM Location_Connections c
                JOIN Locations l ON c.target_id = l.location_id
                WHERE c.source_id = ?;
                """,
                (location_id,)
            ).fetchall()
            neighbors = [dict(r) for r in n_rows]

    except Exception as e:
        logger.error(f"[DB_HELPERS] Error fetching spatial context for {location_id}: {e}")

    return {
        "breadcrumb": " > ".join(breadcrumb) if breadcrumb else "Unknown",
        "description": description,
        "neighbors": neighbors
    }


def create_player_entity(db_path: str, name: str, description: str = "") -> str:
    """Create a player entity (origin='runtime') with its default stats.

    Returns:
        The created entity_id (derived from the name, disambiguated on
        collision).
    """
    import re

    from axiom.schema import migrate_entities_origin_column

    migrate_entities_origin_column(db_path)

    eid = re.sub(r"[^a-z0-9]", "_", name.lower()).strip("_")
    if not eid:
        eid = f"player_{int(datetime.now().timestamp())}"

    with get_connection(db_path) as conn:
        if conn.execute("SELECT 1 FROM Entities WHERE entity_id = ?;", (eid,)).fetchone():
            eid = f"{eid}_{int(datetime.now().timestamp() % 1000)}"

        # origin='runtime' : le joueur n'appartient pas à la définition de
        # l'univers — le hot reload / refresh ne doit jamais y toucher (§7.6).
        conn.execute(
            "INSERT INTO Entities (entity_id, name, entity_type, description, is_active, origin) "
            "VALUES (?, ?, 'player', ?, 1, 'runtime');",
            (eid, name, description),
        )

        # Stats par défaut : 10 pour chaque définition existante (la version
        # avancée lirait `parameters` pour typer la valeur).
        for row in conn.execute("SELECT name FROM Stat_Definitions;").fetchall():
            conn.execute(
                "INSERT INTO Entity_Stats (entity_id, stat_key, stat_value) VALUES (?, ?, ?);",
                (eid, row[0], "10"),
            )
        conn.commit()
    return eid


# ---------------------------------------------------------------------------
# Entity / stat resolution shared by the turn and the mods (LLM aliases)
# ---------------------------------------------------------------------------

def load_entity_meta(db_path: str) -> dict[str, dict[str, str]]:
    """entity_id -> {name, entity_type, entity_role} of the active entities."""
    if not db_path:
        return {}
    try:
        with get_connection(db_path) as conn:
            cols = {c[1] for c in conn.execute("PRAGMA table_info(Entities);")}
            role_sel = "entity_role" if "entity_role" in cols else "entity_type"
            rows = conn.execute(
                f"SELECT entity_id, name, entity_type, {role_sel} AS entity_role "
                "FROM Entities WHERE is_active = 1;"
            ).fetchall()
    except sqlite3.Error:
        return {}
    return {
        r["entity_id"]: {
            "name": r["name"] or "",
            "entity_type": r["entity_type"] or "",
            "entity_role": r["entity_role"] or r["entity_type"] or "",
        }
        for r in rows
    }


def resolve_entity_id(
    raw: str,
    all_stats: dict[str, dict[str, str]],
    meta: dict[str, dict[str, str]] | None = None,
) -> str:
    """Map an LLM alias (any case, the entity's name, 'player') onto the real entity_id."""
    raw = str(raw or "").strip()
    meta = meta or {}
    if not raw:
        return raw
    if raw in all_stats or raw in meta:
        return raw
    lower = raw.lower()
    for eid in list(all_stats) + [k for k in meta if k not in all_stats]:
        if eid.lower() == lower:
            return eid
    for eid, info in meta.items():
        if (info.get("name") or "").lower() == lower:
            return eid
    if lower == "player":
        players = [
            eid for eid, info in meta.items()
            if info.get("entity_role") == "player" or info.get("entity_type") == "player"
        ]
        if len(players) == 1:
            return players[0]
        if "player" in all_stats or "player" in meta:
            return "player"
    return raw


def load_defined_stat_names(db_path: str) -> set[str]:
    """Lowercased names and ids of the universe's stat definitions."""
    if not db_path:
        return set()
    try:
        with get_connection(db_path) as conn:
            rows = conn.execute("SELECT name, stat_id FROM Stat_Definitions;").fetchall()
    except sqlite3.Error:
        return set()
    return {str(r[0]).lower() for r in rows if r[0]} | {str(r[1]).lower() for r in rows if r[1]}

