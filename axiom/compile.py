"""axiom.compile — Universe-as-Code: compiling a source tree into a `.db` cache.

A universe is defined as a versionable **tree of text files** (TOML/MD); the
SQLite `.db` is only a **compiled cache** derived from the text. The text is
the source of truth. This module reads the tree and populates a runtime `.db`.

Zero Qt dependency: pure engine, drivable from the CLI (`axiom compile`).

Boundary: only the **definition tables** are produced here. The runtime/save
tables (Saves, Event_Log, State_Cache, Snapshots, Timeline, …) stay empty in
the cache — they do not belong to the universe definition.

TOML reading: `tomllib` (stdlib). Writing (decompile) uses `tomlkit`.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tomllib
from pathlib import Path
from typing import Any

from axiom.fsutil import replace_with_retry, unlink_with_retry
from axiom.schema import create_universe_db
from axiom.time_system import CalendarConfig

# ---------------------------------------------------------------------------
# Constantes
# ---------------------------------------------------------------------------

CACHE_DIRNAME = ".axiom-cache"
CACHE_DB_NAME = "universe.db"
CACHE_HASH_NAME = "cache_hash.txt"

# Frontmatter TOML pour les entrées de lore en Markdown : `+++\n<toml>\n+++\n<corps>`
_FRONTMATTER_DELIM = "+++"

# Clés Universe_Meta connues, gérées par des sections structurées de universe.toml.
# Toute autre clé est préservée verbatim dans [extra] (lossless).
_META_NAME = "universe_name"
_META_DESCRIPTION = "universe_description"
_META_SYSTEM_PROMPT = "system_prompt"
_META_GLOBAL_LORE = "global_lore"
_META_FIRST_MESSAGE = "first_message"
_META_WORLD_TENSION = "world_tension_level"
_META_CALENDAR = "calendar_config"
_META_COMPANION_ENABLED = "companion_mode_enabled"
_META_COMPANION_HERO = "companion_hero_id"

_STRUCTURED_META_KEYS = frozenset({
    _META_NAME,
    _META_DESCRIPTION,
    _META_SYSTEM_PROMPT,
    _META_GLOBAL_LORE,
    _META_FIRST_MESSAGE,
    _META_WORLD_TENSION,
    _META_CALENDAR,
    _META_COMPANION_ENABLED,
    _META_COMPANION_HERO,
})


class CompileError(Exception):
    """Universe compilation error (malformed source, missing required field)."""


# ---------------------------------------------------------------------------
# Hash de l'arborescence source (cache invalidation)
# ---------------------------------------------------------------------------

def _iter_source_files(src_dir: Path):
    """Itère sur les fichiers source pertinents (hors cache et VCS), triés."""
    for path in sorted(src_dir.rglob("*")):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(src_dir).parts
        if rel_parts and rel_parts[0] in (CACHE_DIRNAME, ".git"):
            continue
        yield path


def hash_directory(src_dir: Path) -> str:
    """Stable hash of the source content (relative path + bytes of each file)."""
    h = hashlib.sha256()
    for path in _iter_source_files(src_dir):
        rel = path.relative_to(src_dir).as_posix()
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Helpers de lecture
# ---------------------------------------------------------------------------

def _load_toml(path: Path) -> dict[str, Any]:
    """Charge un fichier TOML. Lève CompileError si malformé."""
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        raise CompileError(f"Invalid TOML: {path} — {exc}") from exc


def _require(data: dict, key: str, ctx: str) -> Any:
    """Récupère une clé requise ou lève CompileError."""
    if key not in data:
        raise CompileError(f"Required field '{key}' missing in {ctx}")
    return data[key]


def _resolve_text(src_dir: Path, data: dict, inline_key: str, file_key: str) -> str:
    """Résout un texte fourni soit inline (`inline_key`) soit via fichier (`file_key`)."""
    if data.get(file_key):
        target = src_dir / str(data[file_key])
        try:
            # newline="" : pas de traduction de fin de ligne (fidélité LF).
            # Via open() et non read_text(newline=) : ce dernier exige Python 3.13+ (TICKET-049).
            with target.open("r", encoding="utf-8", newline="") as fh:
                return fh.read()
        except OSError as exc:
            raise CompileError(f"Referenced file not found: {target} — {exc}") from exc
    return str(data.get(inline_key, ""))


def _toml_files(directory: Path):
    """Itère sur les *.toml d'un dossier (non récursif), hors `_index.toml`, triés."""
    if not directory.is_dir():
        return
    for path in sorted(directory.glob("*.toml")):
        if path.name == "_index.toml":
            continue
        yield path


