"""axiom.decompile — Universe-as-Code : décompilation d'un `.db` en arborescence source.

Pilier 2 (doc §7.10 + annexe C.1). L'inverse de `axiom.compile` : lit un univers
SQLite existant et régénère l'arborescence de fichiers texte (TOML/MD) équivalente.
Sert à migrer les univers `.db` v1 vers le format texte versionnable.

Préserve : entity_ids, rule_ids, calendrier, lore complet, locations + connections,
scheduled events, story setup, item & stat definitions, personas.

Écriture TOML : `tomlkit` (préserve un formatage propre, utile pour l'édition humaine).
Zéro dépendance Qt.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import tomlkit

from axiom.compile import (
    CACHE_DIRNAME,
    _FRONTMATTER_DELIM,
    _META_CALENDAR,
    _META_COMPANION_ENABLED,
    _META_COMPANION_HERO,
    _META_FIRST_MESSAGE,
    _META_GLOBAL_LORE,
    _META_NAME,
    _META_SYSTEM_PROMPT,
    _META_WORLD_TENSION,
    _STRUCTURED_META_KEYS,
)
from axiom.schema import get_connection
from axiom.time_system import CalendarConfig

_GLOBAL_LORE_FILE = "lore/_global_lore.md"
_FIRST_MESSAGE_FILE = "lore/_first_message.md"


class DecompileError(Exception):
    """Erreur de décompilation d'un univers."""


def _nl(text: str) -> str:
    """Normalise les fins de ligne en LF (format texte git-friendly, déterministe)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _write_text(path: Path, text: str) -> None:
    """Écrit du texte en UTF-8 avec des fins de ligne LF garanties (newline='')."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


# ---------------------------------------------------------------------------
# Lecteur de définition normalisé (partagé avec les tests de round-trip)
# ---------------------------------------------------------------------------

def read_definition(db_path: str | Path) -> dict[str, Any]:
    """Lit toutes les tables de **définition** d'un univers en structures normalisées.

    Ne lit jamais les tables runtime/save. Utilisé par la décompilation et par les
    tests de round-trip (comparaison sémantique).
    """
    path = str(db_path)
    with get_connection(path) as conn:
        conn.row_factory = sqlite3.Row

        meta = {
            row["key"]: row["value"]
            for row in conn.execute("SELECT key, value FROM Universe_Meta;")
        }

        entities = []
        for row in conn.execute(
            "SELECT entity_id, entity_type, name, description, is_active "
            "FROM Entities ORDER BY entity_id;"
        ):
            stats = {
                r["stat_key"]: r["stat_value"]
                for r in conn.execute(
                    "SELECT stat_key, stat_value FROM Entity_Stats "
                    "WHERE entity_id = ? ORDER BY stat_key;",
                    (row["entity_id"],),
                )
            }
            entities.append({
                "entity_id": row["entity_id"],
                "entity_type": row["entity_type"],
                "name": row["name"],
                "description": row["description"],
                "is_active": row["is_active"],
                "stats": stats,
            })

        rules = [
            {
                "rule_id": r["rule_id"],
                "priority": r["priority"],
                "conditions": json.loads(r["conditions"]),
                "actions": json.loads(r["actions"]),
                "target_entity": r["target_entity"],
            }
            for r in conn.execute(
                "SELECT rule_id, priority, conditions, actions, target_entity "
                "FROM Rules ORDER BY rule_id;"
            )
        ]

        stat_definitions = [
            {
                "stat_id": r["stat_id"],
                "name": r["name"],
                "description": r["description"],
                "value_type": r["value_type"],
                "parameters": json.loads(r["parameters"] or "{}"),
            }
            for r in conn.execute(
                "SELECT stat_id, name, description, value_type, parameters "
                "FROM Stat_Definitions ORDER BY stat_id;"
            )
        ]

        locations = [
            dict(r) for r in conn.execute(
                "SELECT location_id, name, scale, parent_id, description, x, y "
                "FROM Locations ORDER BY location_id;"
            )
        ]
        connections = [
            dict(r) for r in conn.execute(
                "SELECT source_id, target_id, distance_km FROM Location_Connections "
                "ORDER BY source_id, target_id;"
            )
        ]

        lore = [
            dict(r) for r in conn.execute(
                "SELECT entry_id, category, name, keywords, content FROM Lore_Book "
                "ORDER BY entry_id;"
            )
        ]
        events = [
            dict(r) for r in conn.execute(
                "SELECT event_id, trigger_minute, title, description "
                "FROM Scheduled_Events ORDER BY event_id;"
            )
        ]
        setup = [
            {
                "setup_id": r["setup_id"],
                "question": r["question"],
                "type": r["type"],
                "options": json.loads(r["options"] or "[]"),
                "max_selections": r["max_selections"],
                "priority": r["priority"],
            }
            for r in conn.execute(
                "SELECT setup_id, question, type, options, max_selections, priority "
                "FROM Story_Setup ORDER BY setup_id;"
            )
        ]
        items = [
            dict(r) for r in conn.execute(
                "SELECT item_id, name, description, category, weight, rarity "
                "FROM Item_Definitions ORDER BY item_id;"
            )
        ]

    return {
        "meta": meta,
        "entities": entities,
        "rules": rules,
        "stat_definitions": stat_definitions,
        "locations": locations,
        "connections": connections,
        "lore": lore,
        "events": events,
        "setup": setup,
        "items": items,
    }


