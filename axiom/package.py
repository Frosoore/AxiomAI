"""axiom.package — Universe-as-Code: `.axiom` v2 packaging + v1 compat.

A `.axiom` v2 archive is a **zip of the source tree** (TOML/MD) including the
compiled cache `.axiom-cache/universe.db` for instant loading.

Backward compatibility: old `.axiom` v1 archives (zip of JSON files) are
detected and converted on the fly (v1 -> .db -> decompile -> v2 tree ->
recompile).

Zero Qt dependency: pure engine. The Qt worker `import_export_worker.py` is a
thin shell calling these functions.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from axiom.compile import (
    CACHE_DB_NAME,
    CACHE_DIRNAME,
    CACHE_HASH_NAME,
    compile_universe,
    hash_directory,
)
from axiom.decompile import decompile_universe
from axiom.schema import create_universe_db

# Fichiers marqueurs des deux formats.
_V2_MARKER = "universe.toml"
_V1_MARKERS = ("universe_meta.json", "format_version.json")


class PackageError(Exception):
    """Error while packing/unpacking a `.axiom` archive."""


# ---------------------------------------------------------------------------
# Pack (arbo source → .axiom v2)
# ---------------------------------------------------------------------------

def pack_universe(src_dir: str | Path, output_path: str | Path) -> Path:
    """Pack a source tree into a `.axiom` v2 archive.

    Recompiles the cache (`.axiom-cache/universe.db`) first so it ships in the
    archive, then zips the tree. An archive only publishes the **definition**
    (same contract as exporting a flat `.db`, TICKET-039):

    - `.git/` and the WAL sidecars (`-wal`/`-shm`) are excluded;
    - the embedded cache is a copy **purged of the runtime tables** (legacy
      embedded saves — private play history — do not travel).

    Args:
        src_dir:     Universe source folder (contains universe.toml).
        output_path: Path of the `.axiom` archive to produce.

    Returns:
        The path of the created archive.
    """
    src_dir = Path(src_dir)
    if not (src_dir / _V2_MARKER).exists():
        raise PackageError(f"Invalid source tree (no universe.toml): {src_dir}")

    compile_universe(src_dir)  # garantit un cache à jour à embarquer
    cache_rel = f"{CACHE_DIRNAME}/{CACHE_DB_NAME}"

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    # ignore_cleanup_errors : sous Windows, un -shm SQLite encore mappé peut
    # faire échouer le rmtree final du dossier temporaire (WinError 32).
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        clean_db = _runtime_free_cache_copy(src_dir / cache_rel, Path(tmp_dir))
        with zipfile.ZipFile(str(output_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(src_dir.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(src_dir).as_posix()
                if rel.split("/", 1)[0] == ".git":
                    continue
                if rel.endswith(("-wal", "-shm")):
                    continue
                if rel == cache_rel:
                    zf.write(clean_db, rel)
                    continue
                zf.write(path, rel)
    return output_path


# Tables runtime purgées du cache embarqué dans une archive (l'ordre respecte
# les FK : enfants d'abord, Saves en dernier).
_RUNTIME_TABLES = (
    "Fired_Scheduled_Events",
    "Active_Modifiers",
    "Items_Inventory",
    "Timeline",
    "Snapshots",
    "State_Cache",
    "Event_Log",
    "Saves",
)


def _runtime_free_cache_copy(cache_db: Path, tmp_dir: Path) -> Path:
    """Copie du cache compilé sans aucune donnée runtime (définition seule).

    Les sidecars WAL sont copiés avec la base puis fusionnés (checkpoint) :
    sans eux, les dernières écritures non checkpointées seraient perdues.
    """
    import shutil
    from contextlib import closing

    clean = tmp_dir / CACHE_DB_NAME
    shutil.copyfile(cache_db, clean)
    wal = Path(str(cache_db) + "-wal")
    if wal.exists():
        shutil.copyfile(wal, Path(str(clean) + "-wal"))  # le -shm se reconstruit seul

    with closing(sqlite3.connect(str(clean))) as conn:
        conn.execute("PRAGMA foreign_keys=OFF;")
        for table in _RUNTIME_TABLES:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?;", (table,)
            ).fetchone()
            if row:
                conn.execute(f"DELETE FROM {table};")
        conn.commit()
        conn.execute("VACUUM;")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    return clean


def export_db_to_axiom(db_path: str | Path, output_path: str | Path) -> Path:
    """Export a `.db` universe to a `.axiom` v2 archive (decompile -> pack).

    For universes that still only exist as a `.db` (legacy GUI). The archive
    only contains the **definition** (the decompiled tree + its recompiled
    cache): saves embedded in the `.db` are not exported — same contract as the
    v1 export.

    Args:
        db_path:     Path of the universe `.db` to export.
        output_path: Path of the `.axiom` archive to produce.

    Returns:
        The path of the created archive.
    """
    db_path = Path(db_path)
    if not db_path.is_file():
        raise PackageError(f"Universe database not found: {db_path}")

    from axiom.decompile import DecompileError, decompile_universe

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        src = Path(tmp_dir) / db_path.stem
        try:
            decompile_universe(db_path, src)
        except DecompileError as exc:
            raise PackageError(f"Decompilation failed: {exc}") from exc
        return pack_universe(src, output_path)


# ---------------------------------------------------------------------------
# Unpack (.axiom → arbo source + cache, prêt à jouer)
# ---------------------------------------------------------------------------

def detect_format(axiom_path: str | Path) -> str:
    """Return 'v2' or 'v1', or raise PackageError, depending on the archive content."""
    try:
        with zipfile.ZipFile(str(axiom_path), "r") as zf:
            names = set(zf.namelist())
    except (zipfile.BadZipFile, OSError) as exc:
        raise PackageError(f"Unreadable .axiom archive: {exc}") from exc
    if _V2_MARKER in names:
        return "v2"
    if any(m in names for m in _V1_MARKERS):
        return "v1"
    raise PackageError("Unrecognized .axiom format (neither v2 nor v1).")


def unpack_universe(axiom_path: str | Path, dest_root: str | Path) -> Path:
    """Unpack a `.axiom` (v1 or v2) into a playable source tree.

    v2: unzip, check the hash — keep the embedded `.db` if valid, recompile
    otherwise. v1: convert (JSON -> .db -> decompile -> v2 tree -> compile).

    Args:
        axiom_path: Path of the `.axiom` archive.
        dest_root:  Root folder where the universe is materialised (in a
                    <name>/ subfolder).

    Returns:
        The path of the universe source folder (containing universe.toml +
        cache).
    """
    axiom_path = Path(axiom_path)
    dest_root = Path(dest_root)
    fmt = detect_format(axiom_path)
    # Le dossier prend le NOM DE L'UNIVERS (lu dans l'archive), pas le nom du
    # fichier .axiom — sinon un export laissé en « universe.axiom » s'installe
    # sous « universe/ ».
    base = _archive_universe_name(axiom_path, fmt) or axiom_path.stem
    name = _unique_name(dest_root, base)

    if fmt == "v2":
        return _unpack_v2(axiom_path, dest_root, name)
    return _import_v1(axiom_path, dest_root, name)


def _archive_universe_name(axiom_path: Path, fmt: str) -> str | None:
    """Lit le nom d'univers déclaré dans l'archive (v2 : universe.toml [meta].name ;
    v1 : universe_meta.json universe_name). None si absent/illisible."""
    import tomllib

    try:
        with zipfile.ZipFile(str(axiom_path), "r") as zf:
            if fmt == "v2":
                data = tomllib.loads(zf.read(_V2_MARKER).decode("utf-8"))
                raw = data.get("meta", {}).get("name", "")
            else:
                meta = json.loads(zf.read("universe_meta.json").decode("utf-8"))
                raw = meta.get("universe_name", "")
    except (KeyError, OSError, zipfile.BadZipFile, json.JSONDecodeError,
            tomllib.TOMLDecodeError, UnicodeDecodeError):
        return None
    safe = "".join(c if c.isalnum() or c in "_ -" else "_" for c in str(raw)).strip()
    safe = safe.replace(" ", "_")
    return safe or None


def _unique_name(dest_root: Path, stem: str) -> str:
    """Nom de dossier libre sous `dest_root` (suffixe _1, _2, … si conflit).

    Ré-importer une archive ne doit jamais écraser un univers installé : son
    cache `.db` peut contenir des parties en cours (§7.6 différé).
    """
    name = stem
    counter = 1
    while (dest_root / name).exists():
        name = f"{stem}_{counter}"
        counter += 1
    return name


def _unpack_v2(axiom_path: Path, dest_root: Path, name: str) -> Path:
    dest = dest_root / name
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(axiom_path), "r") as zf:
        zf.extractall(dest)

    cache_db = dest / CACHE_DIRNAME / CACHE_DB_NAME
    cache_hash = dest / CACHE_DIRNAME / CACHE_HASH_NAME
    cache_valid = (
        cache_db.exists()
        and cache_hash.exists()
        and cache_hash.read_text(encoding="utf-8").strip() == hash_directory(dest)
    )
    if not cache_valid:
        compile_universe(dest, force=True)
    return dest


def _import_v1(axiom_path: Path, dest_root: Path, name: str) -> Path:
    """Convertit un `.axiom` v1 (JSON) en arborescence v2."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        tmp = Path(tmp_dir)
        with zipfile.ZipFile(str(axiom_path), "r") as zf:
            zf.extractall(tmp)

        try:
            meta = json.loads((tmp / "universe_meta.json").read_text(encoding="utf-8"))
            entities = json.loads((tmp / "entities.json").read_text(encoding="utf-8"))
            rules = (
                json.loads((tmp / "rules.json").read_text(encoding="utf-8"))
                if (tmp / "rules.json").exists() else []
            )
            lore = (
                json.loads((tmp / "lore_book.json").read_text(encoding="utf-8"))
                if (tmp / "lore_book.json").exists() else []
            )
        except (json.JSONDecodeError, OSError, KeyError) as exc:
            raise PackageError(f"Corrupt .axiom v1: {exc}") from exc

        v1_db = tmp / "_v1.db"
        create_universe_db(str(v1_db))
        _populate_v1(v1_db, meta, entities, rules, lore)

        dest = dest_root / name
        decompile_universe(v1_db, dest)
        compile_universe(dest, force=True)
        return dest


