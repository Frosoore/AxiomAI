"""
tests/test_chat_buffer.py

Verifies ChatDisplayWidget's streaming token buffer: it must hold back text
that could be the start of a ``~~~json`` tool-call fence, hide completed fences
entirely, and flush any leftover partial fence on demand.
"""

import os
import pytest
from PySide6.QtWidgets import QApplication
from ui.widgets.chat_display import ChatDisplayWidget

# Ensure we can run without a display
os.environ["QT_QPA_PLATFORM"] = "offscreen"

@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app

def test_partial_json_fence_is_buffered_until_flushed(qapp):
    """A token that is only a prefix of '~~~json' stays hidden in the buffer;
    flush_final_buffer then reveals it once no real fence ever completed."""
    widget = ChatDisplayWidget()

    # 1. Test partial JSON fence suppression
    # The string "~~~j" should stay in buffer because it's a prefix of "~~~json"
    widget.append_token("Hello ")
    widget.append_token("~~~j")
    
    # "Hello " should be visible, "~~~j" should be buffered
    assert "Hello" in widget._narrative_display.toPlainText()
    assert "~~~j" not in widget._narrative_display.toPlainText()
    assert widget._token_buf == "~~~j"

    # 2. Test final flush
    # flush_final_buffer should force the buffered "~~~j" to appear 
    # (since it never completed into a real fence)
    widget.flush_final_buffer()
    assert "Hello ~~~j" in widget._narrative_display.toPlainText()
    assert widget._token_buf == ""

def test_completed_json_fence_is_stripped_from_narrative(qapp):
    """A fully-formed '~~~json ... ~~~' block is removed from the visible
    narrative while the surrounding prose stays intact."""
    widget = ChatDisplayWidget()

    # Send tokens including a full JSON block
    widget.append_token("Narrative start. ")
    widget.append_token("~~~json\n{\"key\": \"val\"}\n~~~")
    widget.append_token(" Narrative end.")
    
    text = widget._narrative_display.toPlainText()
    assert "Narrative start." in text
    assert "Narrative end." in text
    assert "{\"key\"" not in text
    assert "~~~json" not in text


def test_backtick_json_fence_is_stripped_from_narrative(qapp):
    """Models often emit ```json despite the prompt asking for ~~~json — the
    streamed block must be hidden too (the engine parser already strips it)."""
    widget = ChatDisplayWidget()

    widget.append_token("The hero advances. ")
    widget.append_token("```json\n{\"tool\": \"update_stats\", \"value\": 3}\n```")
    widget.append_token(" The dust settles around them.")

    text = widget._narrative_display.toPlainText()
    assert "The hero advances." in text
    assert "The dust settles" in text
    assert "update_stats" not in text
    assert "```" not in text


def test_backtick_fence_streamed_char_by_char(qapp):
    """Same as above but token-by-token, as during a real stream."""
    widget = ChatDisplayWidget()

    payload = "Before.\n```json\n{\"a\": 1}\n```\nAfter. Plus enough padding to flush."
    for ch in payload:
        widget.append_token(ch)
    widget.flush_final_buffer()

    text = widget._narrative_display.toPlainText()
    assert "Before." in text
    assert "After." in text
    assert "{\"a\": 1}" not in text
    assert "```" not in text


def test_partial_backtick_fence_is_buffered_until_flushed(qapp):
    """A trailing '```j' could become '```json' — held back, then revealed by
    the final flush if no real fence ever completed."""
    widget = ChatDisplayWidget()

    widget.append_token("Hello ")
    widget.append_token("```j")
    assert "```j" not in widget._narrative_display.toPlainText()

    widget.flush_final_buffer()
    assert "Hello ```j" in widget._narrative_display.toPlainText()
