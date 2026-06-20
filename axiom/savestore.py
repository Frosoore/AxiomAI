"""axiom.savestore — saves stored separately from the universe.

The source tree (and its compiled cache) is the universe **definition**;
play-throughs live in dedicated databases::

    ~/AxiomAI/
    |-- universes/<name>/...                   definition (source + cache)
    `-- saves/<universe key>/save_<uuid>.db    one game (runtime state)

Each save db is **self-contained** — full schema, with a **copy of the
definition tables** taken at creation. Benefits:

- `Session` and the whole engine work unchanged (a single DB path);
- patching the universe does not brick the games (they keep their own
  definition, resynchronised on open via `refresh_definition` — in-place,
  runtime entities and game state survive);
- one save = one portable file (trivial export/import).

Backward compatibility: historical saves embedded in the universe `.db`
remain listed and playable as-is (`storage='embedded'`). Only **new** saves
are created as separate files.

Zero Qt dependency: pure engine.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

from axiom.compile import hash_directory
from axiom.fsutil import replace_with_retry, unlink_with_retry
from axiom.library import universe_root_for
from axiom.schema import create_universe_db

# Tables de définition copiées de l'univers vers chaque save db (colonnes
# explicites = schéma courant ; l'univers source est migré avant copie).
_DEFINITION_COPY: list[tuple[str, tuple[str, ...]]] = [
    ("Universe_Meta", ("key", "value")),
    ("Stat_Definitions", ("stat_id", "name", "description", "value_type", "parameters")),
    ("Entities", ("entity_id", "entity_type", "name", "description", "is_active", "origin")),
    ("Entity_Stats", ("entity_id", "stat_key", "stat_value")),
    ("Rules", ("rule_id", "priority", "conditions", "actions", "target_entity")),
    ("Lore_Book", ("entry_id", "category", "name", "keywords", "content")),
    ("Scheduled_Events", ("event_id", "trigger_minute", "title", "description")),
    ("Item_Definitions", ("item_id", "name", "description", "category", "weight", "rarity")),
    ("Story_Setup", ("setup_id", "question", "type", "options", "max_selections", "priority")),
    ("Locations", ("location_id", "name", "scale", "parent_id", "description", "x", "y")),
    ("Location_Connections", ("source_id", "target_id", "distance_km")),
]

_DDL_SAVE_META = """
CREATE TABLE IF NOT EXISTS Save_Meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class SaveStoreError(Exception):
    """Error from the separate-save store."""


# ---------------------------------------------------------------------------
# Images générées (illustrations de tour) — TICKET-048
#
# Les illustrations vivent hors save db, sous `<data_root>/assets/<save_id>/
# turn_<n>.png`. Elles suivent la save : copiées à la duplication, purgées à
# la suppression, embarquées dans `.axiomsave`, tronquées au rewind. Décision
# assumée : seul le chemin `Session` en génère (pas la file multijoueur).
# ---------------------------------------------------------------------------

def assets_dir_for_save(save_id: str) -> Path:
    """A save's illustrations folder (not created if missing)."""
    from axiom.paths import get_assets_dir

    return get_assets_dir() / save_id


def copy_save_assets(src_save_id: str, dst_save_id: str) -> int:
    """Copy one save's illustrations to another. Returns the number copied."""
    import shutil

    src = assets_dir_for_save(src_save_id)
    if not src.is_dir():
        return 0
    dst = assets_dir_for_save(dst_save_id)
    dst.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in src.glob("turn_*.png"):
        shutil.copyfile(f, dst / f.name)
        count += 1
    return count


def delete_save_assets(save_id: str) -> None:
    """Delete a save's illustrations folder (no-op if missing)."""
    import shutil

    d = assets_dir_for_save(save_id)
    if d.is_dir():
        shutil.rmtree(d, ignore_errors=True)


def truncate_save_assets(save_id: str, last_kept_turn_id: int) -> int:
    """Purge the `turn_<n>.png` files with n > `last_kept_turn_id` (rewind).

    Returns the number of deleted files. Non-conforming names are ignored.
    """
    return truncate_assets_in(assets_dir_for_save(save_id), last_kept_turn_id)


def truncate_assets_in(assets_dir: Path, last_kept_turn_id: int) -> int:
    """Variant of `truncate_save_assets` on an explicit folder (Session with an
    injected data_dir).
    """
    import re

    if not assets_dir.is_dir():
        return 0
    removed = 0
    for f in assets_dir.glob("turn_*.png"):
        m = re.fullmatch(r"turn_(\d+)\.png", f.name)
        if m and int(m.group(1)) > last_kept_turn_id:
            f.unlink(missing_ok=True)
            removed += 1
    return removed