# ---------------------------------------------------------------------------
# Parsers (chacun tolérant à l'absence du fichier/dossier)
# ---------------------------------------------------------------------------

def _parse_universe(src_dir: Path) -> tuple[dict[str, str], set[str]]:
    """Parse universe.toml → dict {clé Universe_Meta: valeur str}.

    Retourne aussi l'ensemble des fichiers référencés (`*_file`) pour que le
    parseur de lore les exclue du Lore_Book.
    """
    path = src_dir / "universe.toml"
    if not path.exists():
        raise CompileError(f"Required universe.toml not found in {src_dir}")

    data = _load_toml(path)
    meta: dict[str, str] = {}
    referenced: set[str] = set()

    meta_section = data.get("meta", {})
    name = meta_section.get("name")
    if name:
        meta[_META_NAME] = str(name)
    description = meta_section.get("description")
    if description:
        meta[_META_DESCRIPTION] = str(description)

    narrative = data.get("narrative", {})
    if "system_prompt" in narrative:
        meta[_META_SYSTEM_PROMPT] = str(narrative["system_prompt"])
    if narrative.get("global_lore_file"):
        referenced.add(str(narrative["global_lore_file"]))
    if narrative.get("first_message_file"):
        referenced.add(str(narrative["first_message_file"]))
    global_lore = _resolve_text(src_dir, narrative, "global_lore", "global_lore_file")
    if global_lore:
        meta[_META_GLOBAL_LORE] = global_lore
    first_message = _resolve_text(src_dir, narrative, "first_message", "first_message_file")
    if first_message:
        meta[_META_FIRST_MESSAGE] = first_message
    if "world_tension_level" in narrative:
        meta[_META_WORLD_TENSION] = str(narrative["world_tension_level"])

    calendar = data.get("calendar")
    if calendar:
        cfg = CalendarConfig(
            minutes_per_hour=int(calendar.get("minutes_per_hour", 60)),
            hours_per_day=int(calendar.get("hours_per_day", 24)),
            days_per_month=list(calendar.get("days_per_month", [30] * 12)),
            month_names=list(calendar.get("month_names", [f"Month {i + 1}" for i in range(12)])),
            start_day=int(calendar.get("start_day", 1)),
            start_hour=int(calendar.get("start_hour", 0)),
            start_minute=int(calendar.get("start_minute", 0)),
        )
        meta[_META_CALENDAR] = cfg.to_json()

    companion = data.get("companion")
    if companion is not None:
        # Mapping clé par clé (symétrique avec decompile → round-trip lossless).
        # Le moteur stocke `companion_mode_enabled` en "1"/"0" (comparé `== "1"`).
        if "enabled" in companion:
            meta[_META_COMPANION_ENABLED] = "1" if companion["enabled"] else "0"
        if "hero_id" in companion:
            meta[_META_COMPANION_HERO] = str(companion["hero_id"])

    # Passthrough verbatim des clés inconnues (lossless).
    for key, value in data.get("extra", {}).items():
        meta[str(key)] = str(value)

    return meta, referenced


