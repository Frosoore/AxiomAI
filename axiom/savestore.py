"""axiom.savestore — Universe-as-Code §7.6 : saves séparées de l'univers.

L'arborescence (et son cache compilé) est la **définition** de l'univers ; les
parties vivent dans des bases dédiées :

    ~/AxiomAI/
    ├── universes/<nom>/…                  ← définition (source + cache)
    └── saves/<clé univers>/save_<uuid>.db ← une partie (état runtime)

Modèle retenu : chaque save db est **autonome** — schéma complet, avec une
**copie des tables de définition** prise à la création. Avantages :
- `Session` et tout le moteur fonctionnent inchangés (un seul chemin de DB) ;
- patcher l'univers ne brique pas les parties (elles gardent leur définition,
  resynchronisée à l'ouverture via `refresh_definition` — in-place, les
  entités runtime et l'état de jeu survivent) ;
- une save = un fichier portable (export/import trivial).

Compat ascendante : les saves historiques embarquées dans le `.db` univers
restent listées et jouables telles quelles (`storage='embedded'`). Seules les
**nouvelles** saves sont créées en fichiers séparés.

Zéro dépendance Qt : pur moteur.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import closing
from pathlib import Path

from axiom.compile import hash_directory
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
    """Erreur du magasin de sauvegardes séparées."""


# ---------------------------------------------------------------------------
# Images générées (illustrations de tour) — TICKET-048
#
# Les illustrations vivent hors save db, sous `<data_root>/assets/<save_id>/
# turn_<n>.png`. Elles suivent la save : copiées à la duplication, purgées à
# la suppression, embarquées dans `.axiomsave`, tronquées au rewind. Décision
# assumée : seul le chemin `Session` en génère (pas la file multijoueur).
# ---------------------------------------------------------------------------

def assets_dir_for_save(save_id: str) -> Path:
    """Dossier des illustrations d'une save (non créé s'il n'existe pas)."""
    from axiom.paths import get_assets_dir

    return get_assets_dir() / save_id


def copy_save_assets(src_save_id: str, dst_save_id: str) -> int:
    """Copie les illustrations d'une save vers une autre. Retourne le nombre copié."""
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
    """Supprime le dossier d'illustrations d'une save (no-op s'il n'existe pas)."""
    import shutil

    d = assets_dir_for_save(save_id)
    if d.is_dir():
        shutil.rmtree(d, ignore_errors=True)


def truncate_save_assets(save_id: str, last_kept_turn_id: int) -> int:
    """Purge les `turn_<n>.png` avec n > `last_kept_turn_id` (rewind).

    Retourne le nombre de fichiers supprimés. Les noms non conformes sont ignorés.
    """
    return truncate_assets_in(assets_dir_for_save(save_id), last_kept_turn_id)


def truncate_assets_in(assets_dir: Path, last_kept_turn_id: int) -> int:
    """Variante de `truncate_save_assets` sur un dossier explicite (Session
    avec data_dir injecté)."""
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
    """Clé stable d'un univers pour le rangement des saves.

    Univers-dossier : nom du dossier source. `.db` plat : stem du fichier.
    Basée sur la **forme du chemin** uniquement (pas sur l'existence de
    universe.toml) : la clé doit rester identique même si la source est
    momentanément absente/cassée, sinon les saves deviennent introuvables.
    """
    from axiom.compile import CACHE_DIRNAME

    p = Path(universe_db)
    if p.parent.name == CACHE_DIRNAME:
        return p.parent.parent.name
    return p.stem


def saves_dir_for(universe_db: str | Path) -> Path:
    """Dossier des saves séparées d'un univers (non créé s'il n'existe pas)."""
    from axiom.paths import get_saves_dir

    return get_saves_dir() / universe_key(universe_db)


def is_separated_save_db(db_path: str | Path) -> bool:
    """True si `db_path` est une save séparée (porte une table Save_Meta)."""
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
    """Crée une nouvelle partie dans sa propre base `saves/<univers>/save_<uuid>.db`.

    La définition de l'univers est copiée dans la save db (autonome). Le lien
    vers l'univers (db + source éventuelle) est consigné dans `Save_Meta` pour
    la resynchronisation à l'ouverture.

    Returns:
        {"save_id": str, "db_path": str} — `db_path` est la base à passer à
        `Session` (et aux helpers moteur) pour jouer cette partie.
    """
    # La ligne Saves elle-même (et les migrations runtime habituelles).
    from axiom.db_helpers import create_new_save as _create_row

    container = new_save_container(universe_db)
    actual_id = _create_row(str(container), player_name, difficulty, player_persona)
    final_db = finalize_save_container(container, actual_id)
    return {"save_id": actual_id, "db_path": str(final_db)}


