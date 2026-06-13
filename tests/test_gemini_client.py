"""
tests/test_gemini_client.py

Unit tests for llm_engine/gemini_client.py.

The google.genai SDK is mocked entirely — no real API calls are made.
We patch the client instance created inside GeminiClient.__init__.
"""

from unittest.mock import MagicMock, patch, PropertyMock
from typing import Iterator

import pytest

from axiom.backends.base import LLMConnectionError, LLMParseError, LLMResponse
from axiom.backends.gemini import GeminiClient


# ---------------------------------------------------------------------------
# Helpers — fake SDK objects
# ---------------------------------------------------------------------------

def _make_response(text: str, finish_reason_str: str = "STOP") -> MagicMock:
    """Build a mock GenerateContentResponse."""
    mock_resp = MagicMock()
    mock_resp.text = text

    candidate = MagicMock()
    candidate.finish_reason = finish_reason_str
    mock_resp.candidates = [candidate]
    return mock_resp


def _make_streaming_chunks(tokens: list[str]) -> list[MagicMock]:
    chunks = []
    for token in tokens:
        chunk = MagicMock()
        chunk.text = token
        chunks.append(chunk)
    return chunks


# ---------------------------------------------------------------------------
# Fixture: patch genai.Client at instantiation
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_client_cls():
    """Patch google.genai.Client so no real HTTP client is created."""
    with patch("axiom.backends.gemini.genai.Client") as mock_cls:
        yield mock_cls


def _make_gemini_client(mock_client_cls) -> tuple[GeminiClient, MagicMock]:
    """Instantiate GeminiClient with a fully mocked inner client."""
    mock_inner = MagicMock()
    mock_client_cls.return_value = mock_inner
    client = GeminiClient(api_key="fake-key")
    return client, mock_inner


# ---------------------------------------------------------------------------
# _translate_messages (static helper — no SDK dependency)
# ---------------------------------------------------------------------------

