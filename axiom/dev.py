"""axiom.dev — Universe-as-Code: dev mode with hot reload.

`axiom dev <src_dir>` watches the source tree and, on every change,
recompiles the **definition** into the target `.db`. The real "modder" mode:
edit `entities/bob.toml` in an editor and see the effect on the next turn.

Key point: legacy saves may live in the **same `.db`** as the definition. A
full `compile_universe` rebuilds the file from scratch and would destroy
games in progress. Hot reload therefore goes through `refresh_definition`:
an **in-place** update of the definition tables only, in a single
transaction, runtime tables untouched (Saves, Event_Log, State_Cache,
Snapshots, Timeline, Items_Inventory, Active_Modifiers,
Fired_Scheduled_Events).

FK constraint: three definition tables have runtime children with
`ON DELETE CASCADE` — `Entities` (Items_Inventory, Active_Modifiers),
`Item_Definitions` (Items_Inventory), `Scheduled_Events`
(Fired_Scheduled_Events). For those, the sync uses targeted
UPDATE/INSERT/DELETE statements (a delete-all-then-reinsert would purge the
children of kept rows). A row removed from the source loses its runtime
children: that is intended (the text is the truth).

Zero Qt dependency: pure engine, drivable from the CLI. The watch is a
`hash_directory` polling loop (no watchdog dependency; universe trees are
small, hashing is instant).
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Callable

from axiom.compile import (
    CACHE_DB_NAME,
    CACHE_DIRNAME,
    CACHE_HASH_NAME,
    CompileError,
    _parse_tree,
    compile_universe,
    hash_directory,
)

# ---------------------------------------------------------------------------
# Refresh in-place de la définition
# ---------------------------------------------------------------------------

def refresh_definition(src_dir: str | Path, db_path: str | Path | None = None) -> Path:
    """Recompile the universe definition into an existing `.db`, in place.

    Runtime/save tables are not touched. When the `.db` does not exist yet,
    this is equivalent to `compile_universe(force=True)`.

    Args:
        src_dir: Universe source folder (contains universe.toml).
        db_path: Target `.db`. Defaults to `<src_dir>/.axiom-cache/universe.db`.

    Returns:
        The path of the refreshed `.db`.

    Raises:
        CompileError: malformed source (the `.db` is left unchanged, the transaction is rolled back).
    """
    src_dir = Path(src_dir)
    if not src_dir.is_dir():
        raise CompileError(f"Source folder not found: {src_dir}")
    if db_path is None:
        db_path = src_dir / CACHE_DIRNAME / CACHE_DB_NAME
    db_path = Path(db_path)

    if not db_path.exists():
        return compile_universe(src_dir, db_path, force=True)

    parsed = _parse_tree(src_dir)  # lève CompileError avant d'ouvrir la DB

    # Provenance des entités : les DBs d'avant la colonne `origin` marquent tout
    # 'definition' par défaut → au premier refresh, on « amnistie » les entités
    # absentes de la source (joueur, PNJ découverts en jeu) au lieu de les
    # supprimer. Ensuite la frontière est stricte.
    from axiom.schema import migrate_entities_origin_column
    amnesty = migrate_entities_origin_column(str(db_path))

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
        # Les FK sont vérifiées au COMMIT : l'ordre des opérations dans la
        # transaction (ex. Locations avec parent_id) devient indifférent.
        conn.execute("PRAGMA defer_foreign_keys=ON;")
        conn.execute("BEGIN;")
        try:
            _sync_definition(conn, parsed, amnesty=amnesty)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    finally:
        conn.close()

    # Le hash de cache n'a de sens que pour le cache par défaut de la source :
    # rafraîchir une autre cible (ex. un save db, §7.6) ne doit pas marquer le
    # cache univers comme frais alors qu'il ne l'est pas.
    if db_path == src_dir / CACHE_DIRNAME / CACHE_DB_NAME:
        hash_file = src_dir / CACHE_DIRNAME / CACHE_HASH_NAME
        hash_file.parent.mkdir(parents=True, exist_ok=True)
        hash_file.write_text(hash_directory(src_dir), encoding="utf-8")
    return db_path


def ensure_compiled(src_dir: str | Path, db_path: str | Path | None = None) -> Path:
    """Guarantee an up-to-date compiled cache **without ever destroying saves**.

    Use this wherever a folder universe must be made playable (Hub,
    `axiom play`): missing cache -> full compilation; stale cache -> in-place
    `refresh_definition` (a full `compile_universe` would rebuild the file and
    erase any saves it contains); fresh cache -> no-op.

    Returns:
        The path of the playable `.db`.
    """
    src_dir = Path(src_dir)
    if db_path is None:
        db_path = src_dir / CACHE_DIRNAME / CACHE_DB_NAME
    db_path = Path(db_path)

    if not db_path.exists():
        return compile_universe(src_dir, db_path, force=True)

    hash_file = src_dir / CACHE_DIRNAME / CACHE_HASH_NAME
    if (
        hash_file.exists()
        and hash_file.read_text(encoding="utf-8").strip() == hash_directory(src_dir)
    ):
        return db_path
    return refresh_definition(src_dir, db_path)


def _sync_definition(
    conn: sqlite3.Connection,
    parsed: dict[str, Any],
    amnesty: bool = False,
) -> None:
    """Aligne les tables de définition sur l'arbo parsée (runtime intact)."""
    # --- Tables sans enfant runtime : remplacement complet --------------------
    conn.execute("DELETE FROM Universe_Meta;")
    conn.executemany(
        "INSERT INTO Universe_Meta (key, value) VALUES (?, ?);",
        list(parsed["meta"].items()),
    )

    conn.execute("DELETE FROM Stat_Definitions;")
    conn.executemany(
        "INSERT INTO Stat_Definitions (stat_id, name, description, value_type, parameters) "
        "VALUES (?, ?, ?, ?, ?);",
        parsed["stat_definitions"],
    )

    conn.execute("DELETE FROM Rules;")
    conn.executemany(
        "INSERT INTO Rules (rule_id, priority, conditions, actions, target_entity) "
        "VALUES (?, ?, ?, ?, ?);",
        parsed["rules"],
    )

    conn.execute("DELETE FROM Lore_Book;")
    conn.executemany(
        "INSERT INTO Lore_Book (entry_id, category, name, keywords, content) "
        "VALUES (?, ?, ?, ?, ?);",
        parsed["lore"],
    )

    conn.execute("DELETE FROM Story_Setup;")
    conn.executemany(
        "INSERT INTO Story_Setup (setup_id, question, type, options, max_selections, priority) "
        "VALUES (?, ?, ?, ?, ?, ?);",
        parsed["setup"],
    )

    conn.execute("DELETE FROM Location_Connections;")
    conn.execute("DELETE FROM Locations;")
    conn.executemany(
        "INSERT INTO Locations (location_id, name, scale, parent_id, description, x, y) "
        "VALUES (?, ?, ?, ?, ?, ?, ?);",
        parsed["locations"],
    )
    conn.executemany(
        "INSERT INTO Location_Connections (source_id, target_id, distance_km) "
        "VALUES (?, ?, ?);",
        parsed["connections"],
    )

    # --- Tables avec enfants runtime en CASCADE : sync ciblé -------------------
    _sync_entities(conn, parsed["entities"], amnesty=amnesty)
    _sync_by_pk(
        conn,
        table="Item_Definitions",
        pk="item_id",
        columns=("item_id", "name", "description", "category", "weight", "rarity"),
        rows=parsed["items"],
    )
    _sync_by_pk(
        conn,
        table="Scheduled_Events",
        pk="event_id",
        columns=("event_id", "trigger_minute", "title", "description"),
        rows=parsed["events"],
    )


