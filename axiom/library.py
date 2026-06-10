"""axiom.library — Universe-as-Code : découverte des univers installés.

Le Hub listait historiquement les `*.db` à plat dans `~/AxiomAI/universes/`.
Avec le Pilier 2, un univers importé (`.axiom` v2) ou créé en mode source vit
dans un **dossier** `universes/<name>/` (universe.toml + `.axiom-cache/universe.db`).
Ce module fournit la découverte unifiée des deux formes, côté moteur (zéro Qt) —
le `DbWorker` du Hub n'est qu'une coquille au-dessus.
"""

from __future__ import annotations

from pathlib import Path

from axiom.compile import CACHE_DIRNAME, CompileError
from axiom.db_helpers import read_universe_card_metadata
from axiom.dev import ensure_compiled
from axiom.logger import logger

_SOURCE_MARKER = "universe.toml"


class LibraryError(Exception):
    """Erreur de gestion de la bibliothèque d'univers."""


def universe_root_for(db_path: str | Path) -> Path | None:
    """Retourne le dossier source d'un univers si `db_path` est son cache compilé.

    `universes/<name>/.axiom-cache/universe.db` → `universes/<name>/`.
    Retourne None pour un `.db` plat (legacy) ou un chemin quelconque.
    """
    db_path = Path(db_path)
    if db_path.parent.name != CACHE_DIRNAME:
        return None
    root = db_path.parent.parent
    return root if (root / _SOURCE_MARKER).exists() else None


def discover_universes(library_dir: str | Path) -> list[dict]:
    """Liste les univers jouables d'un dossier bibliothèque.

    Deux formes reconnues :
    - `*.db` à plat (legacy) ;
    - sous-dossier contenant `universe.toml` (Universe-as-Code), compilé à la
      demande si le cache est absent/périmé (no-op si le hash est inchangé).

    Un dossier source malformé est ignoré (log warning) : il ne doit pas
    empêcher le Hub d'afficher le reste de la bibliothèque.

    Returns:
        Liste de dicts {db_path, source_dir, name, last_updated, difficulty},
        triée par nom de fichier/dossier. `source_dir` vaut None pour un `.db`
        plat.
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
    """Diff texte entre deux arborescences source (zones protégées exclues).

    Sert à la prévisualisation : `before_dir` = source réelle, `after_dir` =
    arbre temporaire reflétant ce que la source deviendrait.

    Returns:
        [{"path": str, "status": "added"|"modified"|"removed", "diff": str}]
        — `diff` est un diff unifié, trié par chemin.
    """
    import difflib

    before_dir = Path(before_dir)
    after_dir = Path(after_dir)

    def _files(root: Path) -> dict[str, Path]:
        return {
            str(p.relative_to(root)): p
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
    """Applique un arbre source validé : miroir vers la source + recompilation.

    `staged_dir` est un instantané complet de la future source (produit par la
    sandbox de prévisualisation) : il remplace la source — zones protégées
    (`.axiom-cache/`, `.git/`) intactes — puis la définition est recompilée
    **in-place** dans `db_path` (runtime intact).
    """
    from axiom.dev import refresh_definition

    _mirror_tree(Path(staged_dir), Path(src_dir))
    return refresh_definition(src_dir, db_path)


# ---------------------------------------------------------------------------
# Conversion .db plat → univers-dossier (TICKET-029)
# ---------------------------------------------------------------------------

def convert_flat_db_to_folder(db_path: str | Path) -> dict:
    """Convertit un `.db` plat (legacy) en univers-dossier Universe-as-Code.

    - la définition est décompilée vers `<parent>/<stem>/` (même clé d'univers :
      les saves gardent leur dossier `saves/<stem>/`) ;
    - chaque save embarquée est extraite vers son propre fichier séparé, puis
      reliée à la nouvelle source (resync à l'ouverture, §7.6) ;
    - la source est compilée (cache `.axiom-cache/universe.db`) ;
    - l'original est conservé en `<nom>.db.bak` (récupération manuelle possible,
      et il disparaît de la découverte du Hub — pas de doublon).

    Returns:
        {"source_dir": str, "db_path": str} — `db_path` est le nouveau cache.
    """
    import sqlite3

    from axiom.compile import compile_universe, hash_directory
    from axiom.decompile import DecompileError, decompile_universe
    from axiom.savestore import extract_save, saves_dir_for

    db_path = Path(db_path)
    if not db_path.is_file():
        raise LibraryError(f"Univers introuvable : {db_path}")
    if db_path.parent.name == CACHE_DIRNAME:
        raise LibraryError("Cet univers est déjà un univers-dossier.")

    root = db_path.parent / db_path.stem
    if root.exists():
        raise LibraryError(f"Le dossier existe déjà : {root}")

    # 1. Saves embarquées → fichiers séparés (la clé d'univers est identique :
    # le stem du .db plat devient le nom du dossier).
    with sqlite3.connect(str(db_path)) as conn:
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

    # 2. Définition → arborescence texte, puis cache compilé.
    try:
        decompile_universe(db_path, root)
        cache_db = compile_universe(root)
    except (DecompileError, CompileError) as exc:
        raise LibraryError(f"Conversion impossible : {exc}") from exc

    # 3. Les saves extraites pointent vers la nouvelle source (resync §7.6).
    src_hash = hash_directory(root)
    for sid in save_ids:
        save_db = sep_dir / f"save_{sid}.db"
        if not save_db.is_file():
            continue
        with sqlite3.connect(str(save_db)) as conn:
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
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    db_path.replace(db_path.with_name(db_path.name + ".bak"))
    for suffix in ("-wal", "-shm"):
        leftover = Path(str(db_path) + suffix)
        if leftover.exists():
            leftover.unlink()

    return {"source_dir": str(root), "db_path": str(cache_db)}


# ---------------------------------------------------------------------------
# Sync .db → source (TICKET-027 : Creator Studio sur univers-dossier)
# ---------------------------------------------------------------------------

# Jamais touchés par le miroir : le cache appartient au compilateur, .git à
# l'utilisateur.
_PROTECTED_TOP_LEVEL = (CACHE_DIRNAME, ".git")


def sync_source_if_any(db_path: str | Path) -> bool:
    """Après une écriture de définition (Creator Studio, Populate) : si le `.db`
    est le cache d'un univers-dossier, réécrit l'arbo texte pour qu'elle reste
    la vérité (TICKET-027).

    Ne lève jamais : une sauvegarde Studio ne doit pas échouer parce que le
    miroir texte a échoué (log warning).

    Returns:
        True si une source a été resynchronisée.
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