class TestTranslateMessages:
    def test_system_becomes_instruction(self) -> None:
        """A leading system message is lifted into Gemini's system_instruction,
        leaving the user turn in contents."""
        msgs = [
            {"role": "system", "content": "You are a dungeon master."},
            {"role": "user", "content": "I enter the cave."},
        ]
        instruction, contents = GeminiClient._translate_messages(msgs)
        assert instruction == "You are a dungeon master."
        assert contents[0]["role"] == "user"

    def test_assistant_maps_to_model(self) -> None:
        """The 'assistant' role is translated to Gemini's 'model' role."""
        msgs = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        _, contents = GeminiClient._translate_messages(msgs)
        assert contents[1]["role"] == "model"

    def test_no_system_message(self) -> None:
        """With no system message, the instruction is None and contents holds
        only the user turn."""
        msgs = [{"role": "user", "content": "hello"}]
        instruction, contents = GeminiClient._translate_messages(msgs)
        assert instruction is None
        assert len(contents) == 1

    def test_subsequent_system_message_prepended_to_next_user(self) -> None:
        """Only the first system message becomes the instruction; a later system
        message is folded into the following user turn's text."""
        msgs = [
            {"role": "system", "content": "Base system."},
            {"role": "user", "content": "Turn 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "system", "content": "Correction note."},
            {"role": "user", "content": "Turn 2"},
        ]
        instruction, contents = GeminiClient._translate_messages(msgs)
        assert instruction == "Base system."
        last_user = contents[-1]
        assert last_user["role"] == "user"
        assert "Correction note." in last_user["parts"][0]["text"]
        assert "Turn 2" in last_user["parts"][0]["text"]

    def test_empty_messages(self) -> None:
        """Translating an empty message list yields (None, [])."""
        instruction, contents = GeminiClient._translate_messages([])
        assert instruction is None
        assert contents == []


# ---------------------------------------------------------------------------
# is_available
# ---------------------------------------------------------------------------

class TestIsAvailable:
    def test_returns_true_when_list_models_succeeds(self, mock_client_cls) -> None:
        """is_available is True when the SDK's models.list call succeeds."""
        client, mock_inner = _make_gemini_client(mock_client_cls)
        mock_inner.models.list.return_value = [MagicMock()]
        assert client.is_available() is True

    def test_returns_false_on_exception(self, mock_client_cls) -> None:
        """is_available is False when models.list raises (e.g. bad auth)."""
        client, mock_inner = _make_gemini_client(mock_client_cls)
        mock_inner.models.list.side_effect = Exception("auth error")
        assert client.is_available() is False

    def test_never_raises(self, mock_client_cls) -> None:
        """is_available swallows unexpected errors and returns False."""
        client, mock_inner = _make_gemini_client(mock_client_cls)
        mock_inner.models.list.side_effect = RuntimeError("unexpected")
        assert client.is_available() is False


# ---------------------------------------------------------------------------
# complete
# ---------------------------------------------------------------------------

class TestComplete:
    def test_returns_llm_response(self, mock_client_cls) -> None:
        """complete returns an LLMResponse with the model's prose and stop reason."""
        client, mock_inner = _make_gemini_client(mock_client_cls)
        mock_inner.models.generate_content.return_value = _make_response("The castle falls.")
        result = client.complete([{"role": "user", "content": "attack"}])
        assert isinstance(result, LLMResponse)
        assert result.narrative_text == "The castle falls."
        assert result.finish_reason == "stop"

    def test_extracts_tool_call(self, mock_client_cls) -> None:
        """complete parses a fenced JSON tool-call out of the model content."""
        content = (
            "The goblin dies.\n"
            "~~~json\n"
            '{"state_changes": [{"entity_id": "goblin", "stat_key": "HP", "delta": -50}]}\n'
            "~~~"
        )
        client, mock_inner = _make_gemini_client(mock_client_cls)
        mock_inner.models.generate_content.return_value = _make_response(content)
        result = client.complete([])
        assert result.tool_call is not None
        assert result.tool_call["state_changes"][0]["entity_id"] == "goblin"
        assert "~~~json" not in result.narrative_text

    def test_finish_reason_length_on_max_tokens(self, mock_client_cls) -> None:
        """A MAX_TOKENS finish reason maps to LLMResponse.finish_reason 'length'."""
        client, mock_inner = _make_gemini_client(mock_client_cls)
        mock_inner.models.generate_content.return_value = _make_response("ok", "MAX_TOKENS")
        result = client.complete([])
        assert result.finish_reason == "length"

    def test_finish_reason_stop(self, mock_client_cls) -> None:
        """A STOP finish reason maps to LLMResponse.finish_reason 'stop'."""
        client, mock_inner = _make_gemini_client(mock_client_cls)
        mock_inner.models.generate_content.return_value = _make_response("ok", "STOP")
        result = client.complete([])
        assert result.finish_reason == "stop"

    def test_system_instruction_passed_in_config(self, mock_client_cls) -> None:
        """complete forwards a leading system message as config.system_instruction."""
        client, mock_inner = _make_gemini_client(mock_client_cls)
        mock_inner.models.generate_content.return_value = _make_response("ok")
        messages = [
            {"role": "system", "content": "You are a GM."},
            {"role": "user", "content": "I attack."},
        ]
        client.complete(messages)
        call_kwargs = mock_inner.models.generate_content.call_args.kwargs
        assert call_kwargs["config"].system_instruction == "You are a GM."

    def test_clamps_stop_sequences_to_five(self, mock_client_cls) -> None:
        """The Gemini API caps stop_sequences at 5; complete must truncate a
        longer engine-built list (else the API returns 400 INVALID_ARGUMENT)."""
        client, mock_inner = _make_gemini_client(mock_client_cls)
        mock_inner.models.generate_content.return_value = _make_response("ok")
        six_stops = ["a", "b", "c", "d", "e", "f"]
        client.complete([{"role": "user", "content": "hi"}], stop_sequences=six_stops)
        call_kwargs = mock_inner.models.generate_content.call_args.kwargs
        assert call_kwargs["config"].stop_sequences == ["a", "b", "c", "d", "e"]

    def test_keeps_stop_sequences_when_within_limit(self, mock_client_cls) -> None:
        """A list of ≤5 stop sequences is passed through unchanged."""
        client, mock_inner = _make_gemini_client(mock_client_cls)
        mock_inner.models.generate_content.return_value = _make_response("ok")
        client.complete([{"role": "user", "content": "hi"}], stop_sequences=["x", "y"])
        call_kwargs = mock_inner.models.generate_content.call_args.kwargs
        assert call_kwargs["config"].stop_sequences == ["x", "y"]

    def test_raises_connection_error_on_sdk_exception(self, mock_client_cls) -> None:
        """complete wraps an SDK exception as LLMConnectionError."""
        client, mock_inner = _make_gemini_client(mock_client_cls)
        mock_inner.models.generate_content.side_effect = Exception("network failure")
        with pytest.raises(LLMConnectionError):
            client.complete([])

    def test_raises_parse_error_when_text_is_none(self, mock_client_cls) -> None:
        """complete raises LLMParseError when the response carries no text."""
        client, mock_inner = _make_gemini_client(mock_client_cls)
        mock_resp = _make_response("ok")
        mock_resp.text = None
        mock_inner.models.generate_content.return_value = mock_resp
        with pytest.raises(LLMParseError, match="None text"):
            client.complete([])

    def test_no_system_message_sends_defaults_in_config(self, mock_client_cls) -> None:
        """Even without a system message, a config carrying default temperature/
        top_p (and a None system_instruction) is always sent."""
        client, mock_inner = _make_gemini_client(mock_client_cls)
        mock_inner.models.generate_content.return_value = _make_response("ok")
        client.complete([{"role": "user", "content": "hi"}])
        call_kwargs = mock_inner.models.generate_content.call_args.kwargs
        # config should ALWAYS be created now to pass temperature and top_p
        assert call_kwargs["config"] is not None
        assert call_kwargs["config"].temperature == 0.7
        assert call_kwargs["config"].top_p == 1.0
        assert call_kwargs["config"].system_instruction is None


# ---------------------------------------------------------------------------
# stream_tokens
# ---------------------------------------------------------------------------

class TestStreamTokens:
    def test_yields_tokens(self, mock_client_cls) -> None:
        """stream_tokens yields each streamed chunk's text in order."""
        client, mock_inner = _make_gemini_client(mock_client_cls)
        chunks = _make_streaming_chunks(["Once ", "upon ", "a time."])
        mock_inner.models.generate_content_stream.return_value = iter(chunks)
        tokens = list(client.stream_tokens([{"role": "user", "content": "story"}]))
        assert tokens == ["Once ", "upon ", "a time."]

    def test_skips_empty_chunks(self, mock_client_cls) -> None:
        """stream_tokens drops chunks with empty text."""
        client, mock_inner = _make_gemini_client(mock_client_cls)
        empty_chunk = MagicMock()
        empty_chunk.text = ""
        normal_chunk = MagicMock()
        normal_chunk.text = "Hello"
        mock_inner.models.generate_content_stream.return_value = iter([empty_chunk, normal_chunk])
        tokens = list(client.stream_tokens([]))
        assert tokens == ["Hello"]

    def test_raises_connection_error_on_sdk_exception(self, mock_client_cls) -> None:
        """stream_tokens wraps a streaming SDK exception as LLMConnectionError."""
        client, mock_inner = _make_gemini_client(mock_client_cls)
        mock_inner.models.generate_content_stream.side_effect = Exception("stream error")
        with pytest.raises(LLMConnectionError):
            list(client.stream_tokens([]))

    def test_skips_chunk_with_attribute_error_on_text(self, mock_client_cls) -> None:
        """Chunks that raise AttributeError on .text must be skipped."""
        client, mock_inner = _make_gemini_client(mock_client_cls)

        class _BadChunk:
            @property
            def text(self) -> str:
                raise AttributeError("no text")

        good_chunk = MagicMock()
        good_chunk.text = "Safe text"

        mock_inner.models.generate_content_stream.return_value = iter([_BadChunk(), good_chunk])
        tokens = list(client.stream_tokens([]))
        assert tokens == ["Safe text"]


# ---------------------------------------------------------------------------
# TICKET-031 — résilience aux quotas (429)
# ---------------------------------------------------------------------------

_QUOTA_MSG = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': "
    "'You exceeded your current quota. Please retry in 32.437285974s.', "
    "'status': 'RESOURCE_EXHAUSTED'}}"
)