def _populate_v1(db_path: Path, meta: dict, entities: list, rules: list, lore: list) -> None:
    """Peuple un `.db` à partir des structures JSON v1 (Universe_Meta/Entities/Rules/Lore)."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.executemany(
            "INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES (?, ?);",
            [(str(k), str(v)) for k, v in meta.items()],
        )
        for ent in entities:
            conn.execute(
                "INSERT OR REPLACE INTO Entities "
                "(entity_id, entity_type, name, description, is_active) VALUES (?, ?, ?, ?, 1);",
                (
                    ent["entity_id"],
                    ent.get("entity_type", "npc"),
                    ent.get("name", ent["entity_id"]),
                    ent.get("description", ""),
                ),
            )
            conn.executemany(
                "INSERT OR REPLACE INTO Entity_Stats (entity_id, stat_key, stat_value) "
                "VALUES (?, ?, ?);",
                [(ent["entity_id"], str(k), str(v)) for k, v in ent.get("stats", {}).items()],
            )
        conn.executemany(
            "INSERT OR REPLACE INTO Rules "
            "(rule_id, priority, conditions, actions, target_entity) VALUES (?, ?, ?, ?, ?);",
            [
                (
                    r["rule_id"],
                    int(r.get("priority", 0)),
                    json.dumps(r.get("conditions", {})),
                    json.dumps(r.get("actions", [])),
                    r.get("target_entity", "*"),
                )
                for r in rules
            ],
        )
        conn.executemany(
            "INSERT OR REPLACE INTO Lore_Book "
            "(entry_id, category, name, keywords, content) VALUES (?, ?, ?, ?, ?);",
            [
                (
                    e["entry_id"],
                    e.get("category", ""),
                    e.get("name", ""),
                    e.get("keywords", ""),
                    e.get("content", ""),
                )
                for e in lore
            ],
        )
        conn.commit()
    finally:
        conn.close()