# ---------------------------------------------------------------------------
# Identité univers → dossier de saves
# ---------------------------------------------------------------------------

def universe_key(universe_db: str | Path) -> str:
    """Stable key of a universe, used to file its saves.

    Folder universe: name of the source folder. Flat `.db`: file stem. Based
    on the **shape of the path** only (not on universe.toml existing): the key
    must stay identical even when the source is momentarily missing/broken,
    otherwise the saves become unreachable.
    """
    from axiom.compile import CACHE_DIRNAME

    p = Path(universe_db)
    if p.parent.name == CACHE_DIRNAME:
        return p.parent.parent.name
    return p.stem


def saves_dir_for(universe_db: str | Path) -> Path:
    """A universe's separate-saves folder (not created if missing)."""
    from axiom.paths import get_saves_dir

    return get_saves_dir() / universe_key(universe_db)


def is_separated_save_db(db_path: str | Path) -> bool:
    """True when `db_path` is a separate save (carries a Save_Meta table)."""
    db_path = Path(db_path)
    if not db_path.is_file():
        return False
    try:
        with closing(sqlite3.connect(str(db_path))) as conn:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='Save_Meta';"
            ).fetchone()
        return row is not None
    except sqlite3.Error:
        return False


# ---------------------------------------------------------------------------
# Création
# ---------------------------------------------------------------------------

def create_save(
    universe_db: str | Path,
    player_name: str,
    difficulty: str,
    player_persona: str = "",
) -> dict:
    """Create a new game in its own `saves/<universe>/save_<uuid>.db` database.

    The universe definition is copied into the save db (self-contained). The
    link to the universe (db + optional source) is recorded in `Save_Meta` for
    resynchronisation on open.

    Returns:
        A dict with keys save_id and db_path — db_path is the database to
        hand to `Session` (and to the engine helpers) to play this game.
    """
    # La ligne Saves elle-même (et les migrations runtime habituelles).
    from axiom.db_helpers import create_new_save as _create_row

    container = new_save_container(universe_db)
    actual_id = _create_row(str(container), player_name, difficulty, player_persona)
    final_db = finalize_save_container(container, actual_id)
    return {"save_id": actual_id, "db_path": str(final_db)}


def new_save_container(universe_db: str | Path) -> Path:
    """Prepare a blank save db (definition copied + Save_Meta, no Saves row).

    Common building block of `create_save` and of the imports (`save-import`,
    `save-unpack`): the caller then creates/imports its Saves row(s) and calls
    `finalize_save_container`.
    """
    universe_db = Path(universe_db)
    if not universe_db.is_file():
        raise SaveStoreError(f"Universe database not found: {universe_db}")

    out_dir = saves_dir_for(universe_db)
    out_dir.mkdir(parents=True, exist_ok=True)
    save_db = out_dir / f"save_tmp_{uuid.uuid4().hex}.db"

    _copy_definition(universe_db, save_db)

    src_root = universe_root_for(universe_db)
    meta = {
        "format": "1",
        "universe_key": universe_key(universe_db),
        "universe_db": str(universe_db),
        "universe_source": str(src_root) if src_root else "",
        "definition_hash": hash_directory(src_root) if src_root else "",
    }
    conn = sqlite3.connect(str(save_db))
    try:
        conn.execute(_DDL_SAVE_META)
        conn.executemany(
            "INSERT OR REPLACE INTO Save_Meta (key, value) VALUES (?, ?);",
            list(meta.items()),
        )
        conn.commit()
    finally:
        conn.close()
    return save_db


def finalize_save_container(container: Path, save_id: str) -> Path:
    """Rename a save container to its real save_id, definitively.

    Flushes the WAL into the main file BEFORE the rename (otherwise the
    -wal/-shm sidecars would stay attached to the old name and the last
    writes would be lost).
    """
    conn = sqlite3.connect(str(container))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    finally:
        conn.close()
    final_db = container.parent / f"save_{save_id}.db"
    replace_with_retry(container, final_db)
    for suffix in ("-wal", "-shm"):
        unlink_with_retry(Path(str(container) + suffix), missing_ok=True)
    return final_db