# A model that is NOT in the key's free tier: the QuotaFailure violation reports
# quotaValue '0', yet the API still attaches a (misleading) retryDelay.
# Waiting can never succeed → must fail fast (TICKET-050).
_HARD_QUOTA_MSG = (
    "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': "
    "'You exceeded your current quota.', 'status': 'RESOURCE_EXHAUSTED', "
    "'details': [{'@type': 'type.googleapis.com/google.rpc.QuotaFailure', "
    "'violations': [{'quotaId': 'GenerateContentFreeTier', "
    "'quotaValue': '0'}]}, {'retryDelay': '14s'}]}}"
)


def _quota_exc() -> Exception:
    return Exception(_QUOTA_MSG)


def _fake_clock(monkeypatch) -> list[float]:
    """Horloge factice : `sleep` avance `monotonic` (l'attente par tranches de
    `_interruptible_wait` boucle sur monotonic — un sleep no-op bloquerait)."""
    clock = {"t": 0.0}
    sleeps: list[float] = []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)
        clock["t"] += s

    monkeypatch.setattr("axiom.backends.gemini.time.monotonic", lambda: clock["t"])
    monkeypatch.setattr("axiom.backends.gemini.time.sleep", fake_sleep)
    return sleeps


class TestQuotaResilience:
    def test_parse_retry_delay(self) -> None:
        from axiom.backends.gemini import _parse_retry_delay

        assert _parse_retry_delay(_QUOTA_MSG) == pytest.approx(32.437285974)
        assert _parse_retry_delay("'retryDelay': '32s'") == 32.0
        assert _parse_retry_delay("no hint here") is None

    def test_retry_respecte_le_delai_puis_reussit(self, mock_client_cls, monkeypatch) -> None:
        client, inner = _make_gemini_client(mock_client_cls)
        sleeps = _fake_clock(monkeypatch)

        inner.models.generate_content.side_effect = [
            _quota_exc(), _make_response("ok"),
        ]
        resp = client.complete([{"role": "user", "content": "hi"}])
        assert resp.narrative_text == "ok"
        assert inner.models.generate_content.call_count == 2
        # délai suggéré par l'API (32.4s) + marge, pas le backoff par défaut
        # (attendu par tranches ≤ 5s : on vérifie le total)
        assert 32.0 < sum(sleeps) < 35.0

    def test_erreur_non_quota_part_immediatement(self, mock_client_cls, monkeypatch) -> None:
        client, inner = _make_gemini_client(mock_client_cls)
        monkeypatch.setattr("axiom.backends.gemini.time.sleep",
                            lambda s: pytest.fail("ne doit pas attendre"))
        inner.models.generate_content.side_effect = Exception("boom 500")
        with pytest.raises(LLMConnectionError):
            client.complete([{"role": "user", "content": "hi"}])
        assert inner.models.generate_content.call_count == 1  # pas de retry

    def test_fallback_model_apres_retries(self, mock_client_cls, monkeypatch) -> None:
        from axiom.backends.gemini import _MAX_QUOTA_RETRIES

        mock_inner = MagicMock()
        mock_client_cls.return_value = mock_inner
        client = GeminiClient(api_key="fake-key", model_name="primary",
                              fallback_model="secours")
        _fake_clock(monkeypatch)

        # primary : quota épuisé à chaque tentative ; secours : OK.
        def gen(model, contents, config):
            if model == "primary":
                raise _quota_exc()
            return _make_response("sauvé")

        mock_inner.models.generate_content.side_effect = gen
        resp = client.complete([{"role": "user", "content": "hi"}])
        assert resp.narrative_text == "sauvé"
        calls = [c.kwargs["model"] for c in mock_inner.models.generate_content.call_args_list]
        assert calls.count("primary") == _MAX_QUOTA_RETRIES + 1
        assert calls[-1] == "secours"

    def test_quota_epuise_partout_erreur_claire(self, mock_client_cls, monkeypatch) -> None:
        client, inner = _make_gemini_client(mock_client_cls)
        _fake_clock(monkeypatch)
        inner.models.generate_content.side_effect = _quota_exc
        with pytest.raises(LLMConnectionError, match="quota"):
            client.complete([{"role": "user", "content": "hi"}])

    # --- TICKET-050 : quota structurellement à zéro (modèle hors free tier) ---

    def test_is_hard_quota_error_detects_zero_limit(self) -> None:
        from axiom.backends.gemini import _is_hard_quota_error

        assert _is_hard_quota_error(Exception(_HARD_QUOTA_MSG)) is True
        assert _is_hard_quota_error(Exception("429 RESOURCE_EXHAUSTED limit: 0")) is True
        # A real, recoverable per-minute quota is NOT hard (must still retry).
        assert _is_hard_quota_error(_quota_exc()) is False
        # Non-zero limits and non-quota errors are never hard.
        assert _is_hard_quota_error(Exception("429 RESOURCE_EXHAUSTED limit: 100")) is False
        assert _is_hard_quota_error(Exception("boom 500")) is False

    def test_hard_quota_skips_retries_no_wait(self, mock_client_cls, monkeypatch) -> None:
        """limit:0 → fail fast: a single call, zero backoff wait (no fallback)."""
        client, inner = _make_gemini_client(mock_client_cls)
        monkeypatch.setattr("axiom.backends.gemini.time.sleep",
                            lambda s: pytest.fail("hard quota must not wait"))
        inner.models.generate_content.side_effect = Exception(_HARD_QUOTA_MSG)
        with pytest.raises(LLMConnectionError, match="free tier"):
            client.complete([{"role": "user", "content": "hi"}])
        assert inner.models.generate_content.call_count == 1  # pas de retry

    def test_hard_quota_still_tries_fallback_model(self, mock_client_cls, monkeypatch) -> None:
        """A model out of the free tier skips retries but still falls back to a
        model that may be in the tier — and reaches it without any backoff."""
        mock_inner = MagicMock()
        mock_client_cls.return_value = mock_inner
        client = GeminiClient(api_key="fake-key", model_name="primary",
                              fallback_model="secours")
        monkeypatch.setattr("axiom.backends.gemini.time.sleep",
                            lambda s: pytest.fail("hard quota must not wait"))

        def gen(model, contents, config):
            if model == "primary":
                raise Exception(_HARD_QUOTA_MSG)
            return _make_response("sauvé")

        mock_inner.models.generate_content.side_effect = gen
        resp = client.complete([{"role": "user", "content": "hi"}])
        assert resp.narrative_text == "sauvé"
        calls = [c.kwargs["model"] for c in mock_inner.models.generate_content.call_args_list]
        assert calls.count("primary") == 1  # une seule fois, pas _MAX_QUOTA_RETRIES+1
        assert calls[-1] == "secours"

    def test_rate_limiter_espace_les_requetes(self, monkeypatch) -> None:
        from axiom.backends import gemini as g

        clock = {"now": 100.0}
        sleeps: list[float] = []
        monkeypatch.setattr(g.time, "monotonic", lambda: clock["now"])
        monkeypatch.setattr(g.time, "sleep", sleeps.append)

        rl = g._RateLimiter()
        rl.wait_turn("m", 6.0)   # première : passe direct
        rl.wait_turn("m", 6.0)   # deuxième : doit attendre ~6s
        assert sleeps == [pytest.approx(6.0)]
        # un autre modèle a son propre compteur
        rl.wait_turn("autre", 6.0)
        assert len(sleeps) == 1

    def test_pacing_desactive_par_defaut(self, mock_client_cls, monkeypatch) -> None:
        client, inner = _make_gemini_client(mock_client_cls)
        monkeypatch.setattr("axiom.backends.gemini.time.sleep",
                            lambda s: pytest.fail("pas de pacing par défaut"))
        inner.models.generate_content.return_value = _make_response("ok")
        assert client.complete([{"role": "user", "content": "hi"}]).narrative_text == "ok"