# ---------------------------------------------------------------------------
# Helpers d'écriture
# ---------------------------------------------------------------------------

def _write_toml(path: Path, doc: Any) -> None:
    _write_text(path, tomlkit.dumps(doc))


def _build_universe_toml(meta: dict[str, str], src_dir: Path) -> None:
    """Reconstruit universe.toml + fichiers narratifs depuis Universe_Meta."""
    doc = tomlkit.document()

    meta_tbl = tomlkit.table()
    if _META_NAME in meta:
        meta_tbl["name"] = meta[_META_NAME]
    doc["meta"] = meta_tbl

    narrative = tomlkit.table()
    if _META_SYSTEM_PROMPT in meta:
        narrative["system_prompt"] = meta[_META_SYSTEM_PROMPT]
    if meta.get(_META_GLOBAL_LORE):
        _write_text(src_dir / _GLOBAL_LORE_FILE, _nl(meta[_META_GLOBAL_LORE]))
        narrative["global_lore_file"] = _GLOBAL_LORE_FILE
    if meta.get(_META_FIRST_MESSAGE):
        _write_text(src_dir / _FIRST_MESSAGE_FILE, _nl(meta[_META_FIRST_MESSAGE]))
        narrative["first_message_file"] = _FIRST_MESSAGE_FILE
    if _META_WORLD_TENSION in meta:
        # Conservé en chaîne verbatim (round-trip lossless).
        narrative["world_tension_level"] = meta[_META_WORLD_TENSION]
    if len(narrative):
        doc["narrative"] = narrative

    if meta.get(_META_CALENDAR):
        cfg = CalendarConfig.from_json(meta[_META_CALENDAR])
        cal = tomlkit.table()
        cal["minutes_per_hour"] = cfg.minutes_per_hour
        cal["hours_per_day"] = cfg.hours_per_day
        cal["days_per_month"] = cfg.days_per_month
        cal["month_names"] = cfg.month_names
        cal["start_day"] = cfg.start_day
        cal["start_hour"] = cfg.start_hour
        cal["start_minute"] = cfg.start_minute
        doc["calendar"] = cal

    if _META_COMPANION_ENABLED in meta or _META_COMPANION_HERO in meta:
        comp = tomlkit.table()
        if _META_COMPANION_ENABLED in meta:
            comp["enabled"] = meta[_META_COMPANION_ENABLED] == "1"
        if _META_COMPANION_HERO in meta:
            comp["hero_id"] = meta[_META_COMPANION_HERO]
        doc["companion"] = comp

    extra = {k: v for k, v in meta.items() if k not in _STRUCTURED_META_KEYS}
    if extra:
        extra_tbl = tomlkit.table()
        for key, value in sorted(extra.items()):
            extra_tbl[key] = value
        doc["extra"] = extra_tbl

    _write_toml(src_dir / "universe.toml", doc)


def _write_lore_entry(path: Path, entry: dict) -> None:
    """Écrit une entrée de lore en .md avec frontmatter TOML.

    Format : `+++\\n<toml>+++\\n<contenu>` — le contenu suit immédiatement le
    délimiteur fermant et est préservé tel quel (round-trip fidèle, modulo LF).
    """
    front = tomlkit.document()
    front["entry_id"] = entry["entry_id"]
    front["category"] = entry["category"] or ""
    front["name"] = entry["name"] or ""
    front["keywords"] = entry["keywords"] or ""
    text = (
        f"{_FRONTMATTER_DELIM}\n"
        f"{tomlkit.dumps(front)}"
        f"{_FRONTMATTER_DELIM}\n"
        f"{_nl(entry['content'])}"
    )
    _write_text(path, text)


def _safe_filename(raw: str) -> str:
    """Nom de fichier sûr dérivé d'un id (sans toucher au contenu stocké)."""
    cleaned = "".join(c if c.isalnum() or c in "-_" else "_" for c in raw)
    return cleaned or "unnamed"


class _UniqueNames:
    """Alloue des noms de fichiers uniques par dossier (déterministe).

    Deux ids distincts peuvent donner le même nom via `_safe_filename`
    (« bob.smith » / « bob_smith ») : sans désambiguïsation, le second fichier
    écraserait le premier en silence. Le compilateur lisant les ids DANS le
    fichier, le suffixe n'altère pas le round-trip.
    """

    def __init__(self) -> None:
        self._used: set[str] = set()

    def claim(self, raw_id: str) -> str:
        name = _safe_filename(raw_id)
        candidate = name
        counter = 2
        while candidate in self._used:
            candidate = f"{name}_{counter}"
            counter += 1
        self._used.add(candidate)
        return candidate


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------

