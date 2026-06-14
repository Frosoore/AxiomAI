"""axiom.library — Universe-as-Code: discovery of installed universes.

The Hub historically listed flat `*.db` files in `~/AxiomAI/universes/`. With
Universe-as-Code, an imported universe (`.axiom` v2) or one created in source
mode lives in a **folder** `universes/<name>/` (universe.toml +
`.axiom-cache/universe.db`). This module provides the unified discovery of
both forms, engine-side (zero Qt) — the Hub's `DbWorker` is just a shell on
top.
"""

from __future__ import annotations

from contextlib import closing
from pathlib import Path

from axiom.compile import CACHE_DIRNAME, CompileError
from axiom.db_helpers import read_universe_card_metadata
from axiom.dev import ensure_compiled
from axiom.fsutil import replace_with_retry, unlink_with_retry
from axiom.logger import logger

_SOURCE_MARKER = "universe.toml"


class LibraryError(Exception):
    """Universe library management error."""


def universe_root_for(db_path: str | Path) -> Path | None:
    """Return a universe's source folder when `db_path` is its compiled cache.

    `universes/<name>/.axiom-cache/universe.db` maps to `universes/<name>/`.
    Returns None for a flat `.db` (legacy) or any other path.
    """
    db_path = Path(db_path)
    if db_path.parent.name != CACHE_DIRNAME:
        return None
    root = db_path.parent.parent
    return root if (root / _SOURCE_MARKER).exists() else None


def discover_universes(library_dir: str | Path) -> list[dict]:
    """List the playable universes of a library folder.

    Two forms are recognised:

    - flat `*.db` (legacy);
    - a subfolder containing `universe.toml` (Universe-as-Code), compiled on
      demand when the cache is missing/stale (no-op when the hash is
      unchanged).

    A malformed source folder is skipped (warning logged): it must not prevent
    the Hub from showing the rest of the library.

    Returns:
        List of dicts {db_path, source_dir, name, last_updated, difficulty},
        sorted by file/folder name. `source_dir` is None for a flat `.db`.
    """
    library_dir = Path(library_dir)
    entries: list[dict] = []
    if not library_dir.is_dir():
        return entries

    for db_file in sorted(library_dir.glob("*.db")):
        entries.append(_entry(db_file, source_dir=None))

    for sub in sorted(p for p in library_dir.iterdir() if p.is_dir()):
        if not (sub / _SOURCE_MARKER).exists():
            continue
        try:
            # ensure_compiled (pas compile_universe) : un refresh in-place
            # préserve les saves embarquées dans le cache (§7.6 différé).
            db_path = ensure_compiled(sub)
        except CompileError as exc:
            logger.warning("Univers source ignoré (%s) : %s", sub.name, exc)
            continue
        entries.append(_entry(db_path, source_dir=sub))

    return entries


# ---------------------------------------------------------------------------
# Prévisualisation / application d'un changement de source (TICKET-030)
# ---------------------------------------------------------------------------

def diff_source_trees(before_dir: str | Path, after_dir: str | Path) -> list[dict]:
    """Text diff between two source trees (protected areas excluded).

    Used for previews: `before_dir` is the real source, `after_dir` a temporary
    tree reflecting what the source would become.

    Returns:
        A list of dicts with keys path, status ('added' | 'modified' |
        'removed') and diff — a unified diff, sorted by path.
    """
    import difflib

    before_dir = Path(before_dir)
    after_dir = Path(after_dir)

    def _files(root: Path) -> dict[str, Path]:
        # as_posix() : clés de diff canoniques (slashes), identiques sous Windows
        # et Linux — sinon le rapport afficherait `entities\bob.toml` et tout
        # appariement par chemin côté UI casserait.
        return {
            p.relative_to(root).as_posix(): p
            for p in root.rglob("*")
            if p.is_file() and p.relative_to(root).parts[0] not in _PROTECTED_TOP_LEVEL
        }

    before = _files(before_dir)
    after = _files(after_dir)
    out: list[dict] = []
    for rel in sorted(before.keys() | after.keys()):
        old_text = before[rel].read_text(encoding="utf-8") if rel in before else ""
        new_text = after[rel].read_text(encoding="utf-8") if rel in after else ""
        if old_text == new_text:
            continue
        status = "modified" if rel in before and rel in after else (
            "added" if rel in after else "removed"
        )
        diff = "".join(difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{rel}", tofile=f"b/{rel}",
        ))
        out.append({"path": rel, "status": status, "diff": diff})
    return out


def apply_staged_source(staged_dir: str | Path, src_dir: str | Path,
                        db_path: str | Path) -> Path:
    """Apply a validated source tree: mirror it to the source + recompile.

    `staged_dir` is a full snapshot of the future source (produced by the
    preview sandbox): it replaces the source — protected areas
    (`.axiom-cache/`, `.git/`) untouched — then the definition is recompiled
    **in-place** into `db_path` (runtime intact).
    """
    from axiom.dev import refresh_definition

    _mirror_tree(Path(staged_dir), Path(src_dir))
    return refresh_definition(src_dir, db_path)


