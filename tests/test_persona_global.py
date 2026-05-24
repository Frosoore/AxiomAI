"""
tests/test_persona_global.py

Round-trip test for global personas (stored in the shared global.db, not a
per-universe db): save personas via DbWorker, confirm they reach
Global_Personas, then load them back through the personas_loaded signal.
"""

import sqlite3
import pytest
from axiom.schema import create_global_db
from workers.db_worker import DbWorker

@pytest.fixture
def global_db_path(tmp_path):
    path = str(tmp_path / "global.db")
    create_global_db(path)
    return path

def test_global_personas_survive_save_then_load_round_trip(global_db_path):
    """Personas saved via save_global_personas are persisted to Global_Personas
    and returned unchanged by a subsequent load_global_personas."""
    # 1. Setup personas to save
    personas = [
        {"persona_id": "p1", "name": "Mercenary", "description": "A battle-hardened soldier."},
        {"persona_id": "p2", "name": "Scholar", "description": "A seeker of ancient knowledge."}
    ]

    # 2. Save via DbWorker
    from PySide6.QtCore import QCoreApplication, Qt
    import time
    done = []
    worker = DbWorker(global_db_path)
    worker.save_complete.connect(lambda: done.append(True), Qt.QueuedConnection)
    worker.save_global_personas(personas)
    
    start = time.time()
    while not done and time.time() - start < 5:
        QCoreApplication.processEvents()
        time.sleep(0.01)

    # 3. Verify in DB directly
    with sqlite3.connect(global_db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM Global_Personas ORDER BY persona_id").fetchall()
        assert len(rows) == 2
        assert rows[0]["name"] == "Mercenary"
        assert rows[1]["description"] == "A seeker of ancient knowledge."

    # 4. Load via DbWorker
    loaded_personas = []
    def on_personas_loaded(data):
        loaded_personas.extend(data)
    
    from PySide6.QtCore import Qt
    done2 = []
    worker.save_complete.connect(lambda: done2.append(True), Qt.QueuedConnection)
    worker.personas_loaded.connect(on_personas_loaded, Qt.QueuedConnection)
    worker.load_global_personas()
    
    start = time.time()
    while not done2 and time.time() - start < 5:
        QCoreApplication.processEvents()
        time.sleep(0.01)

    assert len(loaded_personas) == 2
    assert loaded_personas[0]["persona_id"] == "p1"
    assert loaded_personas[1]["name"] == "Scholar"
