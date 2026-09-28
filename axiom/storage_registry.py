"""axiom/storage_registry.py

Central persistence registry and storage policies for universe definitions and
save states in Axiom AI.

Replaces hardcoded table lists across checkpoint rewind, save forking,
packaging, and savestore copies with unified declarative policies (Phase 0c).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class StoragePolicy(Enum):
    EVENTS = "events"                     # Journal append-only réductible (Event_Log)
    STEP_KEYED = "step_keyed_table"       # Table SQL avec colonne step/turn explicite
    VERSIONED_KV = "versioned_kv"         # Clé-valeur avec borne de validité temporelle
    CUSTOM = "custom"                     # Gestionnaire externe (Vector DB, snapshots, etc.)


@dataclass(frozen=True)
class TableStorageSpec:
    table_name: str
    policy: StoragePolicy
    step_column: str | None = "turn_id"   # Colonne horodatée pour STEP_KEYED
    is_runtime: bool = True               # True = runtime/save, False = définition d'univers
    columns: tuple[str, ...] | None = None
    custom_rewind: Callable[[sqlite3.Connection, str, int], None] | None = None
    custom_fork: Callable[[sqlite3.Connection, str, str, int], None] | None = None


# ---------------------------------------------------------------------------
# Custom Rollback & Fork Callbacks
# ---------------------------------------------------------------------------

def _rewind_observations(conn: sqlite3.Connection, save_id: str, target_turn: int) -> None:
    from axiom.observations import rollback_observations
    rollback_observations(conn, save_id, target_turn)


def _fork_observations(conn: sqlite3.Connection, src_save_id: str, dst_save_id: str, target_turn: int) -> None:
    try:
        rows = conn.execute(
            "SELECT observation_id, subject, statement, proof_count, sources, history, created_turn_id, updated_turn_id, stale "
            "FROM Observations WHERE save_id = ? AND updated_turn_id <= ?;",
            (src_save_id, target_turn),
        ).fetchall()
        conn.executemany(
            "INSERT INTO Observations (observation_id, save_id, subject, statement, proof_count, sources, history, created_turn_id, updated_turn_id, stale) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            [(str(uuid.uuid4()), dst_save_id, r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]) for r in rows],
        )
    except sqlite3.Error:
        pass


def _rewind_mental_models(conn: sqlite3.Connection, save_id: str, target_turn: int) -> None:
    from axiom.mental_models import rollback_mental_models
    rollback_mental_models(conn, save_id, target_turn)


def _fork_mental_models(conn: sqlite3.Connection, src_save_id: str, dst_save_id: str, target_turn: int) -> None:
    try:
        rows = conn.execute(
            "SELECT model_id, subject, summary, sources, created_turn_id, updated_turn_id, stale "
            "FROM Mental_Models WHERE save_id = ? AND updated_turn_id <= ?;",
            (src_save_id, target_turn),
        ).fetchall()
        conn.executemany(
            "INSERT INTO Mental_Models (model_id, save_id, subject, summary, sources, created_turn_id, updated_turn_id, stale) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
            [(str(uuid.uuid4()), dst_save_id, r[1], r[2], r[3], r[4], r[5], r[6]) for r in rows],
        )
    except sqlite3.Error:
        pass


def _rewind_modifiers(conn: sqlite3.Connection, save_id: str, target_turn: int) -> None:
    from axiom.modifiers import rollback_modifiers
    rollback_modifiers(conn, save_id, target_turn)


def _fork_modifiers(conn: sqlite3.Connection, src_save_id: str, dst_save_id: str, target_turn: int) -> None:
    from axiom.saves import _max_turn
    if target_turn < _max_turn(conn, src_save_id):
        from axiom.modifiers import modifiers_at
        mod_rows = [
            {"entity_id": m["entity_id"], "stat_key": m["stat_key"],
             "delta": m["delta"], "minutes_remaining": m["minutes_remaining"]}
            for m in modifiers_at(conn, src_save_id, target_turn)
        ]
        if not mod_rows:
            mod_rows = conn.execute(
                "SELECT entity_id, stat_key, delta, minutes_remaining FROM Active_Modifiers WHERE save_id = ?;",
                (src_save_id,),
            ).fetchall()
    else:
        mod_rows = conn.execute(
            "SELECT entity_id, stat_key, delta, minutes_remaining FROM Active_Modifiers WHERE save_id = ?;",
            (src_save_id,),
        ).fetchall()

    conn.executemany(
        "INSERT INTO Active_Modifiers (modifier_id, save_id, entity_id, stat_key, delta, minutes_remaining) "
        "VALUES (?, ?, ?, ?, ?, ?);",
        [(str(uuid.uuid4()), dst_save_id, r["entity_id"], r["stat_key"], r["delta"], r["minutes_remaining"])
         for r in mod_rows],
    )


def _rewind_inventory(conn: sqlite3.Connection, save_id: str, target_turn: int) -> None:
    from axiom.inventory import rollback_inventory
    rollback_inventory(conn, save_id, target_turn)


def _fork_inventory(conn: sqlite3.Connection, src_save_id: str, dst_save_id: str, target_turn: int) -> None:
    inv_rows = conn.execute(
        "SELECT entity_id, item_id, quantity FROM Items_Inventory WHERE save_id = ?;",
        (src_save_id,),
    ).fetchall()
    conn.executemany(
        "INSERT INTO Items_Inventory (save_id, entity_id, item_id, quantity) VALUES (?, ?, ?, ?);",
        [(dst_save_id, r[0], r[1], r[2]) for r in inv_rows],
    )
    try:
        from axiom.saves import _fork_item_instances
        _fork_item_instances(conn, src_save_id, dst_save_id, target_turn)
    except sqlite3.Error:
        pass


def _rewind_vector_memory(conn: sqlite3.Connection, save_id: str, target_turn: int) -> None:
    pass


def _fork_vector_memory(conn: sqlite3.Connection, src_save_id: str, dst_save_id: str, target_turn: int) -> None:
    pass


# ---------------------------------------------------------------------------
# Canonical Core Storage Registry
# ---------------------------------------------------------------------------

CORE_STORAGE_REGISTRY: list[TableStorageSpec] = [
    # Définition pure (non affectée par le rewind, copiée au fork)
    TableStorageSpec("Universe_Meta", StoragePolicy.VERSIONED_KV, is_runtime=False,
                     columns=("key", "value")),
    TableStorageSpec("Entity_Types", StoragePolicy.VERSIONED_KV, is_runtime=False,
                     columns=("type_id", "name", "role", "description", "is_builtin")),
    TableStorageSpec("Stat_Definitions", StoragePolicy.VERSIONED_KV, is_runtime=False,
                     columns=("stat_id", "name", "description", "value_type", "parameters")),
    TableStorageSpec("Stat_Type_Links", StoragePolicy.VERSIONED_KV, is_runtime=False,
                     columns=("stat_id", "type_id")),
    TableStorageSpec("Entities", StoragePolicy.VERSIONED_KV, is_runtime=False,
                     columns=("entity_id", "entity_type", "entity_role", "name", "description", "is_active", "origin")),
    TableStorageSpec("Entity_Stats", StoragePolicy.VERSIONED_KV, is_runtime=False,
                     columns=("entity_id", "stat_key", "stat_value")),
    TableStorageSpec("Rules", StoragePolicy.VERSIONED_KV, is_runtime=False,
                     columns=("rule_id", "priority", "conditions", "actions", "target_entity")),
    TableStorageSpec("Lore_Book", StoragePolicy.VERSIONED_KV, is_runtime=False,
                     columns=("entry_id", "category", "name", "keywords", "content")),
    TableStorageSpec("Locations", StoragePolicy.VERSIONED_KV, is_runtime=False,
                     columns=("location_id", "name", "scale", "parent_id", "description", "x", "y")),
    TableStorageSpec("Location_Connections", StoragePolicy.VERSIONED_KV, is_runtime=False,
                     columns=("source_id", "target_id", "distance_km")),
    TableStorageSpec("Scheduled_Events", StoragePolicy.VERSIONED_KV, is_runtime=False,
                     columns=("event_id", "trigger_minute", "title", "description")),
    TableStorageSpec("Item_Definitions", StoragePolicy.VERSIONED_KV, is_runtime=False,
                     columns=("item_id", "name", "description", "category", "weight", "rarity", "is_container", "capacity")),
    TableStorageSpec("Story_Setup", StoragePolicy.VERSIONED_KV, is_runtime=False,
                     columns=("setup_id", "question", "type", "options", "max_selections", "priority")),
    TableStorageSpec("Mod_Schema_Versions", StoragePolicy.VERSIONED_KV, is_runtime=False,
                     columns=("mod_id", "schema_version", "installed_at")),

    # Runtime / Sauvegarde (affecté par le rewind et le fork)
    TableStorageSpec("Saves", StoragePolicy.VERSIONED_KV, is_runtime=True,
                     columns=("save_id", "player_name", "difficulty", "last_updated", "player_persona", "created_at")),
    TableStorageSpec("Event_Log", StoragePolicy.EVENTS, step_column="turn_id", is_runtime=True,
                     columns=("event_id", "save_id", "turn_id", "event_type", "target_entity", "payload")),
    TableStorageSpec("Timeline", StoragePolicy.STEP_KEYED, step_column="turn_id", is_runtime=True,
                     columns=("event_id", "save_id", "turn_id", "in_game_time", "description")),
    TableStorageSpec("State_Cache", StoragePolicy.STEP_KEYED, step_column="turn_id", is_runtime=True,
                     columns=("save_id", "entity_id", "stat_key", "stat_value")),
    TableStorageSpec("Snapshots", StoragePolicy.STEP_KEYED, step_column="turn_id", is_runtime=True,
                     columns=("save_id", "turn_id", "state_json")),
    TableStorageSpec("Inventory_Snapshots", StoragePolicy.STEP_KEYED, step_column="turn_id", is_runtime=True,
                     columns=("save_id", "turn_id", "state_json")),
    TableStorageSpec("Modifier_Snapshots", StoragePolicy.STEP_KEYED, step_column="turn_id", is_runtime=True,
                     columns=("save_id", "turn_id", "state_json")),
    TableStorageSpec("Fired_Scheduled_Events", StoragePolicy.STEP_KEYED, step_column="fired_turn_id", is_runtime=True,
                     columns=("save_id", "event_id", "fired_turn_id")),
    TableStorageSpec("Session_Lore", StoragePolicy.STEP_KEYED, step_column="origin_turn", is_runtime=True,
                     columns=("entry_id", "save_id", "category", "name", "keywords", "content", "origin_turn")),
    TableStorageSpec("Facts", StoragePolicy.STEP_KEYED, step_column="turn_id", is_runtime=True,
                     columns=("fact_id", "save_id", "turn_id", "fact_type", "who", "what",
                              "fact_when", "fact_where", "why", "entities", "statement")),
    TableStorageSpec("Observations", StoragePolicy.CUSTOM, is_runtime=True,
                     columns=("observation_id", "save_id", "subject", "statement",
                              "proof_count", "sources", "history", "created_turn_id",
                              "updated_turn_id", "stale"),
                     custom_rewind=_rewind_observations, custom_fork=_fork_observations),
    TableStorageSpec("Mental_Models", StoragePolicy.CUSTOM, is_runtime=True,
                     columns=("model_id", "save_id", "subject", "summary", "sources",
                              "created_turn_id", "updated_turn_id", "stale"),
                     custom_rewind=_rewind_mental_models, custom_fork=_fork_mental_models),
    TableStorageSpec("Active_Modifiers", StoragePolicy.CUSTOM, is_runtime=True,
                     columns=("modifier_id", "save_id", "entity_id", "stat_key", "delta", "minutes_remaining"),
                     custom_rewind=_rewind_modifiers, custom_fork=_fork_modifiers),
    TableStorageSpec("Items_Inventory", StoragePolicy.CUSTOM, is_runtime=True,
                     columns=("save_id", "entity_id", "item_id", "quantity"),
                     custom_rewind=_rewind_inventory, custom_fork=_fork_inventory),
    TableStorageSpec("Item_Instances", StoragePolicy.CUSTOM, is_runtime=True,
                     columns=("instance_id", "save_id", "item_id", "quantity", "holder_kind", "holder_id"),
                     custom_rewind=None, custom_fork=None),
    TableStorageSpec("VectorMemory", StoragePolicy.CUSTOM, is_runtime=True,
                     custom_rewind=_rewind_vector_memory, custom_fork=_fork_vector_memory),
]


# ---------------------------------------------------------------------------
# Public Helper Functions
# ---------------------------------------------------------------------------

def get_definition_tables() -> list[str]:
    """Return all universe definition table names."""
    return [spec.table_name for spec in CORE_STORAGE_REGISTRY if not spec.is_runtime]


def get_runtime_tables() -> list[str]:
    """Return all runtime save table names ordered for safe purge/vacuum (FK children first)."""
    # FK-safe ordering for deletion
    preferred_order = [
        "Fired_Scheduled_Events",
        "Active_Modifiers",
        "Items_Inventory",
        "Item_Instances",
        "Timeline",
        "Snapshots",
        "Modifier_Snapshots",
        "Inventory_Snapshots",
        "Session_Lore",
        "Facts",
        "Observations",
        "Mental_Models",
        "State_Cache",
        "Event_Log",
        "Saves",
    ]
    reg_tables = {spec.table_name for spec in CORE_STORAGE_REGISTRY if spec.is_runtime and spec.table_name != "VectorMemory"}
    ordered = [t for t in preferred_order if t in reg_tables]
    for t in reg_tables:
        if t not in ordered:
            ordered.append(t)
    return ordered


def get_definition_copy_specs() -> list[tuple[str, tuple[str, ...]]]:
    """Return (table_name, columns) pairs for copying universe definitions into a save db."""
    return [
        (spec.table_name, spec.columns)
        for spec in CORE_STORAGE_REGISTRY
        if not spec.is_runtime and spec.columns is not None
    ]


def get_runtime_copy_specs() -> list[tuple[str, tuple[str, ...]]]:
    """Return (table_name, columns) pairs for copying runtime save tables."""
    return [
        (spec.table_name, spec.columns)
        for spec in CORE_STORAGE_REGISTRY
        if spec.is_runtime and spec.columns is not None
    ]


def execute_rewind(conn: sqlite3.Connection, save_id: str, target_turn_id: int) -> dict[str, int]:
    """Execute unified rewind on all registered tables in CORE_STORAGE_REGISTRY."""
    from axiom.schema import (
        ensure_facts_table,
        ensure_fired_event_turn_column,
        ensure_inventory_snapshots_table,
        ensure_modifier_snapshots_table,
    )

    ensure_fired_event_turn_column(conn)
    ensure_facts_table(conn)
    ensure_modifier_snapshots_table(conn)
    ensure_inventory_snapshots_table(conn)

    deleted_count = 0

    # 1. Process EVENTS (Event_Log)
    for spec in CORE_STORAGE_REGISTRY:
        if spec.policy == StoragePolicy.EVENTS:
            row = conn.execute(
                f"SELECT COUNT(*) FROM {spec.table_name} WHERE save_id = ? AND {spec.step_column} > ?;",
                (save_id, target_turn_id),
            ).fetchone()
            if row:
                deleted_count += row[0]
            conn.execute(
                f"DELETE FROM {spec.table_name} WHERE save_id = ? AND {spec.step_column} > ?;",
                (save_id, target_turn_id),
            )

    # 2. Process STEP_KEYED tables
    for spec in CORE_STORAGE_REGISTRY:
        if spec.policy == StoragePolicy.STEP_KEYED and spec.table_name != "State_Cache":
            try:
                conn.execute(
                    f"DELETE FROM {spec.table_name} WHERE save_id = ? AND {spec.step_column} > ?;",
                    (save_id, target_turn_id),
                )
            except sqlite3.Error:
                pass

    # 3. Process CUSTOM handlers
    for spec in CORE_STORAGE_REGISTRY:
        if spec.policy == StoragePolicy.CUSTOM and spec.custom_rewind is not None:
            spec.custom_rewind(conn, save_id, target_turn_id)

    return {"deleted_events": deleted_count, "rebuilt_to_turn": target_turn_id}


def execute_fork(conn: sqlite3.Connection, src_save_id: str, dst_save_id: str, at_turn: int) -> None:
    """Copy all registered runtime tables from src_save_id up to at_turn into dst_save_id."""
    from axiom.schema import ensure_fired_event_turn_column
    ensure_fired_event_turn_column(conn)

    # 1. EVENTS (Event_Log)
    for spec in CORE_STORAGE_REGISTRY:
        if spec.policy == StoragePolicy.EVENTS:
            ev_rows = conn.execute(
                f"SELECT turn_id, event_type, target_entity, payload FROM {spec.table_name} "
                f"WHERE save_id = ? AND {spec.step_column} <= ? ORDER BY event_id ASC;",
                (src_save_id, at_turn),
            ).fetchall()
            conn.executemany(
                f"INSERT INTO {spec.table_name} (save_id, turn_id, event_type, target_entity, payload) "
                "VALUES (?, ?, ?, ?, ?);",
                [(dst_save_id, r[0], r[1], r[2], r[3]) for r in ev_rows],
            )

    # 2. STEP_KEYED
    for spec in CORE_STORAGE_REGISTRY:
        if spec.policy == StoragePolicy.STEP_KEYED:
            if spec.table_name == "Timeline":
                tl_rows = conn.execute(
                    "SELECT turn_id, in_game_time, description FROM Timeline "
                    "WHERE save_id = ? AND turn_id <= ? ORDER BY turn_id ASC;",
                    (src_save_id, at_turn),
                ).fetchall()
                conn.executemany(
                    "INSERT INTO Timeline (save_id, turn_id, in_game_time, description) VALUES (?, ?, ?, ?);",
                    [(dst_save_id, r[0], r[1], r[2]) for r in tl_rows],
                )
            elif spec.table_name == "Session_Lore":
                try:
                    lore_rows = conn.execute(
                        "SELECT category, name, keywords, content, origin_turn FROM Session_Lore "
                        "WHERE save_id = ? AND origin_turn <= ?;",
                        (src_save_id, at_turn),
                    ).fetchall()
                    conn.executemany(
                        "INSERT INTO Session_Lore (entry_id, save_id, category, name, keywords, content, origin_turn) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?);",
                        [(str(uuid.uuid4()), dst_save_id, r[0], r[1], r[2], r[3], r[4]) for r in lore_rows],
                    )
                except sqlite3.Error:
                    pass
            elif spec.table_name == "Fired_Scheduled_Events":
                fired_rows = conn.execute(
                    "SELECT event_id, fired_turn_id FROM Fired_Scheduled_Events WHERE save_id = ?;",
                    (src_save_id,),
                ).fetchall()
                conn.executemany(
                    "INSERT INTO Fired_Scheduled_Events (save_id, event_id, fired_turn_id) VALUES (?, ?, ?);",
                    [(dst_save_id, r[0], r[1]) for r in fired_rows],
                )
            elif spec.table_name == "Facts":
                try:
                    fact_rows = conn.execute(
                        "SELECT fact_id, turn_id, fact_type, who, what, fact_when, fact_where, why, entities, statement "
                        "FROM Facts WHERE save_id = ? AND turn_id <= ?;",
                        (src_save_id, at_turn),
                    ).fetchall()
                    conn.executemany(
                        "INSERT INTO Facts (fact_id, save_id, turn_id, fact_type, who, what, fact_when, fact_where, why, entities, statement) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                        [(str(uuid.uuid4()), dst_save_id, r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9]) for r in fact_rows],
                    )
                except sqlite3.Error:
                    pass

    # 3. CUSTOM
    for spec in CORE_STORAGE_REGISTRY:
        if spec.policy == StoragePolicy.CUSTOM and spec.custom_fork is not None:
            spec.custom_fork(conn, src_save_id, dst_save_id, at_turn)


def register_table_storage(spec: TableStorageSpec) -> None:
    """Register or replace a table storage specification."""
    for i, s in enumerate(CORE_STORAGE_REGISTRY):
        if s.table_name == spec.table_name:
            CORE_STORAGE_REGISTRY[i] = spec
            return
    CORE_STORAGE_REGISTRY.append(spec)


def register_custom_storage(
    table_name: str,
    rewind_callback: Callable[[sqlite3.Connection, str, int], None] | None = None,
    fork_callback: Callable[[sqlite3.Connection, str, str, int], None] | None = None,
) -> None:
    """Register a custom storage handler for non-SQLite or custom rollback/fork needs."""
    spec = TableStorageSpec(
        table_name=table_name,
        policy=StoragePolicy.CUSTOM,
        is_runtime=True,
        custom_rewind=rewind_callback,
        custom_fork=fork_callback,
    )
    register_table_storage(spec)
