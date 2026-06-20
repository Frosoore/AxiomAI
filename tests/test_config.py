"""
tests/test_config.py

Unit tests for core/config.py — AppConfig, load_config, save_config,
build_llm_from_config.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from axiom.config import (
    AppConfig,
    OPENAI_COMPAT_PROVIDERS,
    build_llm_from_config,
    load_config,
    resolve_extraction_model,
    resolve_time_model,
    save_config,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def config_dir(tmp_path: Path):
    """Patch _CONFIG_FILE to use a temp directory."""
    config_file = tmp_path / "settings.json"
    with patch("axiom.config._CONFIG_FILE", config_file), \
         patch("axiom.config._CONFIG_DIR", tmp_path):
        yield tmp_path, config_file


# ---------------------------------------------------------------------------
# AppConfig defaults
# ---------------------------------------------------------------------------

class TestAppConfig:
    def test_defaults(self) -> None:
        """A freshly-constructed AppConfig carries the documented default
        backend, URLs and models."""
        cfg = AppConfig()
        assert cfg.llm_backend == "universal"
        assert cfg.universal_base_url == "http://localhost:11434/v1"
        assert cfg.universal_model == "llama3.2"
        assert cfg.gemini_api_key == ""
        assert cfg.gemini_model == "gemini-2.0-flash"
        assert cfg.custom_wallpaper == ""


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_returns_defaults_when_no_file(self, config_dir) -> None:
        """With no settings file on disk, load_config returns a default AppConfig."""
        _, config_file = config_dir
        assert not config_file.exists()
        cfg = load_config()
        assert cfg == AppConfig()

    def test_loads_saved_values(self, config_dir) -> None:
        """load_config reads persisted values from the settings file."""
        _, config_file = config_dir
        data = {
            "llm_backend": "gemini",
            "gemini_api_key": "test-key",
            "rag_chunk_count": 9,
        }
        config_file.write_text(json.dumps(data))
        cfg = load_config()
        assert cfg.llm_backend == "gemini"
        assert cfg.gemini_api_key == "test-key"
        assert cfg.rag_chunk_count == 9

    def test_unknown_keys_ignored(self, config_dir) -> None:
        """Unrecognised keys in the settings file are ignored rather than
        crashing load_config (forward compatibility)."""
        _, config_file = config_dir
        data = {"llm_backend": "universal", "unknown_future_key": "ignored"}
        config_file.write_text(json.dumps(data))
        cfg = load_config()
        assert cfg.llm_backend == "universal"

    def test_malformed_json_returns_defaults(self, config_dir) -> None:
        """A corrupt settings file falls back to defaults instead of raising."""
        _, config_file = config_dir
        config_file.write_text("{not valid json")
        cfg = load_config()
        assert cfg == AppConfig()

    def test_never_raises_on_any_error(self, config_dir) -> None:
        """Even valid-but-wrong-typed JSON (e.g. 'null') yields an AppConfig,
        never an exception."""
        _, config_file = config_dir
        config_file.write_text("null")  # valid JSON but wrong type
        cfg = load_config()
        assert isinstance(cfg, AppConfig)


# ---------------------------------------------------------------------------
# save_config + load_config round-trip
# ---------------------------------------------------------------------------

class TestSaveConfig:
    def test_round_trip(self, config_dir) -> None:
        """Values saved by save_config are read back identically by load_config."""
        original = AppConfig(
            llm_backend="gemini",
            gemini_api_key="my-secret-key",
            chronicler_minutes_interval=480,
            basic_prompt="Speak only in English",
            negative_prompt="Do not mention magic",
            custom_wallpaper="my_wallpaper.png",
        )
        save_config(original)
        loaded = load_config()
        assert loaded.llm_backend == "gemini"
        assert loaded.gemini_api_key == "my-secret-key"
        assert loaded.chronicler_minutes_interval == 480
        assert loaded.basic_prompt == "Speak only in English"
        assert loaded.negative_prompt == "Do not mention magic"
        assert loaded.custom_wallpaper == "my_wallpaper.png"


    def test_creates_directory(self, tmp_path: Path) -> None:
        """save_config creates any missing parent directories for the settings file."""
        nested = tmp_path / "a" / "b" / "settings.json"
        with patch("axiom.config._CONFIG_FILE", nested), \
             patch("axiom.config._CONFIG_DIR", nested.parent):
            save_config(AppConfig())
        assert nested.exists()

    def test_overwrites_existing(self, config_dir) -> None:
        """A second save_config fully replaces the previously persisted settings."""
        save_config(AppConfig(universal_model="mistral"))
        save_config(AppConfig(universal_model="llama3.2"))
        loaded = load_config()
        assert loaded.universal_model == "llama3.2"


# ---------------------------------------------------------------------------
# build_llm_from_config
# ---------------------------------------------------------------------------

class TestBuildLlmFromConfig:
    def test_ollama_backend_returns_universal_client(self) -> None:
        """The 'universal' backend builds a UniversalClient (the OpenAI-compatible
        client used for Ollama and similar local servers)."""
        from axiom.backends.universal import UniversalClient
        cfg = AppConfig(llm_backend="universal", universal_model="llama3.2")
        llm = build_llm_from_config(cfg)
        assert isinstance(llm, UniversalClient)

    def test_gemini_backend_returns_gemini_client(self) -> None:
        """The 'gemini' backend with an API key builds a GeminiClient."""
        from axiom.backends.gemini import GeminiClient
        from unittest.mock import patch as p
        with p("axiom.backends.gemini.genai.Client"):
            cfg = AppConfig(llm_backend="gemini", gemini_api_key="key")
            llm = build_llm_from_config(cfg)
            assert isinstance(llm, GeminiClient)

    def test_unknown_backend_raises_value_error(self) -> None:
        """An unrecognised llm_backend raises ValueError('Unknown LLM backend')."""
        cfg = AppConfig(llm_backend="unknown_ai")
        with pytest.raises(ValueError, match="Unknown LLM backend"):
            build_llm_from_config(cfg)

    def test_gemini_without_api_key_raises(self) -> None:
        """Selecting the gemini backend with no API key raises ValueError('no API key')."""
        cfg = AppConfig(llm_backend="gemini", gemini_api_key="")
        with pytest.raises(ValueError, match="no API key"):
            build_llm_from_config(cfg)

    def test_ollama_url_passed_to_client(self) -> None:
        """The configured base_url and model are forwarded onto the built
        UniversalClient."""
        from axiom.backends.universal import UniversalClient
        cfg = AppConfig(
            llm_backend="universal",
            universal_base_url="http://192.168.1.5:11434",
            universal_model="mistral",
        )
        llm = build_llm_from_config(cfg)
        assert isinstance(llm, UniversalClient)
        assert llm.base_url == "http://192.168.1.5:11434"
        assert llm.model_name == "mistral"


class TestOpenAICompatCloudProviders:
    """The claude/venice/fireworks/openai backends reuse UniversalClient with
    a preset base URL (Cloud settings tab dropdown)."""

    def test_venice_backend_builds_universal_client(self) -> None:
        from axiom.backends.universal import UniversalClient
        cfg = AppConfig(
            llm_backend="venice", venice_api_key="vk", venice_model="zai-org-glm-4.7"
        )
        llm = build_llm_from_config(cfg)
        assert isinstance(llm, UniversalClient)
        assert llm.base_url == "https://api.venice.ai/api/v1"
        assert llm.api_key == "vk"
        assert llm.model_name == "zai-org-glm-4.7"

    def test_fireworks_backend_builds_universal_client(self) -> None:
        cfg = AppConfig(llm_backend="fireworks", fireworks_api_key="fk")
        llm = build_llm_from_config(cfg)
        assert llm.base_url == "https://api.fireworks.ai/inference/v1"

    def test_openrouter_backend_builds_universal_client(self) -> None:
        cfg = AppConfig(llm_backend="openrouter", openrouter_api_key="ork")
        llm = build_llm_from_config(cfg)
        assert llm.base_url == "https://openrouter.ai/api/v1"
        assert llm.api_key == "ork"
        assert llm.model_name == "openrouter/auto"

    def test_claude_backend_uses_native_anthropic_headers(self) -> None:
        """Anthropic's /v1/models rejects a bare Bearer: the claude provider
        authenticates with x-api-key + anthropic-version instead."""
        cfg = AppConfig(llm_backend="claude", anthropic_api_key="sk-ant-test")
        llm = build_llm_from_config(cfg)
        assert llm.base_url == "https://api.anthropic.com/v1"
        headers = llm._get_headers()
        assert headers["x-api-key"] == "sk-ant-test"
        assert headers["anthropic-version"] == "2023-06-01"
        assert "Authorization" not in headers

    def test_stop_sequences_capped_where_documented(self) -> None:
        """Venice, Fireworks, OpenAI and OpenRouter reject more than 4 stop
        sequences with a 400 (their /models works, so the connection test
        passed but generation failed — bug rapporté sur Fireworks). Claude's
        compat layer has no such limit: full list kept there."""
        keys = {
            "venice": {"venice_api_key": "k"},
            "fireworks": {"fireworks_api_key": "k"},
            "openai": {"openai_api_key": "k"},
            "openrouter": {"openrouter_api_key": "k"},
        }
        for provider, kwargs in keys.items():
            llm = build_llm_from_config(AppConfig(llm_backend=provider, **kwargs))
            payload = llm._get_payload([{"role": "user", "content": "hi"}], stream=False)
            assert len(payload["stop"]) <= 4, provider

        claude = build_llm_from_config(
            AppConfig(llm_backend="claude", anthropic_api_key="k")
        )
        payload = claude._get_payload([{"role": "user", "content": "hi"}], stream=False)
        assert len(payload["stop"]) > 4

    def test_missing_api_key_raises_for_each_provider(self) -> None:
        for provider in OPENAI_COMPAT_PROVIDERS:
            cfg = AppConfig(llm_backend=provider)
            with pytest.raises(ValueError, match="no API key"):
                build_llm_from_config(cfg)

    def test_status_error_message_includes_provider_body(self) -> None:
        """HTTP 4xx/5xx from a provider must surface the response body (the
        actionable cause) instead of a bare '400 Bad Request'."""
        import httpx
        from axiom.backends.universal import UniversalClient

        request = httpx.Request(
            "POST", "https://api.fireworks.ai/inference/v1/chat/completions"
        )
        response = httpx.Response(
            400, request=request, text='{"error": "stop: at most 4 items"}'
        )
        exc = httpx.HTTPStatusError("Bad Request", request=request, response=response)
        msg = UniversalClient._format_status_error(exc)
        assert "400" in msg
        assert "stop: at most 4 items" in msg

    def test_status_error_404_hints_at_unknown_model(self) -> None:
        """A 404 on /chat/completions means the model id is unknown/retired —
        the message must say so (the server itself answers, /models is 200)."""
        import httpx
        from axiom.backends.universal import UniversalClient

        request = httpx.Request(
            "POST", "https://api.fireworks.ai/inference/v1/chat/completions"
        )
        response = httpx.Response(404, request=request, text="")
        exc = httpx.HTTPStatusError("Not Found", request=request, response=response)
        msg = UniversalClient._format_status_error(exc)
        assert "404" in msg
        assert "model" in msg.lower()
        assert "Settings" in msg

    def test_model_override_wins(self) -> None:
        cfg = AppConfig(llm_backend="venice", venice_api_key="vk")
        llm = build_llm_from_config(cfg, model_override="qwen3-next-80b")
        assert llm.model_name == "qwen3-next-80b"

    def test_cloud_provider_keys_round_trip(self, config_dir) -> None:
        """New per-provider key/model fields persist through save/load."""
        save_config(AppConfig(
            llm_backend="venice",
            venice_api_key="vk",
            anthropic_api_key="ak",
            fireworks_api_key="fwk",
            openai_api_key="ok",
        ))
        loaded = load_config()
        assert loaded.llm_backend == "venice"
        assert loaded.venice_api_key == "vk"
        assert loaded.anthropic_api_key == "ak"
        assert loaded.fireworks_api_key == "fwk"
        assert loaded.openai_api_key == "ok"


class TestResolveExtractionModel:
    """resolve_extraction_model picks a backend-appropriate auxiliary model.

    `extraction_model` is an Ollama-style name; sending it to Gemini → 404.
    """

    def test_universal_backend_uses_extraction_model(self) -> None:
        """On the universal/Ollama backend the local extraction_model is used."""
        cfg = AppConfig(llm_backend="universal", extraction_model="llama3.1:8b")
        assert resolve_extraction_model(cfg) == "llama3.1:8b"

    def test_gemini_backend_falls_back_to_gemini_model(self) -> None:
        """On the Gemini backend the Ollama extraction_model is ignored in favour
        of gemini_model (avoids a 404 from an unknown model name)."""
        cfg = AppConfig(
            llm_backend="gemini",
            gemini_model="gemini-2.0-flash",
            extraction_model="llama3.1:8b",
        )
        assert resolve_extraction_model(cfg) == "gemini-2.0-flash"

    def test_openai_compat_backend_falls_back_to_provider_model(self) -> None:
        """Same 404 trap on the OpenAI-compatible cloud providers: the local
        extraction/time model names are replaced by the provider's model."""
        cfg = AppConfig(
            llm_backend="venice",
            venice_model="zai-org-glm-4.7",
            extraction_model="llama3.1:8b",
            time_model="llama3.2:1b",
        )
        assert resolve_extraction_model(cfg) == "zai-org-glm-4.7"
        assert resolve_time_model(cfg) == "zai-org-glm-4.7"


class TestHttpTimeouts:
    """QA-test-connexion-gemini: the connect phase must have its own short
    timeout — a scalar timeout let a broken IPv6 route stall the client for
    minutes before the IPv4 fallback."""

    def test_universal_client_has_separate_connect_timeout(self) -> None:
        from axiom.backends.universal import (
            UniversalClient,
            _CONNECT_TIMEOUT,
            _DEFAULT_TIMEOUT,
        )
        llm = UniversalClient(base_url="http://x.test/v1", api_key="", model_name="m")
        assert llm._client.timeout.connect == _CONNECT_TIMEOUT
        assert llm._client.timeout.read == _DEFAULT_TIMEOUT

    def test_universal_client_uses_ipv4_first_transport(self) -> None:
        from axiom.backends.transport import IPv4FirstTransport
        from axiom.backends.universal import UniversalClient

        llm = UniversalClient(base_url="http://x.test/v1", api_key="", model_name="m")
        assert isinstance(llm._client._transport, IPv4FirstTransport)