def _sync_entities(
    conn: sqlite3.Connection,
    entities: list[tuple[tuple, dict]],
    amnesty: bool = False,
) -> None:
    """Sync Entities + Entity_Stats, en ne gérant QUE les entités de définition.

    Les entités `origin='runtime'` (joueur, PNJ découverts en jeu) ne sont
    jamais touchées par la source — sauf si la source revendique leur id
    (l'entité redevient alors 'definition'). `amnesty=True` (première migration
    de la colonne) requalifie en 'runtime' les entités absentes de la source au
    lieu de les supprimer.
    """
    rows = [row for row, _stats in entities]
    incoming = {row[0] for row in rows}
    existing: dict[str, str] = {
        r[0]: r[1] for r in conn.execute("SELECT entity_id, origin FROM Entities;")
    }
    definition_ids = {eid for eid, origin in existing.items() if origin == "definition"}

    removed = sorted(definition_ids - incoming)
    if removed:
        if amnesty:
            conn.executemany(
                "UPDATE Entities SET origin = 'runtime' WHERE entity_id = ?;",
                [(eid,) for eid in removed],
            )
        else:
            conn.executemany(
                "DELETE FROM Entities WHERE entity_id = ?;",
                [(eid,) for eid in removed],
            )

    for row in rows:
        entity_id, entity_type, name, description, is_active = row
        if entity_id in existing:
            conn.execute(
                "UPDATE Entities SET entity_type = ?, name = ?, description = ?, "
                "is_active = ?, origin = 'definition' WHERE entity_id = ?;",
                (entity_type, name, description, is_active, entity_id),
            )
        else:
            conn.execute(
                "INSERT INTO Entities (entity_id, entity_type, name, description, is_active, origin) "
                "VALUES (?, ?, ?, ?, ?, 'definition');",
                row,
            )

    # Entity_Stats (valeurs de base) : remplacées pour les entités de définition
    # uniquement ; celles des entités runtime (stats du joueur…) survivent.
    conn.execute(
        "DELETE FROM Entity_Stats WHERE entity_id IN "
        "(SELECT entity_id FROM Entities WHERE origin = 'definition');"
    )
    for row, stats in entities:
        conn.executemany(
            "INSERT INTO Entity_Stats (entity_id, stat_key, stat_value) VALUES (?, ?, ?);",
            [(row[0], k, v) for k, v in stats.items()],
        )