# ---------------------------------------------------------------------------
# Conversion .db plat → univers-dossier (TICKET-029)
# ---------------------------------------------------------------------------

def convert_flat_db_to_folder(db_path: str | Path) -> dict:
    """Convert a flat legacy `.db` into a Universe-as-Code folder universe.

    - the definition is decompiled to `<parent>/<stem>/` (same universe key:
      the saves keep their `saves/<stem>/` folder);
    - every embedded save is extracted to its own separate file, then linked
      to the new source (resynchronised on open);
    - the source is compiled (`.axiom-cache/universe.db` cache);
    - the original is kept as `<name>.db.bak` (manual recovery stays possible,
      and it disappears from the Hub discovery — no duplicate).

    Returns:
        A dict with keys source_dir and db_path — db_path is the new cache.
    """
    import sqlite3

    from axiom.compile import compile_universe, hash_directory
    from axiom.decompile import DecompileError, decompile_universe
    from axiom.savestore import extract_save, saves_dir_for

    db_path = Path(db_path)
    if not db_path.is_file():
        raise LibraryError(f"Universe not found: {db_path}")
    if db_path.parent.name == CACHE_DIRNAME:
        raise LibraryError("This universe is already a folder universe.")

    root = db_path.parent / db_path.stem
    if root.exists():
        raise LibraryError(f"Folder already exists: {root}")

    # 0. Provenance : AVANT extraction et décompilation, marquer 'runtime' les
    # entités joueur d'un db d'avant la colonne `origin` — sinon le joueur
    # créé au lobby deviendrait une entité de DÉFINITION de l'univers converti
    # (TICKET-037). Les saves extraites héritent ainsi du bon origin.
    _mark_legacy_runtime_entities(db_path)

    # 1. Saves embarquées → fichiers séparés (la clé d'univers est identique :
    # le stem du .db plat devient le nom du dossier).
    with closing(sqlite3.connect(str(db_path))) as conn:
        has_saves = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='Saves';"
        ).fetchone()
        save_ids = (
            [r[0] for r in conn.execute("SELECT save_id FROM Saves;")] if has_saves else []
        )
    sep_dir = saves_dir_for(db_path)
    for sid in save_ids:
        if (sep_dir / f"save_{sid}.db").exists():
            continue  # déjà extraite (conversion rejouée) : ne jamais écraser
        extract_save(db_path, sid)

    # 2. Définition → arborescence texte (sans les entités runtime, comme la
    # sync Studio), puis cache compilé.
    try:
        decompile_universe(db_path, root)
        _strip_runtime_entity_files(db_path, root)
        cache_db = compile_universe(root)
    except (DecompileError, CompileError) as exc:
        raise LibraryError(f"Conversion failed: {exc}") from exc

    # 3. Les saves extraites pointent vers la nouvelle source (resync §7.6).
    src_hash = hash_directory(root)
    for sid in save_ids:
        save_db = sep_dir / f"save_{sid}.db"
        if not save_db.is_file():
            continue
        with closing(sqlite3.connect(str(save_db))) as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO Save_Meta (key, value) VALUES (?, ?);",
                [
                    ("universe_db", str(cache_db)),
                    ("universe_source", str(root)),
                    ("definition_hash", src_hash),
                ],
            )
            conn.commit()

    # 4. L'original sort de la bibliothèque (mais reste récupérable).
    with closing(sqlite3.connect(str(db_path))) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    replace_with_retry(db_path, db_path.with_name(db_path.name + ".bak"))
    for suffix in ("-wal", "-shm"):
        unlink_with_retry(Path(str(db_path) + suffix), missing_ok=True)

    return {"source_dir": str(root), "db_path": str(cache_db)}


# ---------------------------------------------------------------------------
# Sync .db → source (TICKET-027 : Creator Studio sur univers-dossier)
# ---------------------------------------------------------------------------

# Jamais touchés par le miroir : le cache appartient au compilateur, .git à
# l'utilisateur.
_PROTECTED_TOP_LEVEL = (CACHE_DIRNAME, ".git")


def sync_source_if_any(db_path: str | Path) -> bool:
    """After a definition write (Creator Studio, Populate): when the `.db` is
    the cache of a folder universe, rewrite the text tree so it stays the
    source of truth (TICKET-027).

    Never raises: a Studio save must not fail because the text mirror failed
    (warning logged).

    Returns:
        True when a source was resynchronised.
    """
    root = universe_root_for(db_path)
    if root is None:
        return False
    try:
        sync_source_from_db(db_path, root)
        return True
    except Exception as exc:  # noqa: BLE001 — volontairement non bloquant
        logger.warning("Sync source impossible pour %s : %s", root.name, exc)
        return False


