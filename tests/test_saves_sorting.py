import pytest
from PySide6.QtCore import Qt
from ui.setup_view import SetupView

def test_saves_sorting_by_last_updated_and_creation_date(qtbot):
    # Instantiate SetupView
    view = SetupView(main_window=None)
    qtbot.addWidget(view)

    # Prepare dummy saves
    # Save 1: Created first, but updated last (most recent update)
    # Save 2: Created second, updated second
    # Save 3: Created third (most recent creation), updated first (oldest update)
    saves = [
        {
            "save_id": "save_1",
            "player_name": "Alice",
            "difficulty": "Normal",
            "created_at": "2026-06-20T10:00:00",
            "last_updated": "2026-06-20T18:00:00"
        },
        {
            "save_id": "save_2",
            "player_name": "Bob",
            "difficulty": "Hardcore",
            "created_at": "2026-06-20T11:00:00",
            "last_updated": "2026-06-20T17:00:00"
        },
        {
            "save_id": "save_3",
            "player_name": "Charlie",
            "difficulty": "Companion",
            "created_at": "2026-06-20T12:00:00",
            "last_updated": "2026-06-20T16:00:00"
        }
    ]

    # Load saves into view
    view._on_saves_loaded(saves)

    # 1. Default sorting: Last Updated (Descending)
    # Expected order: save_1 (18:00), save_2 (17:00), save_3 (16:00)
    assert view._saves_list.count() == 3
    assert view._saves_list.item(0).data(Qt.UserRole)["save_id"] == "save_1"
    assert view._saves_list.item(1).data(Qt.UserRole)["save_id"] == "save_2"
    assert view._saves_list.item(2).data(Qt.UserRole)["save_id"] == "save_3"

    # Verify formatting of the item texts (contains both dates)
    assert view._saves_list.item(0).text() == "Alice (Normal) - Last Updated: 2026-06-20 18:00 | Creation Date: 2026-06-20 10:00"
    assert view._saves_list.item(1).text() == "Bob (Hardcore) - Last Updated: 2026-06-20 17:00 | Creation Date: 2026-06-20 11:00"
    assert view._saves_list.item(2).text() == "Charlie (Companion) - Last Updated: 2026-06-20 16:00 | Creation Date: 2026-06-20 12:00"

    # 2. Switch sorting to: Creation Date (Descending)
    # Expected order: save_3 (12:00), save_2 (11:00), save_1 (10:00)
    creation_index = view._sort_combo.findData("created_at")
    assert creation_index != -1
    view._sort_combo.setCurrentIndex(creation_index)

    assert view._saves_list.count() == 3
    assert view._saves_list.item(0).data(Qt.UserRole)["save_id"] == "save_3"
    assert view._saves_list.item(1).data(Qt.UserRole)["save_id"] == "save_2"
    assert view._saves_list.item(2).data(Qt.UserRole)["save_id"] == "save_1"

    # 3. Switch back to: Last Updated
    updated_index = view._sort_combo.findData("last_updated")
    view._sort_combo.setCurrentIndex(updated_index)

    assert view._saves_list.item(0).data(Qt.UserRole)["save_id"] == "save_1"
    assert view._saves_list.item(1).data(Qt.UserRole)["save_id"] == "save_2"
    assert view._saves_list.item(2).data(Qt.UserRole)["save_id"] == "save_3"

    # 4. Verify timezone-aware date formatting (converts UTC to local)
    from datetime import datetime
    s_tz = {
        "save_id": "save_tz",
        "player_name": "TzTest",
        "difficulty": "Normal",
        "created_at": "2026-06-20T10:00:00+00:00",
        "last_updated": "2026-06-20T18:00:00+00:00"
    }
    view._on_saves_loaded([s_tz])
    expected_created = datetime.fromisoformat("2026-06-20T10:00:00+00:00").astimezone().strftime("%Y-%m-%d %H:%M")
    expected_updated = datetime.fromisoformat("2026-06-20T18:00:00+00:00").astimezone().strftime("%Y-%m-%d %H:%M")
    assert expected_created in view._saves_list.item(0).text()
    assert expected_updated in view._saves_list.item(0).text()


def test_resolve_tick_updates_last_updated(tmp_path):
    from pathlib import Path
    from axiom.compile import compile_universe
    from axiom.db_helpers import create_new_save
    from axiom.session import Session
    from axiom.schema import get_connection
    from unittest.mock import MagicMock

    root = tmp_path / "src"
    root.mkdir(parents=True, exist_ok=True)
    (root / "universe.toml").write_text('[meta]\nname = "Test"\n[narrative]\nsystem_prompt = "GM."\n')
    (root / "entities").mkdir(parents=True, exist_ok=True)
    (root / "entities" / "player_1.toml").write_text(
        'entity_id = "player_1"\nentity_type = "player"\nname = "Hero"\n[stats]\nHealth = "100"\n'
    )
    
    db_path = str(compile_universe(root, tmp_path / "u.db"))
    save_id = create_new_save(db_path, "Hero", "Normal")
    
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT last_updated FROM Saves WHERE save_id = ?;", (save_id,)).fetchone()
        orig_last_updated = row["last_updated"]
        
    session = Session(db_path, save_id, llm=MagicMock())
    session._arbitrator = MagicMock()
    mock_result = MagicMock()
    mock_result.elapsed_minutes = 10
    mock_result.narrative_text = "Turn done."
    mock_result.game_state_tag = "normal"
    session._arbitrator.process_turn.return_value = mock_result
    
    session.submit_intent("player_1", "I walk north.")
    session.resolve_tick()
    
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT last_updated FROM Saves WHERE save_id = ?;", (save_id,)).fetchone()
        new_last_updated = row["last_updated"]
        
    assert new_last_updated != orig_last_updated
    assert "+" in new_last_updated or "Z" in new_last_updated