# ---------------------------------------------------------------------------
# Network transport (QA-test-connexion-gemini)
# ---------------------------------------------------------------------------

class TestIPv4FirstTransport:
    """IPv4 must be tried first (a broken IPv6 route stalled for minutes) and
    every request must carry a connect timeout — the SDK passes timeout=None
    per request, which disables client-level timeouts."""

    @staticmethod
    def _make_transport():
        import httpx
        from axiom.backends.transport import IPv4FirstTransport

        transport = IPv4FirstTransport()
        transport._ipv4 = MagicMock()
        transport._dual = MagicMock()
        return httpx, transport

    def test_ipv4_tried_first(self) -> None:
        httpx, transport = self._make_transport()
        request = httpx.Request("GET", "https://example.test")
        response = transport.handle_request(request)
        assert response is transport._ipv4.handle_request.return_value
        transport._dual.handle_request.assert_not_called()

    def test_falls_back_to_dual_stack_and_sticks(self) -> None:
        httpx, transport = self._make_transport()
        transport._ipv4.handle_request.side_effect = httpx.ConnectError("no v4")
        request = httpx.Request("GET", "https://example.test")
        response = transport.handle_request(request)
        assert response is transport._dual.handle_request.return_value
        # The dead IPv4 probe is remembered: next request skips it entirely.
        transport.handle_request(httpx.Request("GET", "https://example.test"))
        assert transport._ipv4.handle_request.call_count == 1
        assert transport._dual.handle_request.call_count == 2

    def test_injects_connect_timeout_when_none(self) -> None:
        from axiom.backends.transport import _CONNECT_TIMEOUT_S

        httpx, transport = self._make_transport()
        request = httpx.Request(
            "GET",
            "https://example.test",
            extensions={
                "timeout": {"connect": None, "read": None, "write": None, "pool": None}
            },
        )
        transport.handle_request(request)
        timeouts = request.extensions["timeout"]
        assert timeouts["connect"] == _CONNECT_TIMEOUT_S
        # Read stays unlimited: long generations must not be cut short.
        assert timeouts["read"] is None

    def test_injects_connect_timeout_when_extension_missing(self) -> None:
        from axiom.backends.transport import _CONNECT_TIMEOUT_S

        httpx, transport = self._make_transport()
        request = httpx.Request("GET", "https://example.test")
        transport.handle_request(request)
        assert request.extensions["timeout"]["connect"] == _CONNECT_TIMEOUT_S

    def test_respects_explicit_connect_timeout(self) -> None:
        httpx, transport = self._make_transport()
        request = httpx.Request(
            "GET",
            "https://example.test",
            extensions={"timeout": {"connect": 30.0, "read": 5.0}},
        )
        transport.handle_request(request)
        assert request.extensions["timeout"] == {"connect": 30.0, "read": 5.0}

    def test_gemini_client_built_with_transport(self, mock_client_cls) -> None:
        from axiom.backends.transport import IPv4FirstTransport

        GeminiClient(api_key="fake-key")
        http_options = mock_client_cls.call_args.kwargs["http_options"]
        assert isinstance(http_options.client_args["transport"], IPv4FirstTransport)
