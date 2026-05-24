"""
tests/test_llm_base.py

Unit tests for llm_engine/base.py — covers parse_tool_call() and the
LLMBackend abstract interface.  No network calls; no mocking needed
(base.py is pure Python with no I/O).
"""

import pytest

from axiom.backends.base import (
    LLMBackend,
    LLMConnectionError,
    LLMMessage,
    LLMParseError,
    LLMResponse,
)


# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing the ABC
# ---------------------------------------------------------------------------

class _StubBackend(LLMBackend):
    """Minimal concrete implementation used only to verify instantiation."""

    def complete(self, messages, stream=False) -> LLMResponse:
        return LLMResponse(narrative_text="ok", tool_call=None, finish_reason="stop")

    def stream_tokens(self, messages):
        yield "ok"

    def is_available(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# LLMResponse dataclass
# ---------------------------------------------------------------------------

class TestLLMResponse:
    def test_fields_accessible(self) -> None:
        """LLMResponse exposes narrative_text, tool_call and finish_reason."""
        r = LLMResponse(narrative_text="Hello", tool_call={"x": 1}, finish_reason="stop")
        assert r.narrative_text == "Hello"
        assert r.tool_call == {"x": 1}
        assert r.finish_reason == "stop"

    def test_tool_call_none(self) -> None:
        """tool_call may be None for a pure-prose response."""
        r = LLMResponse(narrative_text="prose", tool_call=None, finish_reason="stop")
        assert r.tool_call is None


# ---------------------------------------------------------------------------
# LLMBackend ABC enforcement
# ---------------------------------------------------------------------------

class TestLLMBackendABC:
    def test_cannot_instantiate_abstract_class(self) -> None:
        """LLMBackend is abstract — instantiating it directly raises TypeError."""
        with pytest.raises(TypeError):
            LLMBackend()  # type: ignore[abstract]

    def test_concrete_subclass_instantiates(self) -> None:
        """A subclass implementing all abstract methods can be instantiated."""
        backend = _StubBackend()
        assert backend.is_available() is True

    def test_concrete_complete_returns_llm_response(self) -> None:
        """A concrete backend's complete() returns an LLMResponse."""
        backend = _StubBackend()
        result = backend.complete([])
        assert isinstance(result, LLMResponse)

    def test_concrete_stream_tokens_yields_strings(self) -> None:
        """A concrete backend's stream_tokens() yields string tokens."""
        backend = _StubBackend()
        tokens = list(backend.stream_tokens([]))
        assert all(isinstance(t, str) for t in tokens)


# ---------------------------------------------------------------------------
# parse_tool_call — happy paths
# ---------------------------------------------------------------------------

class TestParseToolCall:
    def test_no_tool_call_returns_full_text(self) -> None:
        """Raw text with no fenced JSON returns (full stripped text, None)."""
        raw = "The dragon roars and attacks the knight."
        narrative, tool_call = LLMBackend.parse_tool_call(raw)
        assert narrative == raw.strip()
        assert tool_call is None

    def test_extracts_json_block(self) -> None:
        """A fenced ~~~json block is parsed into tool_call and stripped from
        the returned narrative."""
        raw = (
            "The knight takes damage.\n\n"
            "~~~json\n"
            '{"state_changes": [{"entity_id": "knight", "stat_key": "HP", "delta": -10}]}\n'
            "~~~"
        )
        narrative, tool_call = LLMBackend.parse_tool_call(raw)
        assert "~~~json" not in narrative
        assert "~~~" not in narrative
        assert tool_call is not None
        assert tool_call["state_changes"][0]["delta"] == -10

    def test_narrative_whitespace_collapsed(self) -> None:
        """Surrounding whitespace is trimmed from the extracted narrative."""
        raw = "  Some prose.  \n\n~~~json\n{}\n~~~\n\n  "
        narrative, _ = LLMBackend.parse_tool_call(raw)
        assert narrative == "Some prose."

    def test_empty_json_object(self) -> None:
        """An empty ~~~json {} block parses to an empty dict, not None."""
        raw = "Prose.\n~~~json\n{}\n~~~"
        narrative, tool_call = LLMBackend.parse_tool_call(raw)
        assert tool_call == {}
        assert narrative == "Prose."

    def test_tool_call_with_narrative_events(self) -> None:
        """A narrative_events array inside the tool-call JSON is preserved."""
        raw = (
            "A cataclysm strikes the realm.\n"
            "~~~json\n"
            '{"state_changes": [], "narrative_events": ["cataclysm"]}\n'
            "~~~"
        )
        _, tool_call = LLMBackend.parse_tool_call(raw)
        assert tool_call["narrative_events"] == ["cataclysm"]

    def test_multiline_narrative_preserved(self) -> None:
        """Multi-line prose before the JSON fence keeps all its lines."""
        raw = "Line one.\nLine two.\n~~~json\n{}\n~~~"
        narrative, _ = LLMBackend.parse_tool_call(raw)
        assert "Line one." in narrative
        assert "Line two." in narrative

    def test_json_block_inline_spacing(self) -> None:
        """~~~json and ~~~ on the same line as content should still parse."""
        raw = "Prose.\n~~~json\n  {\"k\": \"v\"}  \n~~~"
        _, tool_call = LLMBackend.parse_tool_call(raw)
        assert tool_call == {"k": "v"}

    def test_empty_raw_string(self) -> None:
        """An empty input returns ('', None)."""
        narrative, tool_call = LLMBackend.parse_tool_call("")
        assert narrative == ""
        assert tool_call is None


# ---------------------------------------------------------------------------
# parse_tool_call — error paths
# ---------------------------------------------------------------------------

class TestParseToolCallErrors:
    def test_invalid_json_raises_parse_error(self) -> None:
        """Malformed JSON inside the fence raises LLMParseError."""
        raw = "Prose.\n~~~json\n{not valid json\n~~~"
        with pytest.raises(LLMParseError, match="Failed to parse tool-call JSON block"):
            LLMBackend.parse_tool_call(raw)

    def test_truncated_json_raises_parse_error(self) -> None:
        """Truncated/incomplete JSON inside the fence raises LLMParseError."""
        raw = "Prose.\n~~~json\n{\"key\": \n~~~"
        with pytest.raises(LLMParseError):
            LLMBackend.parse_tool_call(raw)


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class TestExceptions:
    def test_llm_connection_error_is_exception(self) -> None:
        """LLMConnectionError is an Exception that carries its message."""
        exc = LLMConnectionError("server down")
        assert isinstance(exc, Exception)
        assert "server down" in str(exc)

    def test_llm_parse_error_is_exception(self) -> None:
        """LLMParseError is an Exception subclass."""
        exc = LLMParseError("bad json")
        assert isinstance(exc, Exception)

    def test_exceptions_are_distinct(self) -> None:
        """Connection and parse errors are unrelated types (neither subclasses
        the other), so callers can catch them separately."""
        assert not issubclass(LLMConnectionError, LLMParseError)
        assert not issubclass(LLMParseError, LLMConnectionError)
