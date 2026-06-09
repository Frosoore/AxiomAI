"""tests/test_ticket_fixes.py

Couverture des correctifs TICKET-006 / TICKET-023 / TICKET-024 (session 2026-06-09).

- TICKET-006 : les events `chronicler_update` se matérialisent dans State_Cache.
- TICKET-023 : `Universe.load` lit la clé canonique `universe_name`.
- TICKET-024 : `Active_Modifiers` est isolé par `save_id` (plus de fuite entre saves).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from axiom.compile import compile_universe
from axiom.db_helpers import create_new_save
from axiom.events import EventSourcer
from axiom.modifiers import ModifierProcessor
from axiom.schema import create_universe_db, get_connection, migrate_active_modifiers_table
from axiom.universe import Universe


def _new_db(tmp_path: Path) -> str:
    db = str(tmp_path / "u.db")
    create_universe_db(db)
    with get_connection(db) as conn:
        conn.execute(
            "INSERT INTO Entities (entity_id, entity_type, name) VALUES ('e1', 'npc', 'NPC');"
        )
        conn.commit()
    return db


# ---------------------------------------------------------------------------
# TICKET-006 — chronicler_update matérialisé
# ---------------------------------------------------------------------------

def test_chronicler_update_materializes_on_rebuild(tmp_path: Path):
    db = _new_db(tmp_path)
    save_id = create_new_save(db, "Hero", "Normal")
    es = EventSourcer(db)
    es.append_event(save_id, 1, "chronicler_update", "e1",
                    {"entity_id": "e1", "stat_key": "Gold", "value": "50"})
    es.append_event(save_id, 2, "chronicler_update", "e1",
                    {"entity_id": "e1", "stat_key": "Gold", "delta": 25})
    es.rebuild_state_cache(save_id)
    assert es.get_current_stats(save_id, "e1")["Gold"] == "75"


def test_chronicler_update_incremental_cache(tmp_path: Path):
    db = _new_db(tmp_path)
    save_id = create_new_save(db, "Hero", "Normal")
    es = EventSourcer(db)
    batch = [(save_id, 1, "chronicler_update", "e1",
              {"entity_id": "e1", "stat_key": "Reputation", "value": "10"})]
    es.append_events_batch(batch)
    es.update_state_cache(save_id, batch)
    assert es.get_current_stats(save_id, "e1")["Reputation"] == "10"


def test_chronicler_update_in_state_at(tmp_path: Path):
    db = _new_db(tmp_path)
    save_id = create_new_save(db, "Hero", "Normal")
    es = EventSourcer(db)
    es.append_event(save_id, 1, "chronicler_update", "e1",
                    {"entity_id": "e1", "stat_key": "Mood", "value": "Calm"})
    assert es.state_at(save_id)["e1"]["Mood"] == "Calm"


# ---------------------------------------------------------------------------
# TICKET-023 — Universe.load lit universe_name
# ---------------------------------------------------------------------------

def test_universe_load_uses_universe_name(tmp_path: Path):
    root = tmp_path / "src"
    (root).mkdir()
    (root / "universe.toml").write_text('[meta]\nname = "Drakthar"\n', encoding="utf-8")
    db = compile_universe(root)  # cache nommé universe.db
    assert Universe.load(str(db)).name == "Drakthar"  # pas "universe" (stem)


def test_universe_load_falls_back_to_stem(tmp_path: Path):
    """Sans universe_name ni name, on retombe sur le stem du fichier."""
    db = str(tmp_path / "Myria.db")
    create_universe_db(db)
    assert Universe.load(db).name == "Myria"


# ---------------------------------------------------------------------------
# TICKET-024 — Active_Modifiers isolé par save_id
# ---------------------------------------------------------------------------

def test_modifiers_isolated_between_saves(tmp_path: Path):
    db = _new_db(tmp_path)
    s1 = create_new_save(db, "A", "Normal")
    s2 = create_new_save(db, "B", "Normal")
    mp = ModifierProcessor(db)
    mp.add_modifier(s1, "e1", "HP", -10.0, 5)

    assert mp.apply_modifiers(s1, "e1", {"HP": "100"})["HP"] == "90"
    assert mp.apply_modifiers(s2, "e1", {"HP": "100"})["HP"] == "100"  # isolé


def test_modifier_tick_scoped_to_save(tmp_path: Path):
    db = _new_db(tmp_path)
    s1 = create_new_save(db, "A", "Normal")
    s2 = create_new_save(db, "B", "Normal")
    mp = ModifierProcessor(db)
    mid1 = mp.add_modifier(s1, "e1", "HP", -10.0, 1)
    mp.add_modifier(s2, "e1", "HP", -5.0, 5)

    expired = mp.tick_modifiers(s1, elapsed_minutes=1)
    assert expired == [mid1]                                  # seul s1 a expiré
    assert mp.apply_modifiers(s2, "e1", {"HP": "100"})["HP"] == "95"  # s2 intact


def test_modifier_stored_with_save_id(tmp_path: Path):
    db = _new_db(tmp_path)
    s1 = create_new_save(db, "A", "Normal")
    mp = ModifierProcessor(db)
    mid = mp.add_modifier(s1, "e1", "HP", -3.0, 2)
    with get_connection(db) as conn:
        row = conn.execute(
            "SELECT save_id FROM Active_Modifiers WHERE modifier_id = ?;", (mid,)
        ).fetchone()
    assert row[0] == s1


def test_migrate_active_modifiers_adds_column(tmp_path: Path):
    """Une table legacy sans save_id reçoit la colonne via migration (idempotent)."""
    db = str(tmp_path / "legacy.db")
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE Active_Modifiers ("
            "modifier_id TEXT PRIMARY KEY, entity_id TEXT, stat_key TEXT, "
            "delta REAL, minutes_remaining INTEGER);"
        )
        conn.commit()
    migrate_active_modifiers_table(db)
    migrate_active_modifiers_table(db)  # idempotent
    with sqlite3.connect(db) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(Active_Modifiers);")}
    assert "save_id" in cols
