"""
tests/test_reasoning_models.py

TICKET-066 — reasoning models (gpt-oss, o-series, deepseek-v4…) on the
universal backend:

* a response whose `message` has no `content` (budget eaten by the hidden
  chain-of-thought) must NOT crash `complete()` — it is an empty generation;
* `_get_payload` floors `max_tokens` for reasoning model ids (the cap is
  billed on actual usage, so the floor is free) and leaves other models
  untouched;
* `reasoning_effort: "low"` is sent for gpt-oss models only (probed accepted
  by Fireworks on 2026-06-12).
"""

from __future__ import annotations

import httpx

from axiom.backends.universal import (
    _REASONING_TOKEN_FLOOR,
    UniversalClient,
    _is_reasoning_model,
)


def _client(model_name: str) -> UniversalClient:
    return UniversalClient(
        base_url="https://fw.test/v1", api_key="k", model_name=model_name
    )


def _mock(llm: UniversalClient, handler) -> UniversalClient:
    llm._client = httpx.Client(
        base_url="https://fw.test/v1",
        headers=llm._get_headers(),
        transport=httpx.MockTransport(handler),
    )
    return llm


# ---------------------------------------------------------------------------
# Reasoning model detection
# ---------------------------------------------------------------------------

class TestReasoningDetection:
    def test_known_reasoning_ids_match(self) -> None:
        for model in (
            "accounts/fireworks/models/gpt-oss-20b",
            "accounts/fireworks/models/gpt-oss-120b",
            "accounts/fireworks/models/deepseek-v4-flash",
            "deepseek-r1",
            "o3-mini",
            "o4-mini",
            "qwq-32b",
            "qwen3-235b-thinking",
        ):
            assert _is_reasoning_model(model), model

    def test_plain_models_do_not_match(self) -> None:
        for model in (
            "gpt-4.1-mini",
            "accounts/fireworks/models/llama-v3p1-70b-instruct",
            "mistral-small",
            "kimi-k2p5",
        ):
            assert not _is_reasoning_model(model), model

    def test_o_series_must_start_the_id(self) -> None:
        # "o1"/"o3"/"o4" only count as a prefix of the model id, not anywhere.
        assert not _is_reasoning_model("solar-pro4")
        assert _is_reasoning_model("openai/o1-mini")  # tail after the '/'


# ---------------------------------------------------------------------------
# Token floor in the payload
# ---------------------------------------------------------------------------

class TestTokenFloor:
    def test_floor_applied_to_reasoning_model(self) -> None:
        llm = _client("accounts/fireworks/models/gpt-oss-120b")
        payload = llm._get_payload([], stream=False, max_tokens=150)
        assert payload["max_tokens"] == _REASONING_TOKEN_FLOOR

    def test_floor_applied_to_default_budget(self) -> None:
        llm = _client("accounts/fireworks/models/deepseek-v4-flash")
        payload = llm._get_payload([], stream=False)  # default 1024
        assert payload["max_tokens"] == _REASONING_TOKEN_FLOOR

    def test_larger_explicit_budget_is_kept(self) -> None:
        llm = _client("accounts/fireworks/models/gpt-oss-20b")
        payload = llm._get_payload([], stream=False, max_tokens=4096)
        assert payload["max_tokens"] == 4096

    def test_plain_model_budget_untouched(self) -> None:
        llm = _client("gpt-4.1-mini")
        payload = llm._get_payload([], stream=False, max_tokens=150)
        assert payload["max_tokens"] == 150


# ---------------------------------------------------------------------------
# reasoning_effort: gpt-oss only
# ---------------------------------------------------------------------------

class TestReasoningEffort:
    def test_sent_for_gpt_oss(self) -> None:
        llm = _client("accounts/fireworks/models/gpt-oss-20b")
        payload = llm._get_payload([], stream=False)
        assert payload["reasoning_effort"] == "low"

    def test_not_sent_for_other_reasoning_models(self) -> None:
        llm = _client("accounts/fireworks/models/deepseek-v4-flash")
        payload = llm._get_payload([], stream=False)
        assert "reasoning_effort" not in payload

    def test_not_sent_for_plain_models(self) -> None:
        llm = _client("gpt-4.1-mini")
        payload = llm._get_payload([], stream=False)
        assert "reasoning_effort" not in payload


# ---------------------------------------------------------------------------
# Missing/empty `content` tolerated (the original Timekeeper crash)
# ---------------------------------------------------------------------------

class TestMissingContent:
    def test_content_key_absent_returns_empty_narrative(self) -> None:
        # gpt-oss with an exhausted budget: message has reasoning_content
        # but NO content key at all (observed live, finish_reason=length).
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{
                "message": {"role": "assistant", "reasoning_content": "…"},
                "finish_reason": "length",
            }]})

        llm = _mock(_client("accounts/fireworks/models/gpt-oss-20b"), handler)
        result = llm.complete([{"role": "user", "content": "hi"}])
        assert result.narrative_text == ""
        assert result.tool_call is None
        assert result.finish_reason == "length"

    def test_content_null_returns_empty_narrative(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"choices": [{
                "message": {"role": "assistant", "content": None},
                "finish_reason": "length",
            }]})

        llm = _mock(_client("accounts/fireworks/models/gpt-oss-20b"), handler)
        result = llm.complete([{"role": "user", "content": "hi"}])
        assert result.narrative_text == ""
        assert result.tool_call is None
