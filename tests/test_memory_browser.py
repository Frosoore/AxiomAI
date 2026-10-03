"""UI tests for the editable memory browser (facts + beliefs + models)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from axiom.schema import create_universe_db, get_connection
from core.localization import tr
from mods.axiom.living_memory.facts import Fact, get_fact, insert_facts
from mods.axiom.living_memory.observations import Observation, insert_observation
from mods.axiom.living_memory.ui.memory_browser import MemoryBrowserDialog


@pytest.fixture
def db_path() -> str:
    with tempfile.TemporaryDirectory() as d:
        path = str(Path(d) / "universe.db")
        create_universe_db(path)
        with get_connection(path) as conn:
            conn.execute(
                "INSERT INTO Saves (save_id, player_name, difficulty, last_updated) "
                "VALUES (?, ?, ?, ?);", ("s1", "Hero", "Normal", "2026-06-19"))
            conn.commit()
        yield path


def test_no_session_shows_notice(qtbot) -> None:
    dialog = MemoryBrowserDialog(None, None, None)
    qtbot.addWidget(dialog)
    from PySide6.QtWidgets import QTableWidget
    assert dialog.findChildren(QTableWidget) == []
    assert dialog.windowTitle() == tr("memory_browser_title")


def test_lists_beliefs_with_trend_and_facts(qtbot, db_path: str) -> None:
    insert_facts(db_path, "s1", 3, [
        Fact(statement="Kael swore an oath", fact_type="experience",
             who="Kael", entities=["Kael"]),
    ])
    insert_observation(db_path, "s1", Observation(
        statement="The smith holds an old debt", subject="Smith",
        sources=[{"fact_id": 1, "turn_id": 5}], created_turn_id=5, updated_turn_id=5))

    dialog = MemoryBrowserDialog(db_path, "s1", now_turn=100)
    qtbot.addWidget(dialog)

    from PySide6.QtWidgets import QTableWidget
    tables = dialog.findChildren(QTableWidget)
    assert len(tables) == 3  # models + beliefs + facts
    beliefs_table = dialog._beliefs_table
    facts_table = dialog._facts_table

    assert beliefs_table.rowCount() == 1
    assert beliefs_table.item(0, 0).text() == "Smith"
    assert beliefs_table.item(0, 1).text() == "The smith holds an old debt"
    assert beliefs_table.item(0, 2).text() == tr("trend_stale")

    assert facts_table.rowCount() == 1
    assert facts_table.item(0, 2).text() == "Kael swore an oath"
    assert facts_table.item(0, 3).text() == "Kael"


def test_world_belief_shown_with_world_label(qtbot, db_path: str) -> None:
    insert_observation(db_path, "s1", Observation(
        statement="The city is on edge", subject="",
        sources=[{"fact_id": 1, "turn_id": 6}], created_turn_id=6, updated_turn_id=6))
    dialog = MemoryBrowserDialog(db_path, "s1", now_turn=8)
    qtbot.addWidget(dialog)
    assert dialog._beliefs_table.item(0, 0).text() == tr("memory_browser_world")


def test_edit_fact_via_engine_reload(qtbot, db_path: str) -> None:
    """Sanity: after engine update_fact, refresh shows new text."""
    from mods.axiom.living_memory.facts import update_fact

    ids = insert_facts(db_path, "s1", 1, [Fact(statement="Old text", entities=[])])
    fid = ids[0]
    dialog = MemoryBrowserDialog(db_path, "s1", now_turn=1)
    qtbot.addWidget(dialog)
    assert dialog._facts_table.item(0, 2).text() == "Old text"

    assert update_fact(db_path, "s1", fid, statement="Corrected text") is True
    dialog._reload_all()
    assert dialog._facts_table.item(0, 2).text() == "Corrected text"
    assert get_fact(db_path, "s1", fid).statement == "Corrected text"