def _copy_definition(universe_db: Path, save_db: Path) -> None:
    """Copie les tables de définition de l'univers vers une save db neuve."""
    # Aligne l'univers sur le schéma courant avant la copie par colonnes.
    from axiom.schema import (
        migrate_entities_table,
        migrate_location_tables,
        migrate_lore_book_table,
        migrate_scheduled_events_table,
        migrate_stat_definitions_table,
    )

    migrate_lore_book_table(str(universe_db))
    migrate_stat_definitions_table(str(universe_db))
    migrate_entities_table(str(universe_db))
    migrate_scheduled_events_table(str(universe_db))
    migrate_location_tables(str(universe_db))

    if save_db.exists():
        raise SaveStoreError(f"Save db already exists: {save_db}")
    create_universe_db(str(save_db))

    conn = sqlite3.connect(str(save_db))
    try:
        conn.execute("ATTACH DATABASE ? AS universe;", (str(universe_db),))
        conn.execute("PRAGMA defer_foreign_keys=ON;")
        conn.execute("BEGIN;")
        for table, columns in _DEFINITION_COPY:
            cols = ", ".join(columns)
            conn.execute(
                f"INSERT INTO main.{table} ({cols}) SELECT {cols} FROM universe.{table};"
            )
        conn.commit()
        conn.execute("DETACH DATABASE universe;")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Listing / résolution (fusion séparées + legacy embarquées)
# ---------------------------------------------------------------------------

def list_saves(universe_db: str | Path) -> list[dict]:
    """List all the games of a universe, separate **and** embedded (legacy).

    Returns:
        List of dicts in the `db_helpers.load_saves` format, enriched with
        `db_path` (the database to open for this save) and `storage`
        ('separated' | 'embedded'), sorted by `last_updated`, most recent
        first.
    """
    from axiom.db_helpers import load_saves as _load_rows

    universe_db = Path(universe_db)
    out: list[dict] = []

    sep_dir = saves_dir_for(universe_db)
    if sep_dir.is_dir():
        for db_file in sorted(sep_dir.glob("*.db")):
            try:
                rows = _load_rows(str(db_file))
            except sqlite3.Error:
                continue  # fichier corrompu : ignoré, pas bloquant
            for row in rows:
                row["db_path"] = str(db_file)
                row["storage"] = "separated"
                out.append(row)

    if universe_db.is_file():
        for row in _load_rows(str(universe_db)):
            row["db_path"] = str(universe_db)
            row["storage"] = "embedded"
            out.append(row)

    out.sort(key=lambda r: r.get("last_updated") or "", reverse=True)
    return out


def resolve_save_db(universe_db: str | Path, save_id: str) -> str | None:
    """Return the database containing `save_id` (separate, or the universe itself)."""
    for row in list_saves(universe_db):
        if row.get("save_id") == save_id:
            return row["db_path"]
    return None


def prepare_save_for_play(universe_db: str | Path, save_id: str) -> str | None:
    """Resolve a save's database and resync its definition if the source changed.

    For a separate save linked to a folder universe: when the source hash
    differs from the recorded one, `refresh_definition` is applied **to the
    save db** (in-place: journal, runtime entities and game state intact) and
    the recorded hash is updated. A missing/broken source is not blocking:
    the save keeps its embedded definition (it is self-contained).

    Returns:
        The path of the database to hand to `Session`, or None for an unknown
        save.
    """
    db_path = resolve_save_db(universe_db, save_id)
    if db_path is None:
        return None
    refresh_save_definition(db_path)
    return db_path


def refresh_save_definition(save_db: str | Path) -> bool:
    """Resynchronise a separate save's definition from its universe source.

    No-op (False) for an embedded save, a save with no linked source, or one
    already up to date. A malformed source is ignored (the save stays
    playable as-is).
    """
    save_db = Path(save_db)
    if not is_separated_save_db(save_db):
        return False

    with closing(sqlite3.connect(str(save_db))) as conn:
        meta = dict(conn.execute("SELECT key, value FROM Save_Meta;").fetchall())
    src = meta.get("universe_source") or ""
    if not src or not (Path(src) / "universe.toml").exists():
        return False

    src_dir = Path(src)
    current = hash_directory(src_dir)
    if current == meta.get("definition_hash"):
        return False

    from axiom.compile import CompileError
    from axiom.dev import refresh_definition

    try:
        refresh_definition(src_dir, save_db)
    except CompileError:
        return False  # source momentanément cassée : on joue avec la définition embarquée

    with closing(sqlite3.connect(str(save_db))) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO Save_Meta (key, value) VALUES ('definition_hash', ?);",
            (current,),
        )
        conn.commit()
    return True


