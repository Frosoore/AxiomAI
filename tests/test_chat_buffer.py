"""
tests/test_chat_buffer.py

Verifies ChatDisplayWidget's streaming token buffer: it must hold back text
that could be the start of a ``~~~json`` tool-call fence, hide completed fences
entirely, and flush any leftover partial fence on demand.
"""

import os
import pytest
from PySide6.QtWidgets import QApplication
from mods.axiom.ui.qt.ui.widgets.chat_display import ChatDisplayWidget

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


def test_image_placeholder_shows_and_clears(qapp):
    """show_image_placeholder inserts the vignette; clear removes it while
    keeping the narrative that preceded it."""
    from core.localization import tr
    widget = ChatDisplayWidget()
    widget.append_token("Scene narrative.")
    widget.flush_final_buffer()

    widget.show_image_placeholder()
    label = tr("generating_image")
    assert label in widget._narrative_display.toPlainText()
    assert widget._img_placeholder_range is not None
    # A second call is a no-op (no duplicate vignette).
    widget.show_image_placeholder()

    widget.clear_image_placeholder()
    text = widget._narrative_display.toPlainText()
    assert label not in text
    assert "Scene narrative." in text
    assert widget._img_placeholder_range is None


def test_image_placeholder_preserves_text_flushed_after_it(qapp):
    """The final buffer flush can append narrative AFTER the placeholder; clearing
    the placeholder must not eat that text."""
    from core.localization import tr
    widget = ChatDisplayWidget()
    widget.show_image_placeholder()
    # Simulate a late flush landing at the document end (after the placeholder).
    widget._insert_instant_parsed_text("Tail text.")

    widget.clear_image_placeholder()
    text = widget._narrative_display.toPlainText()
    assert "Tail text." in text
    assert tr("generating_image") not in text


def test_append_image_clears_pending_placeholder(qapp):
    """append_image drops any pending 'generating…' vignette (even with no file)."""
    from core.localization import tr
    widget = ChatDisplayWidget()
    widget.show_image_placeholder()
    assert widget._img_placeholder_range is not None

    # Non-existent path: append_image returns early but must still clear.
    widget.append_image("/nonexistent/turn_999.png")
    assert widget._img_placeholder_range is None
    assert tr("generating_image") not in widget._narrative_display.toPlainText()


def test_chat_auto_scroll_follows_streaming_when_at_bottom(qapp):
    """When the user is at the bottom of the chat, incoming LLM tokens auto-scroll to bottom."""
    widget = ChatDisplayWidget()
    widget.resize(300, 200)
    widget.show()
    sb = widget._narrative_display.verticalScrollBar()

    # Stream enough lines so the document overflows and creates a scroll range
    for i in range(50):
        widget.append_token(f"Line {i} of streaming narrative text.\n")
    widget.flush_final_buffer()

    assert sb.maximum() > 0
    assert widget.is_at_bottom() is True
    assert sb.value() == sb.maximum()


def test_chat_auto_scroll_disabled_when_user_scrolled_up(qapp):
    """When the user scrolls up, auto-scroll is disabled and user position is preserved."""
    widget = ChatDisplayWidget()
    widget.resize(300, 200)
    widget.show()
    sb = widget._narrative_display.verticalScrollBar()

    for i in range(50):
        widget.append_token(f"Line {i} of streaming narrative text.\n")
    widget.flush_final_buffer()

    initial_max = sb.maximum()
    assert initial_max > 100

    # User scrolls up to view older lines
    user_pos = 50
    sb.setValue(user_pos)
    assert widget.is_at_bottom() is False
    assert widget._auto_scroll is False

    # New LLM tokens arrive while user is reading above
    for i in range(50, 80):
        widget.append_token(f"New line {i} streaming from LLM.\n")
    widget.flush_final_buffer()

    # The maximum grew, but user's scroll position was NOT forced down
    assert sb.maximum() > initial_max
    assert sb.value() == user_pos
    assert widget._auto_scroll is False


def test_chat_auto_scroll_reenabled_when_user_scrolls_back_to_bottom(qapp):
    """Scrolling back to bottom manually re-enables auto-scroll for subsequent tokens."""
    widget = ChatDisplayWidget()
    widget.resize(300, 200)
    widget.show()
    sb = widget._narrative_display.verticalScrollBar()

    for i in range(40):
        widget.append_token(f"Line {i} of narrative.\n")
    widget.flush_final_buffer()

    # Scroll up -> disabled
    sb.setValue(20)
    assert widget._auto_scroll is False

    # Scroll back down -> re-enabled
    sb.setValue(sb.maximum())
    assert widget.is_at_bottom() is True
    assert widget._auto_scroll is True

    # Next tokens follow the bottom
    for i in range(40, 60):
        widget.append_token(f"Subsequent line {i}.\n")
    widget.flush_final_buffer()

    assert sb.value() == sb.maximum()
    assert widget._auto_scroll is True


def test_append_user_message_forces_scroll_to_bottom(qapp):
    """Submitting a user message forces scrolling to bottom and re-enables auto-scroll."""
    widget = ChatDisplayWidget()
    widget.resize(300, 200)
    widget.show()
    sb = widget._narrative_display.verticalScrollBar()

    for i in range(40):
        widget.append_token(f"Line {i} of narrative.\n")
    widget.flush_final_buffer()

    # User scrolled up
    sb.setValue(10)
    assert widget._auto_scroll is False

    # User posts a new action
    widget.append_user_message("I explore the dark hallway.")
    assert sb.value() == sb.maximum()
    assert widget._auto_scroll is True