def _parse_stat_definitions(src_dir: Path) -> list[tuple]:
    """stats/definitions.toml → lignes Stat_Definitions."""
    path = src_dir / "stats" / "definitions.toml"
    if not path.exists():
        return []
    data = _load_toml(path)
    rows: list[tuple] = []
    for entry in data.get("definitions", []):
        params = entry.get("parameters", {})
        rows.append((
            _require(entry, "stat_id", path.name),
            str(entry.get("name", entry["stat_id"])),
            str(entry.get("description", "")),
            str(entry.get("value_type", "numeric")),
            json.dumps(params) if isinstance(params, (dict, list)) else str(params),
        ))
    return rows


def _parse_entities(src_dir: Path) -> list[tuple[tuple, dict]]:
    """entities/*.toml → [(ligne Entities, dict stats)]."""
    out: list[tuple[tuple, dict]] = []
    for path in _toml_files(src_dir / "entities"):
        data = _load_toml(path)
        entity_id = _require(data, "entity_id", path.name)
        row = (
            entity_id,
            str(data.get("entity_type", "npc")),
            str(data.get("name", entity_id)),
            str(data.get("description", "")),
            1 if data.get("is_active", True) else 0,
        )
        stats = {str(k): str(v) for k, v in data.get("stats", {}).items()}
        out.append((row, stats))
    return out


def _parse_rules(src_dir: Path) -> list[tuple]:
    """rules/*.toml → lignes Rules (conditions/actions sérialisées en JSON)."""
    rows: list[tuple] = []
    for path in _toml_files(src_dir / "rules"):
        data = _load_toml(path)
        rows.append((
            _require(data, "rule_id", path.name),
            int(data.get("priority", 0)),
            json.dumps(data.get("conditions", {})),
            json.dumps(data.get("actions", [])),
            str(data.get("target_entity", "*")),
        ))
    return rows


def _parse_locations(src_dir: Path) -> tuple[list[tuple], list[tuple]]:
    """locations/map.toml → (lignes Locations, lignes Location_Connections)."""
    path = src_dir / "locations" / "map.toml"
    if not path.exists():
        return [], []
    data = _load_toml(path)
    locations: list[tuple] = []
    for loc in data.get("locations", []):
        locations.append((
            _require(loc, "location_id", path.name),
            str(loc.get("name", loc["location_id"])),
            str(loc.get("scale", "poi")),
            loc.get("parent_id"),
            str(loc.get("description", "")),
            float(loc.get("x", 0)),
            float(loc.get("y", 0)),
        ))
    connections: list[tuple] = []
    for conn in data.get("connections", []):
        connections.append((
            _require(conn, "source_id", path.name),
            _require(conn, "target_id", path.name),
            int(conn.get("distance_km", 0)),
        ))
    return locations, connections


