"""Headless canonize: extract recent story into universe definition.

Mirrors workers/db_tasks.py::CanonizeStoryTask without Qt. Preview stages a
source-tree sandbox; apply writes it back through axiom.library.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import uuid
from contextlib import closing
from pathlib import Path
from typing import Any, Callable

from axiom.backends.base import LLMBackend
from axiom.library import (
    apply_staged_source,
    diff_source_trees,
    sync_source_from_db,
    universe_root_for,
)
from axiom.logger import logger
from axiom.schema import get_connection


def discard_staged_source(staged_dir: str | Path | None) -> None:
    """Delete a preview sandbox (the parent of staged_dir)."""
    if not staged_dir:
        return
    shutil.rmtree(Path(staged_dir).parent, ignore_errors=True)


_UAC_FOLDER_REQUIRED = "Canonize needs a folder-backed universe (Universe-as-Code)."


def _stage_source_change(universe_db: str, mutate: Callable[[str], Any]) -> dict:
    src_root = universe_root_for(universe_db)
    if src_root is None:
        raise ValueError(_UAC_FOLDER_REQUIRED)

    stage_root = Path(tempfile.mkdtemp(prefix="axiom_stage_"))
    tmp_db = stage_root / "preview.db"
    with closing(sqlite3.connect(universe_db)) as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    shutil.copyfile(universe_db, tmp_db)

    def _synced_copy(name: str) -> Path:
        tree = stage_root / name
        shutil.copytree(src_root, tree, ignore=shutil.ignore_patterns(".axiom-cache", ".git"))
        sync_source_from_db(tmp_db, tree)
        return tree

    baseline = _synced_copy("baseline")
    try:
        result = mutate(str(tmp_db))
        staged = _synced_copy("tree")
    except BaseException:
        shutil.rmtree(stage_root, ignore_errors=True)
        raise
    diffs = diff_source_trees(baseline, staged)
    if not diffs:
        shutil.rmtree(stage_root, ignore_errors=True)
        return {"result": result, "diffs": [], "staged_dir": "", "src_dir": str(src_root)}
    return {"result": result, "diffs": diffs, "staged_dir": str(staged), "src_dir": str(src_root)}


def _insert_canon(db: str, entities: list, lore: list) -> dict:
    from axiom.populate import entity_id_for

    inserted = {"entities": 0, "lore": 0}
    with get_connection(db) as conn:
        existing_ids = {str(r[0]).lower() for r in conn.execute("SELECT entity_id FROM Entities;")}
        for ent in entities or []:
            name = str(ent.get("name", "")).strip()
            if not name:
                continue
            eid = entity_id_for(name)
            if eid in existing_ids:
                continue
            etype = str(ent.get("entity_type", "npc")).lower()
            if etype not in ("npc", "faction"):
                etype = "npc"
            conn.execute(
                "INSERT INTO Entities (entity_id, name, entity_type, description, is_active) "
                "VALUES (?, ?, ?, ?, 1);",
                (eid, name, etype, str(ent.get("description", "")).strip()),
            )
            existing_ids.add(eid)
            inserted["entities"] += 1

        existing_lore = {str(r[0]).lower() for r in conn.execute("SELECT name FROM Lore_Book;")}
        for entry in lore or []:
            name = str(entry.get("name", "")).strip()
            if not name or name.lower() in existing_lore:
                continue
            conn.execute(
                "INSERT INTO Lore_Book (entry_id, category, name, keywords, content) "
                "VALUES (?, ?, ?, ?, ?);",
                (
                    str(uuid.uuid4()),
                    str(entry.get("category", "General")) or "General",
                    name,
                    str(entry.get("keywords", "")).strip(),
                    str(entry.get("content", "")).strip(),
                ),
            )
            existing_lore.add(name.lower())
            inserted["lore"] += 1
        conn.commit()
    return inserted


def _insert_session_canon(save_db: str, entities: list, lore: list) -> dict:
    """Write canonize picks into the save only (Session_Lore + runtime entities)."""
    from axiom.populate import entity_id_for
    from axiom.schema import ensure_entity_type, migrate_schema

    migrate_schema(save_db)
    inserted = {"entities": 0, "lore": 0}
    with get_connection(save_db) as conn:
        existing_ids = {str(r[0]).lower() for r in conn.execute("SELECT entity_id FROM Entities;")}
        for ent in entities or []:
            name = str(ent.get("name", "")).strip()
            if not name:
                continue
            eid = entity_id_for(name)
            if eid in existing_ids:
                continue
            etype = str(ent.get("entity_type", "npc")).lower()
            if etype not in ("npc", "faction"):
                etype = "npc"
            ensure_entity_type(conn, etype)
            conn.execute(
                "INSERT INTO Entities (entity_id, name, entity_type, description, is_active, origin) "
                "VALUES (?, ?, ?, ?, 1, 'runtime');",
                (eid, name, etype, str(ent.get("description", "")).strip()),
            )
            existing_ids.add(eid)
            inserted["entities"] += 1

        existing_lore = set()
        try:
            existing_lore = {
                str(r[0]).lower()
                for r in conn.execute("SELECT name FROM Session_Lore;")
            }
        except sqlite3.Error:
            existing_lore = set()
        for entry in lore or []:
            name = str(entry.get("name", "")).strip()
            if not name or name.lower() in existing_lore:
                continue
            conn.execute(
                "INSERT INTO Session_Lore "
                "(entry_id, save_id, category, name, keywords, content, origin_turn) "
                "VALUES (?, ?, ?, ?, ?, ?, 0);",
                (
                    str(uuid.uuid4()),
                    _first_save_id(conn),
                    str(entry.get("category", "General")) or "General",
                    name,
                    str(entry.get("keywords", "")).strip(),
                    str(entry.get("content", "")).strip(),
                ),
            )
            existing_lore.add(name.lower())
            inserted["lore"] += 1
        conn.commit()
    return inserted


def _first_save_id(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT save_id FROM Saves LIMIT 1;").fetchone()
    return str(row[0]) if row else ""


def _resolve_universe_db(save_or_universe_db: str) -> str:
    from axiom.savestore import is_separated_save_db

    candidate = save_or_universe_db
    if is_separated_save_db(save_or_universe_db):
        with closing(sqlite3.connect(save_or_universe_db)) as conn:
            meta = dict(conn.execute("SELECT key, value FROM Save_Meta;").fetchall())
        candidate = meta.get("universe_db", "")
    if candidate and Path(candidate).is_file() and universe_root_for(candidate):
        return candidate
    raise ValueError(_UAC_FOLDER_REQUIRED)


def canonize_story(
    db_path: str,
    narrative_text: str,
    *,
    preview: bool = True,
    llm: LLMBackend | None = None,
    on_status: Callable[[str], None] | None = None,
) -> dict:
    """Extract canon from recent narrative into the universe definition.

    preview=True stages a sandbox and returns diffs (nothing written).
    preview=False applies immediately and refreshes the save definition.
    """
    from axiom.config import build_llm_from_config, load_config, resolve_extraction_model
    from axiom.prompts import build_canonize_prompt

    def _status(msg: str) -> None:
        if on_status:
            on_status(msg)

    universe_db = _resolve_universe_db(db_path)
    _status("Reading universe canon...")
    with get_connection(universe_db) as conn:
        existing_entities = [str(r[0]) for r in conn.execute(
            "SELECT name FROM Entities WHERE is_active = 1;")]
        existing_lore = [str(r[0]) for r in conn.execute("SELECT name FROM Lore_Book;")]
        row = conn.execute(
            "SELECT value FROM Universe_Meta WHERE key = 'global_lore';").fetchone()
        global_lore = row[0] if row else ""

    _status("Canonizing recent story...")
    if llm is None:
        cfg = load_config()
        llm = build_llm_from_config(cfg, model_override=resolve_extraction_model(cfg))
    prompt = build_canonize_prompt(
        narrative_text, existing_entities, existing_lore, global_lore)
    resp = llm.complete(prompt, response_format="json")
    data = resp.tool_call if isinstance(resp.tool_call, dict) else {}
    entities = data.get("entities", [])
    lore = data.get("lore_entries", [])

    info = _stage_source_change(
        universe_db, lambda tmp_db: _insert_canon(tmp_db, entities, lore))
    info["counts"] = info.pop("result")
    info["universe_db"] = universe_db
    info["applied"] = False
    info["entities"] = entities or []
    info["lore_entries"] = lore or []

    if not preview:
        # Auto-canonize stays save-scoped so a new game is not polluted.
        counts = apply_canon_entries(db_path, entities or [], lore or [])
        discard_staged_source(info.get("staged_dir"))
        info["staged_dir"] = ""
        info["counts"] = counts
        info["applied"] = True
        info["scope"] = "save"
    return info


def apply_canonize_preview(staged_dir: str, src_dir: str, universe_db: str,
                           save_db: str | None = None) -> None:
    """Commit a previously previewed canonize sandbox (full world apply)."""
    from axiom.savestore import refresh_save_definition

    apply_staged_source(staged_dir, src_dir, universe_db)
    discard_staged_source(staged_dir)
    if save_db:
        refresh_save_definition(save_db)


def apply_canon_entries(target_db: str, entities: list, lore: list) -> dict:
    """Insert selected canon entries into a database (save or universe)."""
    from axiom.savestore import is_separated_save_db

    if is_separated_save_db(target_db):
        return _insert_session_canon(target_db, entities, lore)
    return _insert_canon(target_db, entities, lore)


def apply_canonize_selection(
    *,
    save_db: str,
    universe_db: str,
    entities: list,
    lore: list,
    scope: str = "save",
) -> dict:
    """Apply the player-picked subset.

    scope='save'  — this playthrough only (new games stay clean).
    scope='world' — write into the universe source + this save.
    """
    from axiom.library import sync_source_from_db
    from axiom.savestore import refresh_save_definition

    scope = (scope or "save").strip().lower()
    if scope == "world":
        if not universe_db:
            raise ValueError(_UAC_FOLDER_REQUIRED)
        counts = _insert_canon(universe_db, entities, lore)
        root = universe_root_for(universe_db)
        if root is not None:
            sync_source_from_db(universe_db, root)
        try:
            refresh_save_definition(save_db)
        except Exception:
            logger.warning("World canonize applied but save refresh failed", exc_info=True)
        counts["scope"] = "world"
        return counts

    counts = _insert_session_canon(save_db, entities, lore)
    counts["scope"] = "save"
    return counts