# ---------------------------------------------------------------------------
# Export / import d'une save (.axiomsave) — §7.6 « les deux exportables »
# ---------------------------------------------------------------------------

# Tables runtime copiées lors de l'extraction d'une save embarquée (legacy).
_RUNTIME_COPY: list[tuple[str, tuple[str, ...]]] = [
    ("Saves", ("save_id", "player_name", "difficulty", "last_updated", "player_persona")),
    ("Event_Log", ("event_id", "save_id", "turn_id", "event_type", "target_entity", "payload")),
    ("State_Cache", ("save_id", "entity_id", "stat_key", "stat_value")),
    ("Snapshots", ("save_id", "turn_id", "state_json")),
    ("Modifier_Snapshots", ("save_id", "turn_id", "state_json")),
    ("Timeline", ("event_id", "save_id", "turn_id", "in_game_time", "description")),
    ("Fired_Scheduled_Events", ("save_id", "event_id", "fired_turn_id")),
    ("Items_Inventory", ("save_id", "entity_id", "item_id", "quantity")),
    ("Active_Modifiers", ("modifier_id", "save_id", "entity_id", "stat_key", "delta", "minutes_remaining")),
    # Living-mode memory (Phase 2 facts, Phase 3 beliefs) travels with the save.
    # These tables are created lazily, so a save that never used living mode may
    # not have them in the source DB — the copy loop skips absent source tables.
    ("Facts", ("fact_id", "save_id", "turn_id", "fact_type", "who", "what",
               "fact_when", "fact_where", "why", "entities", "statement")),
    ("Observations", ("observation_id", "save_id", "subject", "statement",
                      "proof_count", "sources", "history", "created_turn_id",
                      "updated_turn_id", "stale")),
    ("Mental_Models", ("model_id", "save_id", "subject", "summary", "sources",
                       "created_turn_id", "updated_turn_id", "stale")),
]

_MANIFEST_NAME = "manifest.toml"
_ARCHIVE_DB_NAME = "save.db"
_ARCHIVE_ASSETS_PREFIX = "assets/"


def extract_save(universe_db: str | Path, save_id: str) -> Path:
    """Extract an **embedded** (legacy) save to its own separate file.

    Copies the universe's current definition + all this save's runtime rows.
    The original save stays intact in the universe `.db` (it is a copy, not a
    move).

    Returns:
        The path of the new `saves/<universe>/save_<id>.db` file.
    """
    universe_db = Path(universe_db)
    container = new_save_container(universe_db)
    conn = sqlite3.connect(str(container))
    try:
        conn.execute("ATTACH DATABASE ? AS universe;", (str(universe_db),))
        conn.execute("PRAGMA defer_foreign_keys=ON;")
        conn.execute("BEGIN;")
        # Lazily-created tables (Facts/Observations) may be absent from an older
        # source DB — copy only what the source actually has.
        source_tables = {
            r[0] for r in conn.execute(
                "SELECT name FROM universe.sqlite_master WHERE type = 'table';"
            ).fetchall()
        }
        for table, columns in _RUNTIME_COPY:
            if table not in source_tables:
                continue
            cols = ", ".join(columns)
            conn.execute(
                f"INSERT INTO main.{table} ({cols}) "
                f"SELECT {cols} FROM universe.{table} WHERE save_id = ?;",
                (save_id,),
            )
        copied = conn.execute(
            "SELECT COUNT(*) FROM main.Saves WHERE save_id = ?;", (save_id,)
        ).fetchone()[0]
        if not copied:
            conn.rollback()
            raise SaveStoreError(f"Save not found in universe: {save_id}")
        conn.commit()
        conn.execute("DETACH DATABASE universe;")
    finally:
        conn.close()
    return finalize_save_container(container, save_id)


