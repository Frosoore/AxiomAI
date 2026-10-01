import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication
from mods.axiom.ui.qt.ui.widgets.chat_display import ChatDisplayWidget

def test_chat_display_user_message_renders_edit_link(qtbot):
    widget = ChatDisplayWidget()
    qtbot.addWidget(widget)
    
    widget.append_user_message("Hello World", turn_id=5)
    
    # Check that the text browser contains the edit link in its HTML
    html = widget._narrative_display.toHtml()
    assert "edit:user_input:5" in html
    assert "Hello World" in html

def test_chat_display_hero_intent_renders_edit_link(qtbot):
    widget = ChatDisplayWidget()
    qtbot.addWidget(widget)
    
    widget.append_hero_intent("Companion heals Kael", turn_id=6)
    
    html = widget._narrative_display.toHtml()
    assert "edit:hero_intent:6" in html
    assert "Companion heals Kael" in html

def test_chat_display_variants_nav_renders_edit_link(qtbot):
    widget = ChatDisplayWidget()
    qtbot.addWidget(widget)
    
    # Renders navigation with edit link
    widget.append_variants_nav(turn_id=7, active_index=0, total_variants=1, is_latest=True)
    
    html = widget._narrative_display.toHtml()
    assert "edit:narrative_text:7" in html

def test_chat_display_emits_edit_signal_on_link_click(qtbot):
    widget = ChatDisplayWidget()
    qtbot.addWidget(widget)
    
    signals = []
    widget.edit_message_requested.connect(lambda t, tid: signals.append((t, tid)))
    
    # Simulate clicking the edit link
    url = QUrl("edit:user_input:8")
    widget._on_link_clicked(url)
    
    assert len(signals) == 1
    assert signals[0] == ("user_input", 8)

def test_tabletop_view_chains_vector_rollback(qtbot, tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    from mods.axiom.ui.qt.ui.tabletop_view import TabletopView
    from axiom.memory import VectorMemory

    # Mock components to avoid heavy side-effects
    monkeypatch.setattr("mods.axiom.ui.qt.ui.tabletop_view.TabletopView.reload_llm", lambda self: None)
    monkeypatch.setattr("mods.axiom.ui.qt.ui.tabletop_view.load_rules_for_session", lambda *args, **kwargs: [])
    
    view = TabletopView(main_window=MagicMock())
    qtbot.addWidget(view)

    # Setup necessary fields
    view._vector_memory = MagicMock(spec=VectorMemory)
    view._vector_memory._disabled = False
    view._save_id = "test_save"
    view._db_path = str(tmp_path / "dummy.db")
    view._db_worker = MagicMock()
    view._arbitrator = MagicMock()
    
    # Spy on finalization
    finalize_called = []
    orig_finalize = view._finalize_rewind
    def wrapped_finalize(*args, **kwargs):
        finalize_called.append((args, kwargs))
        return orig_finalize(*args, **kwargs)
    monkeypatch.setattr(view, "_finalize_rewind", wrapped_finalize)
    
    # We trigger the slot directly with a summary dict
    summary = {"rebuilt_to_turn": 5}
    view._on_rewind_done(summary)
    
    # It should have started a VectorWorker
    assert view._vector_worker is not None
    
    # Wait for the worker to finish and trigger finalize
    qtbot.waitUntil(lambda: len(finalize_called) == 1, timeout=2000)
    
    # The worker should be cleaned up
    assert view._vector_worker is None

def test_tabletop_view_on_send_message_increments_turn_id_first(qtbot, tmp_path, monkeypatch):
    from unittest.mock import MagicMock
    from mods.axiom.ui.qt.ui.tabletop_view import TabletopView

    # Mock components to avoid side-effects
    monkeypatch.setattr("mods.axiom.ui.qt.ui.tabletop_view.TabletopView.reload_llm", lambda self: None)
    monkeypatch.setattr("mods.axiom.ui.qt.ui.tabletop_view.load_rules_for_session", lambda *args, **kwargs: [])
    monkeypatch.setattr("workers.narrative_worker.NarrativeWorker.start", lambda self: None)
    monkeypatch.setattr("mods.axiom.ui.qt.ui.tabletop_view.Session", MagicMock())
    
    view = TabletopView(main_window=MagicMock())
    qtbot.addWidget(view)
    
    # Initialize state
    view._turn_id = 0
    view._chat = MagicMock()
    view._db_worker = MagicMock()
    view._history = []
    view._db_path = str(tmp_path / "dummy.db")
    view._save_id = "test_save"
    
    view._on_send_message("My user action")
    
    # turn_id must be incremented before appending, so it should be 1
    assert view._turn_id == 1
    
    # append_user_message must have been called with turn_id = 1
    view._chat.append_user_message.assert_called_once_with("My user action", turn_id=1)
    
    # The history entry must have turn_id = 1
    assert len(view._history) == 1
    assert view._history[0]["turn_id"] == 1
    assert view._history[0]["event_type"] == "user_input"
    assert view._history[0]["payload"] == "My user action"


def test_chat_display_strips_json_on_rebuild(qtbot):
    widget = ChatDisplayWidget()
    qtbot.addWidget(widget)

    raw_text = (
        "Hello player!\n"
        "~~~\n"
        "You feel a cold breeze.\n"
        "~~~\n"
        "~~~json\n"
        "{\n"
        '  "state_changes": [],\n'
        '  "inventory_changes": [],\n'
        '  "narrative_events": ["'
    )

    history = [
        {
            "event_type": "narrative_text",
            "payload": raw_text,
            "turn_id": 1
        }
    ]

    widget.rebuild_from_history(history)
    html = widget._narrative_display.toHtml()

    assert "Hello player!" in html
    assert "You feel a cold breeze." in html
    assert "state_changes" not in html
    assert "inventory_changes" not in html
    assert "narrative_events" not in html
    assert "~~~json" not in html