def _mark_legacy_runtime_entities(db_path: Path) -> None:
    """Pose la provenance 'runtime' sur les entités joueur d'un `.db` plat.

    Dans un `.db` plat, les joueurs d'avant la colonne `origin` sont en
    'definition' (défaut de migration) — la conversion les exporterait alors
    vers la définition de l'univers. Seules les entités `entity_type='player'`
    sont requalifiées (un joueur dans un `.db` plat vient du lobby ; les
    PNJ/factions viennent du Studio ou d'un Populate : c'est bien de la
    définition), en épargnant l'éventuel héros compagnon (référencé par la
    définition).
    """
    import sqlite3

    from axiom.schema import migrate_entities_origin_column

    migrate_entities_origin_column(str(db_path))
    with closing(sqlite3.connect(str(db_path))) as conn:
        hero = conn.execute(
            "SELECT value FROM Universe_Meta WHERE key = 'companion_hero_id';"
        ).fetchone()
        hero_id = hero[0] if hero else ""
        conn.execute(
            "UPDATE Entities SET origin = 'runtime' "
            "WHERE entity_type = 'player' AND entity_id != ?;",
            (hero_id,),
        )
        conn.commit()


def _strip_runtime_entity_files(db_path: Path, tree: Path) -> None:
    """Retire d'une arbo décompilée les entités `origin='runtime'` du `.db`.

    Le joueur et les PNJ nés en jeu n'appartiennent pas à la définition —
    partagé entre la sync Studio (TICKET-027) et la conversion (TICKET-037).
    L'id fait foi (lu DANS chaque fichier : le nom de fichier peut être
    désambiguïsé par le décompilateur).
    """
    import sqlite3
    import tomllib

    try:
        with closing(sqlite3.connect(str(db_path))) as conn:
            runtime_ids = {
                r[0] for r in conn.execute(
                    "SELECT entity_id FROM Entities WHERE origin = 'runtime';"
                )
            }
    except sqlite3.OperationalError:
        return  # colonne absente (db d'avant migration)
    if not runtime_ids:
        return
    ent_dir = tree / "entities"
    if not ent_dir.is_dir():
        return
    for f in ent_dir.glob("*.toml"):
        try:
            entity_id = tomllib.loads(f.read_text(encoding="utf-8")).get("entity_id")
        except (tomllib.TOMLDecodeError, OSError):
            continue
        if entity_id in runtime_ids:
            f.unlink()


def sync_source_from_db(db_path: str | Path, src_dir: str | Path) -> None:
    """Rewrite a universe's source tree from its `.db` (mirror).

    Decompiles to a temporary folder then aligns `src_dir` on it: files are
    added/overwritten, orphan files removed (definition removed in the Studio
    also disappears from the text). `.axiom-cache/` and `.git/` are never
    touched. Entities with `origin='runtime'` (the player, NPCs born in game)
    are not exported to the source.

    The cache hash is updated: the `.db` that was just written IS the
    compilation of the freshly rewritten source (lossless round-trip).
    """
    import tempfile

    from axiom.compile import CACHE_HASH_NAME, hash_directory
    from axiom.decompile import decompile_universe

    db_path = Path(db_path)
    src_dir = Path(src_dir)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tree = Path(tmp) / "tree"
        decompile_universe(db_path, tree)
        # Les entités runtime n'appartiennent pas à la définition.
        _strip_runtime_entity_files(db_path, tree)
        _mirror_tree(tree, src_dir)

    hash_file = src_dir / CACHE_DIRNAME / CACHE_HASH_NAME
    hash_file.parent.mkdir(parents=True, exist_ok=True)
    hash_file.write_text(hash_directory(src_dir), encoding="utf-8")


def _mirror_tree(new_tree: Path, dest: Path) -> None:
    """Aligne `dest` sur `new_tree` (copie + purge des orphelins), hors zones protégées."""
    import shutil

    new_files = {
        p.relative_to(new_tree) for p in new_tree.rglob("*")
        if p.is_file() and p.relative_to(new_tree).parts[0] not in _PROTECTED_TOP_LEVEL
    }
    for rel in new_files:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(new_tree / rel, target)

    for p in sorted(dest.rglob("*"), reverse=True):
        rel = p.relative_to(dest)
        if rel.parts and rel.parts[0] in _PROTECTED_TOP_LEVEL:
            continue
        if p.is_file() and rel not in new_files:
            p.unlink()
        elif p.is_dir():
            try:
                p.rmdir()  # ne supprime que les dossiers devenus vides
            except OSError:
                pass


def _entry(db_path: Path, source_dir: Path | None) -> dict:
    name, last_updated, difficulty = read_universe_card_metadata(str(db_path))
    return {
        "db_path": str(db_path),
        "source_dir": str(source_dir) if source_dir else None,
        "name": name,
        "last_updated": last_updated,
        "difficulty": difficulty,
    }