def sync_source_from_db(db_path: str | Path, src_dir: str | Path) -> None:
    """Réécrit l'arborescence source d'un univers depuis son `.db` (miroir).

    Décompile vers un dossier temporaire puis aligne `src_dir` dessus :
    fichiers ajoutés/écrasés, fichiers orphelins supprimés (la définition
    retirée dans le Studio disparaît aussi du texte). `.axiom-cache/` et
    `.git/` ne sont jamais touchés. Les entités `origin='runtime'` (joueur,
    PNJ nés en jeu) ne sont pas exportées vers la source.

    Le hash de cache est mis à jour : le `.db` qui vient d'être écrit EST la
    compilation de la source fraîchement réécrite (round-trip lossless).
    """
    import sqlite3
    import tempfile

    from axiom.compile import CACHE_HASH_NAME, hash_directory
    from axiom.decompile import _safe_filename, decompile_universe

    db_path = Path(db_path)
    src_dir = Path(src_dir)

    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "tree"
        decompile_universe(db_path, tree)

        # Les entités runtime n'appartiennent pas à la définition.
        try:
            with sqlite3.connect(str(db_path)) as conn:
                runtime_ids = [
                    r[0] for r in conn.execute(
                        "SELECT entity_id FROM Entities WHERE origin = 'runtime';"
                    )
                ]
        except sqlite3.OperationalError:
            runtime_ids = []  # colonne absente (db d'avant migration)
        for eid in runtime_ids:
            f = tree / "entities" / f"{_safe_filename(eid)}.toml"
            if f.exists():
                f.unlink()

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
