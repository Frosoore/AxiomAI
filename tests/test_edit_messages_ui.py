import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication
from ui.widgets.chat_display import ChatDisplayWidget

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