def pack_save(universe_db: str | Path, save_id: str, output_path: str | Path) -> Path:
    """Export a save to a `.axiomsave` archive (zip: self-contained save.db + manifest).

    A separate save is zipped as-is; an embedded (legacy) save is first
    extracted to a self-contained file (a copy — the original stays). The
    vector memory does not travel (empty on import).
    """
    import tempfile
    import zipfile

    universe_db = Path(universe_db)
    db_path = resolve_save_db(universe_db, save_id)
    if db_path is None:
        raise SaveStoreError(f"Save not found: {save_id}")

    cleanup: Path | None = None
    if not is_separated_save_db(db_path):
        cleanup = extract_save(universe_db, save_id)
        db_path = str(cleanup)

    # Fige le WAL pour zipper un fichier principal complet.
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    finally:
        conn.close()

    def _toml_str(value: str) -> str:
        # Chaîne TOML basique échappée (un nom d'univers peut porter " ou \).
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'

    manifest = (
        f'format = "axiomsave-1"\n'
        f"save_id = {_toml_str(save_id)}\n"
        f"universe_key = {_toml_str(universe_key(universe_db))}\n"
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(output_path), "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(db_path, _ARCHIVE_DB_NAME)
        zf.writestr(_MANIFEST_NAME, manifest)
        # Illustrations de tour (TICKET-048). Entrées supplémentaires ignorées
        # par les anciens lecteurs : le format reste compatible dans les deux sens.
        assets = assets_dir_for_save(save_id)
        if assets.is_dir():
            for f in sorted(assets.glob("turn_*.png")):
                zf.write(f, f"{_ARCHIVE_ASSETS_PREFIX}{f.name}")

    if cleanup is not None:
        # L'extraction n'était qu'un intermédiaire d'export : on ne laisse pas
        # une copie séparée concurrente de la save embarquée d'origine.
        _remove_db_files(cleanup)
    return output_path


def unpack_save(
    archive_path: str | Path,
    universe_db: str | Path,
    force: bool = False,
) -> dict:
    """Import a `.axiomsave` archive into a universe's save store.

    By default, refuses an archive coming from another universe (different
    `universe_key`) — pass `force=True` to override. When the `save_id`
    already exists here, the imported save is **re-identified** (new uuid) so
    an existing game is never overwritten.

    Returns:
        A dict with keys save_id and db_path.
    """
    import tomllib
    import zipfile

    archive_path = Path(archive_path)
    universe_db = Path(universe_db)
    try:
        with zipfile.ZipFile(str(archive_path), "r") as zf:
            names = set(zf.namelist())
            if _ARCHIVE_DB_NAME not in names or _MANIFEST_NAME not in names:
                raise SaveStoreError("Invalid .axiomsave archive (missing save.db/manifest).")
            manifest = tomllib.loads(zf.read(_MANIFEST_NAME).decode("utf-8"))
            db_bytes = zf.read(_ARCHIVE_DB_NAME)
            # Illustrations embarquées (TICKET-048) ; absentes des archives
            # antérieures, et seuls les noms `turn_<n>.png` plats sont acceptés.
            asset_bytes: dict[str, bytes] = {
                Path(n).name: zf.read(n)
                for n in names
                if n.startswith(_ARCHIVE_ASSETS_PREFIX)
                and "/" not in n[len(_ARCHIVE_ASSETS_PREFIX):]
                and Path(n).name.startswith("turn_")
                and n.endswith(".png")
            }
    except (zipfile.BadZipFile, OSError, tomllib.TOMLDecodeError) as exc:
        raise SaveStoreError(f"Unreadable .axiomsave archive: {exc}") from exc

    src_key = str(manifest.get("universe_key", ""))
    dst_key = universe_key(universe_db)
    if src_key and src_key != dst_key and not force:
        raise SaveStoreError(
            f"This save comes from universe '{src_key}', not '{dst_key}'. "
            "Use force to import anyway."
        )

    save_id = str(manifest.get("save_id", ""))
    out_dir = saves_dir_for(universe_db)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / f"save_tmp_{uuid.uuid4().hex}.db"
    tmp.write_bytes(db_bytes)

    existing_ids = {r["save_id"] for r in list_saves(universe_db)}
    if not save_id or save_id in existing_ids:
        new_id = str(uuid.uuid4())
        _reassign_save_id(tmp, save_id, new_id)
        save_id = new_id

    # Re-lie la save à l'univers de DESTINATION : l'archive porte les chemins
    # de la machine/univers de l'exportateur — sans cette réécriture, la save
    # importée ne se resynchroniserait jamais avec la source locale (§7.6) et
    # la canonisation la croirait orpheline (TICKET-036).
    src_root = universe_root_for(universe_db)
    meta = {
        "universe_key": dst_key,
        "universe_db": str(universe_db),
        "universe_source": str(src_root) if src_root else "",
        # Hash volontairement vide : la définition embarquée vient d'un autre
        # export — le premier prepare_save_for_play resynchronisera depuis la
        # source locale si elle existe.
        "definition_hash": "",
    }
    conn = sqlite3.connect(str(tmp))
    try:
        conn.execute(_DDL_SAVE_META)
        conn.executemany(
            "INSERT OR REPLACE INTO Save_Meta (key, value) VALUES (?, ?);",
            list(meta.items()),
        )
        conn.commit()
    finally:
        conn.close()

    final_db = finalize_save_container(tmp, save_id)

    if asset_bytes:
        assets_dir = assets_dir_for_save(save_id)
        assets_dir.mkdir(parents=True, exist_ok=True)
        for name, data in asset_bytes.items():
            (assets_dir / name).write_bytes(data)

    return {"save_id": save_id, "db_path": str(final_db)}


def _reassign_save_id(db: Path, old_id: str, new_id: str) -> None:
    """Change le save_id dans toutes les tables runtime d'une save db."""
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("PRAGMA defer_foreign_keys=ON;")
        conn.execute("BEGIN;")
        for table, _cols in _RUNTIME_COPY:
            if old_id:
                conn.execute(
                    f"UPDATE {table} SET save_id = ? WHERE save_id = ?;",
                    (new_id, old_id),
                )
            else:
                conn.execute(f"UPDATE {table} SET save_id = ?;", (new_id,))
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Duplication (« save manuelle » : point de branche au présent)
# ---------------------------------------------------------------------------

def duplicate_save(
    universe_db: str | Path,
    save_id: str,
    player_name: str | None = None,
) -> dict:
    """Duplicate a game as-is (full journal preserved).

    Separate save: re-identified file copy (new uuid) — the "one save = one
    file" model is preserved, unlike a `fork_save` within the same file.
    Embedded (legacy) save: fork at the last turn in the same database, as
    before.

    Returns:
        A dict with keys save_id and db_path.
    """
    import shutil
    from datetime import datetime

    db_path = resolve_save_db(universe_db, save_id)
    if db_path is None:
        raise SaveStoreError(f"Save not found: {save_id}")

    if not is_separated_save_db(db_path):
        from axiom.saves import fork_save

        new_id = fork_save(db_path, save_id, player_name=player_name)
        copy_save_assets(save_id, new_id)
        return {"save_id": new_id, "db_path": db_path}

    # Fige le WAL pour copier un fichier principal complet.
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    finally:
        conn.close()

    out_dir = saves_dir_for(universe_db)
    tmp = out_dir / f"save_tmp_{uuid.uuid4().hex}.db"
    shutil.copyfile(db_path, tmp)

    new_id = str(uuid.uuid4())
    _reassign_save_id(tmp, save_id, new_id)
    conn = sqlite3.connect(str(tmp))
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
        # Si le fichier portait d'autres saves (forks CLI dans le même fichier),
        # la copie ne garde que la partie dupliquée.
        conn.execute("DELETE FROM Saves WHERE save_id != ?;", (new_id,))
        conn.execute(
            "UPDATE Saves SET player_name = COALESCE(?, player_name), last_updated = ? "
            "WHERE save_id = ?;",
            (player_name, datetime.now().isoformat(), new_id),
        )
        conn.commit()
    finally:
        conn.close()
    final_db = finalize_save_container(tmp, new_id)
    copy_save_assets(save_id, new_id)
    return {"save_id": new_id, "db_path": str(final_db)}


# ---------------------------------------------------------------------------
# Suppression
# ---------------------------------------------------------------------------

def delete_save(universe_db: str | Path, save_id: str) -> bool:
    """Delete a game. A separate save whose database becomes empty is removed from disk.

    Returns:
        True when a save was deleted.
    """
    db_path = resolve_save_db(universe_db, save_id)
    if db_path is None:
        return False
    with closing(sqlite3.connect(db_path)) as conn:
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("DELETE FROM Saves WHERE save_id = ?;", (save_id,))
        conn.commit()
        remaining = conn.execute("SELECT COUNT(*) FROM Saves;").fetchone()[0]
    if remaining == 0 and is_separated_save_db(db_path):
        _remove_db_files(Path(db_path))
    delete_save_assets(save_id)
    return True


def delete_universe_saves(universe_db: str | Path) -> None:
    """Delete a universe's separate-saves folder (along with the universe),
    illustrations included.
    """
    import shutil

    for row in list_saves(universe_db):
        sid = row.get("save_id")
        if sid:
            delete_save_assets(sid)
    sep_dir = saves_dir_for(universe_db)
    if sep_dir.is_dir():
        shutil.rmtree(sep_dir)


def _remove_db_files(db: Path) -> None:
    for suffix in ("", "-wal", "-shm"):
        unlink_with_retry(Path(str(db) + suffix), missing_ok=True)
