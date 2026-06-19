"""tests/test_gemini_prompt_cache.py

Explicit Gemini context caching (Phase 4 / B-4): guarded by size, memoises
failures, and always falls back to the inline system prompt. The genai client
is faked — no network.
"""

from __future__ import annotations

import pytest

from axiom.backends.gemini import GeminiClient


class _FakeCaches:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.create_calls = 0

    def create(self, *, model, config):
        self.create_calls += 1
        if self.fail:
            raise RuntimeError("cached content too small")
        return type("Cached", (), {"name": f"caches/{model}-abc"})()


def _client(monkeypatch, *, enabled, fail=False) -> GeminiClient:
    # Avoid constructing the real genai.Client (needs network/transport).
    monkeypatch.setattr(GeminiClient, "__init__",
                        lambda self, **kw: None)
    c = GeminiClient()
    c._enable_prompt_cache = enabled
    c._prompt_cache = {}
    c._client = type("C", (), {"caches": _FakeCaches(fail=fail)})()
    return c


SMALL = "short system prompt"
BIG = "x" * (GeminiClient._PROMPT_CACHE_MIN_CHARS + 10)


def test_disabled_never_caches(monkeypatch):
    c = _client(monkeypatch, enabled=False)
    assert c._resolve_cached_content("gemini-2.0-flash", BIG) is None
    assert c._client.caches.create_calls == 0


def test_small_prompt_skipped(monkeypatch):
    c = _client(monkeypatch, enabled=True)
    assert c._resolve_cached_content("gemini-2.0-flash", SMALL) is None
    assert c._client.caches.create_calls == 0  # never even attempted


def test_big_prompt_cached_and_reused(monkeypatch):
    c = _client(monkeypatch, enabled=True)
    name1 = c._resolve_cached_content("gemini-2.0-flash", BIG)
    name2 = c._resolve_cached_content("gemini-2.0-flash", BIG)
    assert name1 and name1 == name2
    assert c._client.caches.create_calls == 1  # second call reuses the memo


def test_failure_memoised_and_graceful(monkeypatch):
    c = _client(monkeypatch, enabled=True, fail=True)
    assert c._resolve_cached_content("gemini-2.0-flash", BIG) is None
    assert c._resolve_cached_content("gemini-2.0-flash", BIG) is None
    assert c._client.caches.create_calls == 1  # failure remembered, not retried


def test_make_config_uses_cache_or_inline(monkeypatch):
    c = _client(monkeypatch, enabled=True)
    cfg = c._make_generate_config("gemini-2.0-flash", BIG, temperature=0.2)
    assert getattr(cfg, "cached_content", None) == "caches/gemini-2.0-flash-abc"
    assert not getattr(cfg, "system_instruction", None)
    # Small prompt → inline system_instruction, no cache.
    cfg2 = c._make_generate_config("gemini-2.0-flash", SMALL, temperature=0.2)
    assert getattr(cfg2, "system_instruction", None) == SMALL
    assert getattr(cfg2, "cached_content", None) is None