def _sync_by_pk(
    conn: sqlite3.Connection,
    table: str,
    pk: str,
    columns: tuple[str, ...],
    rows: list[tuple],
) -> None:
    """UPDATE les lignes existantes, INSERT les nouvelles, DELETE les retirées.

    Un UPDATE ne déclenche pas les `ON DELETE CASCADE` : les enfants runtime des
    lignes conservées survivent. Seules les lignes absentes de la source sont
    supprimées (cascade voulue).
    """
    existing = {r[0] for r in conn.execute(f"SELECT {pk} FROM {table};")}
    incoming = {row[0] for row in rows}

    removed = existing - incoming
    if removed:
        conn.executemany(
            f"DELETE FROM {table} WHERE {pk} = ?;",
            [(pk_value,) for pk_value in sorted(removed)],
        )

    non_pk = [c for c in columns if c != pk]
    set_clause = ", ".join(f"{c} = ?" for c in non_pk)
    placeholders = ", ".join("?" for _ in columns)
    for row in rows:
        values = dict(zip(columns, row))
        if row[0] in existing:
            conn.execute(
                f"UPDATE {table} SET {set_clause} WHERE {pk} = ?;",
                [values[c] for c in non_pk] + [row[0]],
            )
        else:
            conn.execute(
                f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders});",
                row,
            )


# ---------------------------------------------------------------------------
# Boucle de surveillance (polling)
# ---------------------------------------------------------------------------

def poll_once(
    src_dir: str | Path,
    db_path: str | Path | None,
    last_hash: str | None,
) -> tuple[str, bool]:
    """One watch iteration: recompile when the source changed since `last_hash`.

    Args:
        src_dir:   Watched source folder.
        db_path:   Target `.db` (None = default cache).
        last_hash: Hash from the previous iteration (None = first pass).

    Returns:
        Tuple (current hash, True when a refresh was performed).

    Raises:
        CompileError: the source changed but is malformed. The current hash is carried by the exception (`src_hash` attribute) so the caller can record it and avoid retrying the same content in a loop.
    """
    src_dir = Path(src_dir)
    current = hash_directory(src_dir)
    if current == last_hash:
        return current, False
    try:
        refresh_definition(src_dir, db_path)
    except CompileError as exc:
        exc.src_hash = current
        raise
    return current, True


def watch_universe(
    src_dir: str | Path,
    db_path: str | Path | None = None,
    interval: float = 1.0,
    on_event: Callable[[str], None] = print,
    should_stop: Callable[[], bool] | None = None,
) -> None:
    """Watch the source tree and recompile the definition on every change.

    A momentarily malformed source (mid-typing save, invalid TOML) is reported
    through `on_event` but does not kill the loop: the next fix triggers a
    refresh again.

    Args:
        src_dir:     Universe source folder.
        db_path:     Target `.db` (None = `<src>/.axiom-cache/universe.db`).
        interval:    Polling period in seconds.
        on_event:    Log callback (one line per event).
        should_stop: Optional predicate tested at each iteration (for tests /
                     integration); None = loop until KeyboardInterrupt.
    """
    src_dir = Path(src_dir)
    target = Path(db_path) if db_path else src_dir / CACHE_DIRNAME / CACHE_DB_NAME

    last_hash: str | None = None
    first = True
    while True:
        if should_stop is not None and should_stop():
            return
        try:
            last_hash, refreshed = poll_once(src_dir, db_path, last_hash)
            if refreshed:
                msg = "Definition compiled" if first else "Change detected — definition reloaded"
                on_event(f"{msg} → {target}")
        except CompileError as exc:
            # Hash mémorisé : on ne re-tente que si la source change à nouveau.
            last_hash = getattr(exc, "src_hash", last_hash)
            on_event(f"Invalid source (awaiting fix): {exc}")
        first = False
        time.sleep(interval)
