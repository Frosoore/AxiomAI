"""axiom.package — Universe-as-Code : packaging `.axiom` v2 + compat v1.

Pilier 2 (doc §7.5, §7.10, annexe C.1). Un `.axiom` v2 est un **zip de l'arborescence
source** (TOML/MD) incluant le cache compilé `.axiom-cache/universe.db` pour un chargement
instantané.

Compat ascendante : les anciens `.axiom` v1 (zip de fichiers JSON) sont détectés et
convertis à la volée (v1 → .db → decompile → arbo v2 → recompile).

Zéro dépendance Qt : pur moteur. Le worker Qt `import_export_worker.py` devra à terme
n'être qu'une coquille fine appelant ces fonctions.
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
    """Erreur de packaging/dépaquetage d'un `.axiom`."""


# ---------------------------------------------------------------------------
# Pack (arbo source → .axiom v2)
# ---------------------------------------------------------------------------

def pack_universe(src_dir: str | Path, output_path: str | Path) -> Path:
    """Empaquette une arborescence source en archive `.axiom` v2.

    Recompile d'abord le cache (`.axiom-cache/universe.db`) pour l'embarquer, puis
    zippe toute l'arborescence.

    Args:
        src_dir:     Dossier source de l'univers (contient universe.toml).
        output_path: Chemin de l'archive `.axiom` à produire.

    Returns:
        Le chemin de l'archive créée.
    """
    src_dir = Path(src_dir)
    if not (src_dir / _V2_MARKER).exists():
        raise PackageError(f"Arborescence source invalide (pas de universe.toml) : {src_dir}")

    compile_universe(src_dir)  # garantit un cache à jour à embarquer

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(str(output_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(src_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(src_dir).as_posix())
    return output_path


# ---------------------------------------------------------------------------
# Unpack (.axiom → arbo source + cache, prêt à jouer)
# ---------------------------------------------------------------------------

def detect_format(axiom_path: str | Path) -> str:
    """Retourne 'v2', 'v1' ou lève PackageError selon le contenu de l'archive."""
    try:
        with zipfile.ZipFile(str(axiom_path), "r") as zf:
            names = set(zf.namelist())
    except (zipfile.BadZipFile, OSError) as exc:
        raise PackageError(f"Archive .axiom illisible : {exc}") from exc
    if _V2_MARKER in names:
        return "v2"
    if any(m in names for m in _V1_MARKERS):
        return "v1"
    raise PackageError("Format .axiom non reconnu (ni v2 ni v1).")


def unpack_universe(axiom_path: str | Path, dest_root: str | Path) -> Path:
    """Dépaquette un `.axiom` (v1 ou v2) en arborescence source jouable.

    v2 : décompresse, vérifie le hash → garde le `.db` embarqué si valide, sinon recompile.
    v1 : convertit (JSON → .db → decompile → arbo v2 → compile).

    Args:
        axiom_path: Chemin de l'archive `.axiom`.
        dest_root:  Dossier racine où matérialiser l'univers (un sous-dossier <name>/).

    Returns:
        Le chemin du dossier source de l'univers (contenant universe.toml + cache).
    """
    axiom_path = Path(axiom_path)
    dest_root = Path(dest_root)
    fmt = detect_format(axiom_path)
    name = axiom_path.stem

    if fmt == "v2":
        return _unpack_v2(axiom_path, dest_root, name)
    return _import_v1(axiom_path, dest_root, name)


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
    with tempfile.TemporaryDirectory() as tmp_dir:
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
            raise PackageError(f".axiom v1 corrompu : {exc}") from exc

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