def new_save_container(universe_db: str | Path) -> Path:
    """Prépare une save db vierge (définition copiée + Save_Meta, aucune ligne Saves).

    Brique commune de `create_save` et de l'import (`save-import`,
    `save-unpack`) : l'appelant y crée/importe ensuite sa ou ses lignes Saves,
    puis appelle `finalize_save_container`.
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
    """Nomme définitivement un conteneur de save sur son save_id réel.

    Vide le WAL dans le fichier principal AVANT le rename (sinon les sidecars
    -wal/-shm resteraient attachés à l'ancien nom et les dernières écritures
    seraient perdues).
    """
    conn = sqlite3.connect(str(container))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    finally:
        conn.close()
    final_db = container.parent / f"save_{save_id}.db"
    container.replace(final_db)
    for suffix in ("-wal", "-shm"):
        leftover = Path(str(container) + suffix)
        if leftover.exists():
            leftover.unlink()
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
    """Liste toutes les parties d'un univers, séparées **et** embarquées (legacy).

    Returns:
        Liste de dicts au format de `db_helpers.load_saves`, enrichis de
        `db_path` (la base à ouvrir pour cette save) et `storage`
        ('separated' | 'embedded'), triée par `last_updated` décroissant.
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
    """Retourne la base contenant `save_id` (séparée ou l'univers lui-même)."""
    for row in list_saves(universe_db):
        if row.get("save_id") == save_id:
            return row["db_path"]
    return None


def prepare_save_for_play(universe_db: str | Path, save_id: str) -> str | None:
    """Résout la base d'une save et resynchronise sa définition si la source a changé.

    Pour une save séparée liée à un univers-dossier : si le hash de la source
    diffère de celui consigné, `refresh_definition` est appliqué **à la save db**
    (in-place : journal, entités runtime et état de jeu intacts) puis le hash
    consigné est mis à jour. Une source disparue/cassée n'est pas bloquante :
    la save garde sa définition embarquée (elle est autonome).

    Returns:
        Le chemin de la base à passer à `Session`, ou None si save inconnue.
    """
    db_path = resolve_save_db(universe_db, save_id)
    if db_path is None:
        return None
    refresh_save_definition(db_path)
    return db_path


def refresh_save_definition(save_db: str | Path) -> bool:
    """Resynchronise la définition d'une save séparée depuis sa source univers.

    No-op (False) pour une save embarquée, sans source liée, ou déjà à jour.
    Une source malformée est ignorée (la save reste jouable telle quelle).
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
    ("Timeline", ("event_id", "save_id", "turn_id", "in_game_time", "description")),
    ("Fired_Scheduled_Events", ("save_id", "event_id")),
    ("Items_Inventory", ("save_id", "entity_id", "item_id", "quantity")),
    ("Active_Modifiers", ("modifier_id", "save_id", "entity_id", "stat_key", "delta", "minutes_remaining")),
]

_MANIFEST_NAME = "manifest.toml"
_ARCHIVE_DB_NAME = "save.db"
_ARCHIVE_ASSETS_PREFIX = "assets/"


def extract_save(universe_db: str | Path, save_id: str) -> Path:
    """Extrait une save **embarquée** (legacy) vers son propre fichier séparé.

    Copie la définition courante de l'univers + toutes les lignes runtime de
    cette save. La save d'origine reste intacte dans le `.db` univers (c'est
    une copie, pas un déplacement).

    Returns:
        Le chemin du nouveau fichier `saves/<univers>/save_<id>.db`.
    """
    universe_db = Path(universe_db)
    container = new_save_container(universe_db)
    conn = sqlite3.connect(str(container))
    try:
        conn.execute("ATTACH DATABASE ? AS universe;", (str(universe_db),))
        conn.execute("PRAGMA defer_foreign_keys=ON;")
        conn.execute("BEGIN;")
        for table, columns in _RUNTIME_COPY:
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
    """Exporte une save en archive `.axiomsave` (zip : save.db autonome + manifest).

    Une save séparée est zippée telle quelle ; une save embarquée (legacy) est
    d'abord extraite vers un fichier autonome (copie, l'original reste).
    La mémoire vectorielle ne voyage pas (décision D3 : vide à l'import).
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
    """Importe une archive `.axiomsave` dans le magasin de saves d'un univers.

    Par défaut, refuse une archive issue d'un autre univers (`universe_key`
    différente) — `force=True` pour passer outre. Si le `save_id` existe déjà
    ici, la save importée est **ré-identifiée** (nouvel uuid) pour ne jamais
    écraser une partie.

    Returns:
        {"save_id": str, "db_path": str}
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
    """Duplique une partie telle quelle (journal complet préservé).

    Save séparée : copie du fichier ré-identifiée (nouvel uuid) — le modèle
    « une save = un fichier » est conservé, contrairement à un `fork_save`
    dans le même fichier. Save embarquée (legacy) : fork au dernier tour dans
    la même base, comme avant.

    Returns:
        {"save_id": str, "db_path": str}
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
    """Supprime une partie. Une save séparée dont la base se vide est effacée du disque.

    Returns:
        True si une save a été supprimée.
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
    """Supprime le dossier de saves séparées d'un univers (avec l'univers),
    illustrations comprises."""
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
        p = Path(str(db) + suffix)
        if p.exists():
            p.unlink()