def _parse_lore(src_dir: Path, referenced: set[str]) -> list[tuple]:
    """lore/**/*.md → lignes Lore_Book.

    Chaque .md peut porter un frontmatter TOML (`+++ … +++`) avec entry_id,
    category, name, keywords ; le corps = content. Les fichiers référencés par
    universe.toml (`*_file`) sont exclus.
    """
    lore_dir = src_dir / "lore"
    if not lore_dir.is_dir():
        return []
    referenced_paths = {(src_dir / r).resolve() for r in referenced}
    rows: list[tuple] = []
    for path in sorted(lore_dir.rglob("*.md")):
        if path.resolve() in referenced_paths:
            continue
        # open(newline="") et non read_text(newline=) : ce dernier exige Python 3.13+ (TICKET-049).
        with path.open("r", encoding="utf-8", newline="") as fh:
            front, body = _split_frontmatter(fh.read())
        default_id = path.relative_to(lore_dir).with_suffix("").as_posix().replace("/", "_")
        rows.append((
            str(front.get("entry_id", default_id)),
            str(front.get("category", "")),
            str(front.get("name", path.stem.replace("_", " ").title())),
            str(front.get("keywords", "")),
            body,
        ))
    return rows


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Sépare un frontmatter TOML optionnel (`+++ … +++`) du corps Markdown.

    Préserve le corps **octet pour octet** (pas de splitlines/strip) pour garantir
    un round-trip fidèle.
    """
    # On lit le .md en `newline=""` (corps préservé octet pour octet) : il faut
    # donc tolérer les deux styles de fin de ligne. Un fichier édité sous Windows
    # commence par "+++\r\n" — sans cette tolérance, son frontmatter (entry_id,
    # category, keywords) serait silencieusement ignoré et l'id retomberait sur
    # le nom de fichier.
    for nl in ("\n", "\r\n"):
        opener = _FRONTMATTER_DELIM + nl
        if not text.startswith(opener):
            continue
        rest = text[len(opener):]
        closer = nl + _FRONTMATTER_DELIM + nl
        end = rest.find(closer)
        if end == -1:
            break  # ouvert mais non refermé dans le même style → pas de frontmatter
        front_text = rest[:end]
        body = rest[end + len(closer):]
        try:
            return tomllib.loads(front_text), body
        except tomllib.TOMLDecodeError as exc:
            raise CompileError(f"Invalid TOML frontmatter — {exc}") from exc
    return {}, text


def _parse_events(src_dir: Path) -> list[tuple]:
    """events/*.toml → lignes Scheduled_Events."""
    rows: list[tuple] = []
    for path in _toml_files(src_dir / "events"):
        data = _load_toml(path)
        rows.append((
            _require(data, "event_id", path.name),
            int(data.get("trigger_minute", 0)),
            str(data.get("title", "")),
            str(data.get("description", "")),
        ))
    return rows


def _parse_setup(src_dir: Path) -> list[tuple]:
    """setup/questions.toml → lignes Story_Setup."""
    path = src_dir / "setup" / "questions.toml"
    if not path.exists():
        return []
    data = _load_toml(path)
    rows: list[tuple] = []
    for q in data.get("questions", []):
        options = q.get("options", [])
        rows.append((
            _require(q, "setup_id", path.name),
            str(q.get("question", "")),
            str(q.get("type", "text")),
            json.dumps(options) if isinstance(options, list) else str(options),
            int(q.get("max_selections", 1)),
            int(q.get("priority", 0)),
        ))
    return rows


def _parse_items(src_dir: Path) -> list[tuple]:
    """items/*.toml → lignes Item_Definitions."""
    rows: list[tuple] = []
    for path in _toml_files(src_dir / "items"):
        data = _load_toml(path)
        rows.append((
            _require(data, "item_id", path.name),
            str(data.get("name", data["item_id"])),
            str(data.get("description", "")),
            str(data.get("category", "misc")),
            float(data.get("weight", 0.0)),
            str(data.get("rarity", "common")),
        ))
    return rows


# ---------------------------------------------------------------------------
# Population de la base
# ---------------------------------------------------------------------------

def _populate(conn: sqlite3.Connection, parsed: dict[str, Any]) -> None:
    """Insère toutes les données de définition parsées dans une DB fraîche."""
    conn.execute("PRAGMA foreign_keys=ON;")

    conn.executemany(
        "INSERT OR REPLACE INTO Universe_Meta (key, value) VALUES (?, ?);",
        list(parsed["meta"].items()),
    )
    conn.executemany(
        "INSERT INTO Stat_Definitions (stat_id, name, description, value_type, parameters) "
        "VALUES (?, ?, ?, ?, ?);",
        parsed["stat_definitions"],
    )
    for row, stats in parsed["entities"]:
        conn.execute(
            "INSERT INTO Entities (entity_id, entity_type, name, description, is_active) "
            "VALUES (?, ?, ?, ?, ?);",
            row,
        )
        conn.executemany(
            "INSERT INTO Entity_Stats (entity_id, stat_key, stat_value) VALUES (?, ?, ?);",
            [(row[0], k, v) for k, v in stats.items()],
        )
    conn.executemany(
        "INSERT INTO Rules (rule_id, priority, conditions, actions, target_entity) "
        "VALUES (?, ?, ?, ?, ?);",
        parsed["rules"],
    )
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
    conn.executemany(
        "INSERT INTO Lore_Book (entry_id, category, name, keywords, content) "
        "VALUES (?, ?, ?, ?, ?);",
        parsed["lore"],
    )
    conn.executemany(
        "INSERT INTO Scheduled_Events (event_id, trigger_minute, title, description) "
        "VALUES (?, ?, ?, ?);",
        parsed["events"],
    )
    conn.executemany(
        "INSERT INTO Story_Setup (setup_id, question, type, options, max_selections, priority) "
        "VALUES (?, ?, ?, ?, ?, ?);",
        parsed["setup"],
    )
    conn.executemany(
        "INSERT INTO Item_Definitions (item_id, name, description, category, weight, rarity) "
        "VALUES (?, ?, ?, ?, ?, ?);",
        parsed["items"],
    )
    conn.commit()


def _parse_tree(src_dir: Path) -> dict[str, Any]:
    """Parse l'arborescence source complète en structures Python prêtes pour la DB."""
    meta, referenced = _parse_universe(src_dir)
    locations, connections = _parse_locations(src_dir)
    return {
        "meta": meta,
        "stat_definitions": _parse_stat_definitions(src_dir),
        "entities": _parse_entities(src_dir),
        "rules": _parse_rules(src_dir),
        "locations": locations,
        "connections": connections,
        "lore": _parse_lore(src_dir, referenced),
        "events": _parse_events(src_dir),
        "setup": _parse_setup(src_dir),
        "items": _parse_items(src_dir),
    }


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------

def compile_universe(
    src_dir: str | Path,
    output_db: str | Path | None = None,
    force: bool = False,
) -> Path:
    """Compile a source tree into a runtime SQLite database.

    Args:
        src_dir:   Universe source folder (contains universe.toml).
        output_db: Path of the `.db` to produce. Defaults to
                   `<src_dir>/.axiom-cache/universe.db`.
        force:     Recompile even if the source hash is unchanged.

    Returns:
        The path of the compiled `.db`.
    """
    src_dir = Path(src_dir)
    if not src_dir.is_dir():
        raise CompileError(f"Source folder not found: {src_dir}")

    if output_db is None:
        output_db = src_dir / CACHE_DIRNAME / CACHE_DB_NAME
    output_db = Path(output_db)

    src_hash = hash_directory(src_dir)
    hash_file = src_dir / CACHE_DIRNAME / CACHE_HASH_NAME

    if not force and output_db.exists() and hash_file.exists():
        if hash_file.read_text(encoding="utf-8").strip() == src_hash:
            return output_db  # cache à jour

    parsed = _parse_tree(src_dir)

    # Construction atomique : on écrit dans un fichier temporaire puis on remplace.
    output_db.parent.mkdir(parents=True, exist_ok=True)
    tmp_db = output_db.with_suffix(output_db.suffix + ".tmp")
    _remove_db_files(tmp_db)

    create_universe_db(str(tmp_db))
    conn = sqlite3.connect(str(tmp_db))
    try:
        _populate(conn, parsed)
        # Vide le WAL dans le fichier principal avant la bascule (sinon le .db
        # déplacé serait incomplet et les sidecars -wal/-shm seraient orphelins).
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    finally:
        conn.close()

    _remove_db_files(output_db)
    replace_with_retry(tmp_db, output_db)  # bascule atomique, retry anti-lock Windows
    _remove_db_files(tmp_db, keep_main=True)  # nettoie les sidecars -wal/-shm résiduels

    hash_file.parent.mkdir(parents=True, exist_ok=True)
    hash_file.write_text(src_hash, encoding="utf-8")
    return output_db


def _remove_db_files(db: Path, keep_main: bool = False) -> None:
    """Supprime un .db et ses sidecars WAL (-wal/-shm)."""
    suffixes = ("-wal", "-shm") if keep_main else ("", "-wal", "-shm")
    for suffix in suffixes:
        unlink_with_retry(Path(str(db) + suffix), missing_ok=True)
