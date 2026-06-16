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
    # NB (TICKET-026) : `parse_tool_call` est volontairement **résilient** — sur du JSON
    # malformé il ne lève PAS, il renvoie (texte, None) pour ne pas casser le tour. Ces
    # tests encodent ce contrat (ils attendaient `LLMParseError` avant ce changement).
    def test_invalid_json_returns_no_toolcall(self) -> None:
        """Malformed JSON inside the fence is tolerated: returns no tool call (None)."""
        raw = "Prose.\n~~~json\n{not valid json\n~~~"
        text, tool = LLMBackend.parse_tool_call(raw)
        assert tool is None

    def test_truncated_json_returns_no_toolcall(self) -> None:
        """Truncated/incomplete JSON inside the fence is tolerated: returns None."""
        raw = "Prose.\n~~~json\n{\"key\": \n~~~"
        text, tool = LLMBackend.parse_tool_call(raw)
        assert tool is None

    def test_unclosed_fence_repaired_successfully(self) -> None:
        """An unclosed fence with incomplete JSON is stripped from narrative and repaired."""
        raw = "Hello.\n~~~json\n{\"state_changes\": [], \"narrative_events\": [\"guild_intro"
        text, tool = LLMBackend.parse_tool_call(raw)
        assert text == "Hello."
        assert tool is not None
        assert tool["narrative_events"] == ["guild_intro"]

    def test_unclosed_raw_json_at_end_stripped_and_repaired(self) -> None:
        """Raw unclosed JSON object at the end of narrative is stripped and repaired."""
        raw = (
            "Nadine looks to you expectantly.\n\n"
            "{\n"
            "  \"state_changes\": [],\n"
            "  \"inventory_changes\": [],\n"
            "  \"narrative_events\": [\"guild_intro]\n"
        )
        text, tool = LLMBackend.parse_tool_call(raw)
        assert text == "Nadine looks to you expectantly."
        assert tool is not None
        assert tool["narrative_events"] == ["guild_intro]"]

    def test_malformed_json_stripped_even_if_unparseable(self) -> None:
        """Extremely malformed JSON that cannot be parsed/repaired is still stripped from narrative to avoid leaking."""
        raw = "Some story text.\n{\n  \"state_changes\": invalid syntax here"
        text, tool = LLMBackend.parse_tool_call(raw)
        assert text == "Some story text."
        assert tool is None


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


class TestTrimSentences:
    def test_trim_incomplete_sentence_helper(self) -> None:
        """Test _trim_incomplete_sentence with various inputs."""
        # Standard case: incomplete sentence at end
        t1 = "Nadine looks nervous. She points to a notice with neat handwriting. It pays 8 silver and the write-up says the area's safe—just watch out for wild"
        res1 = LLMResponse._trim_incomplete_sentence(t1)
        assert res1 == "Nadine looks nervous. She points to a notice with neat handwriting."

        # Case: already complete sentence
        t2 = "Nadine looks nervous. She points to a notice with neat handwriting."
        res2 = LLMResponse._trim_incomplete_sentence(t2)
        assert res2 == "Nadine looks nervous. She points to a notice with neat handwriting."

        # Dialogue quotes case
        t3 = "Nadine says, \"Hello Nadine! How are you doing?\" and then"
        res3 = LLMResponse._trim_incomplete_sentence(t3)
        assert res3 == "Nadine says, \"Hello Nadine! How are you doing?\""

        # Spanish/Inverted case or other punctuation
        t4 = "¡Hola Nadine! ¿Cómo estás? Me llamo Juan y"
        res4 = LLMResponse._trim_incomplete_sentence(t4)
        assert res4 == "¡Hola Nadine! ¿Cómo estás?"

        # Chinese / Japanese punctuation
        t5 = "彼女は微笑んだ。そして、手を伸ばして"
        res5 = LLMResponse._trim_incomplete_sentence(t5)
        assert res5 == "彼女は微笑んだ。"

    def test_arbitrator_trim_integration(self, monkeypatch) -> None:
        """Test that ArbitratorEngine._call_llm triggers trimming based on config and finish_reason/completeness."""
        from axiom.arbitrator import ArbitratorEngine
        from axiom.backends.base import LLMResponse, LLMBackend
        
        # Create a mock LLMBackend
        class FakeLLM(LLMBackend):
            def __init__(self, response):
                self.resp = response
                self.last_finish_reason = response.finish_reason
            def complete(self, *args, **kwargs):
                return self.resp
            def stream_tokens(self, *args, **kwargs):
                pass
            def is_available(self):
                return True
                
        # 1. trim_sentences = True, finish_reason = length
        class MockConfigTrue:
            trim_sentences = True
            
        monkeypatch.setattr("axiom.config.load_config", lambda: MockConfigTrue())
        
        raw_text = "Nadine looks nervous. She points to a notice with neat handwriting. It pays 8 silver and the write-up says the area's safe—just watch out for wild"
        
        # Test case A: finish_reason is length
        fake_llm = FakeLLM(LLMResponse(narrative_text=raw_text, tool_call=None, finish_reason="length"))
        arb = ArbitratorEngine(db_path=":memory:", rules_list=[])
        arb.configure(fake_llm, None)
        res = arb._call_llm(messages=[], stream_token_callback=None)
        assert res.narrative_text == "Nadine looks nervous. She points to a notice with neat handwriting."
        
        # Test case B: finish_reason is stop, but sentence is incomplete (should trim because it's incomplete)
        fake_llm = FakeLLM(LLMResponse(narrative_text=raw_text, tool_call=None, finish_reason="stop"))
        arb.configure(fake_llm, None)
        res = arb._call_llm(messages=[], stream_token_callback=None)
        assert res.narrative_text == "Nadine looks nervous. She points to a notice with neat handwriting."

        # Test case C: trim_sentences = False, finish_reason is length (should NOT trim)
        class MockConfigFalse:
            trim_sentences = False
        monkeypatch.setattr("axiom.config.load_config", lambda: MockConfigFalse())
        fake_llm = FakeLLM(LLMResponse(narrative_text=raw_text, tool_call=None, finish_reason="length"))
        arb.configure(fake_llm, None)
        res = arb._call_llm(messages=[], stream_token_callback=None)
        assert res.narrative_text == raw_text
