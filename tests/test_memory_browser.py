"""tests/test_memory_browser.py

UI tests for the read-only memory browser (beliefs + facts viewer, TICKET-081).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from axiom.facts import Fact, insert_facts
from axiom.observations import Observation, insert_observation
from axiom.schema import create_universe_db, get_connection
from core.localization import tr
from ui.memory_browser import MemoryBrowserDialog


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
    # No session → no tables, just the "load a game" notice + close button.
    from PySide6.QtWidgets import QTableWidget
    assert dialog.findChildren(QTableWidget) == []
    assert dialog.windowTitle() == tr("memory_browser_title")


def test_lists_beliefs_with_trend_and_facts(qtbot, db_path: str) -> None:
    insert_facts(db_path, "s1", 3, [
        Fact(statement="Kael swore an oath", fact_type="experience",
             who="Kael", entities=["Kael"]),
    ])
    # A belief whose only evidence is far in the past → stale at turn 100.
    insert_observation(db_path, "s1", Observation(
        statement="The smith holds an old debt", subject="Smith",
        sources=[{"fact_id": 1, "turn_id": 5}], created_turn_id=5, updated_turn_id=5))

    dialog = MemoryBrowserDialog(db_path, "s1", now_turn=100)
    qtbot.addWidget(dialog)

    from PySide6.QtWidgets import QTableWidget
    tables = dialog.findChildren(QTableWidget)
    assert len(tables) == 2  # beliefs + facts
    # findChildren order is not guaranteed; tell them apart by column count
    # (beliefs = 5 columns, facts = 4).
    beliefs_table = next(t for t in tables if t.columnCount() == 5)
    facts_table = next(t for t in tables if t.columnCount() == 4)

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
    from PySide6.QtWidgets import QTableWidget
    beliefs_table = dialog.findChildren(QTableWidget)[0]
    assert beliefs_table.item(0, 0).text() == tr("memory_browser_world")