def decompile_universe(db_path: str | Path, output_dir: str | Path) -> Path:
    """Décompile un univers `.db` en arborescence source texte.

    Args:
        db_path:    Chemin du `.db` univers à lire.
        output_dir: Dossier de destination (créé s'il n'existe pas).

    Returns:
        Le chemin du dossier source généré.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise DecompileError(f"Universe not found: {db_path}")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    data = read_definition(db_path)

    _build_universe_toml(data["meta"], out)

    if data["stat_definitions"]:
        doc = tomlkit.document()
        arr = tomlkit.aot()
        for d in data["stat_definitions"]:
            t = tomlkit.table()
            t["stat_id"] = d["stat_id"]
            t["name"] = d["name"]
            t["description"] = d["description"]
            t["value_type"] = d["value_type"]
            t["parameters"] = d["parameters"]
            arr.append(t)
        doc["definitions"] = arr
        _write_toml(out / "stats" / "definitions.toml", doc)

    ent_names = _UniqueNames()
    for ent in data["entities"]:
        doc = tomlkit.document()
        doc["entity_id"] = ent["entity_id"]
        doc["entity_type"] = ent["entity_type"]
        doc["name"] = ent["name"]
        doc["description"] = ent["description"]
        doc["is_active"] = bool(ent["is_active"])
        if ent["stats"]:
            stats_tbl = tomlkit.table()
            for k, v in ent["stats"].items():
                stats_tbl[k] = v
            doc["stats"] = stats_tbl
        _write_toml(out / "entities" / f"{ent_names.claim(ent['entity_id'])}.toml", doc)

    rule_names = _UniqueNames()
    for rule in data["rules"]:
        doc = tomlkit.document()
        doc["rule_id"] = rule["rule_id"]
        doc["priority"] = rule["priority"]
        doc["target_entity"] = rule["target_entity"]
        doc["conditions"] = rule["conditions"]
        doc["actions"] = rule["actions"]
        _write_toml(out / "rules" / f"{rule_names.claim(rule['rule_id'])}.toml", doc)

    if data["locations"] or data["connections"]:
        doc = tomlkit.document()
        locs = tomlkit.aot()
        for loc in data["locations"]:
            t = tomlkit.table()
            t["location_id"] = loc["location_id"]
            t["name"] = loc["name"]
            t["scale"] = loc["scale"]
            if loc["parent_id"]:
                t["parent_id"] = loc["parent_id"]
            t["description"] = loc["description"]
            t["x"] = loc["x"]
            t["y"] = loc["y"]
            locs.append(t)
        if data["locations"]:
            doc["locations"] = locs
        conns = tomlkit.aot()
        for c in data["connections"]:
            t = tomlkit.table()
            t["source_id"] = c["source_id"]
            t["target_id"] = c["target_id"]
            t["distance_km"] = c["distance_km"]
            conns.append(t)
        if data["connections"]:
            doc["connections"] = conns
        _write_toml(out / "locations" / "map.toml", doc)

    lore_names = _UniqueNames()
    for entry in data["lore"]:
        _write_lore_entry(out / "lore" / f"{lore_names.claim(entry['entry_id'])}.md", entry)

    event_names = _UniqueNames()
    for ev in data["events"]:
        doc = tomlkit.document()
        doc["event_id"] = ev["event_id"]
        doc["trigger_minute"] = ev["trigger_minute"]
        doc["title"] = ev["title"]
        doc["description"] = ev["description"]
        _write_toml(out / "events" / f"{event_names.claim(ev['event_id'])}.toml", doc)

    if data["setup"]:
        doc = tomlkit.document()
        arr = tomlkit.aot()
        for q in data["setup"]:
            t = tomlkit.table()
            t["setup_id"] = q["setup_id"]
            t["question"] = q["question"]
            t["type"] = q["type"]
            t["options"] = q["options"]
            t["max_selections"] = q["max_selections"]
            t["priority"] = q["priority"]
            arr.append(t)
        doc["questions"] = arr
        _write_toml(out / "setup" / "questions.toml", doc)

    item_names = _UniqueNames()
    for it in data["items"]:
        doc = tomlkit.document()
        doc["item_id"] = it["item_id"]
        doc["name"] = it["name"]
        doc["description"] = it["description"]
        doc["category"] = it["category"]
        doc["weight"] = it["weight"]
        doc["rarity"] = it["rarity"]
        _write_toml(out / "items" / f"{item_names.claim(it['item_id'])}.toml", doc)

    # .gitignore : le cache compilé n'est jamais versionné.
    (out / ".gitignore").write_text(f"{CACHE_DIRNAME}/\n", encoding="utf-8")
    return out
