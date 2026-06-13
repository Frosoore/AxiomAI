"""
tests/test_builtin_keys.py

Shared beta keys, key rotation and the affordability filter (TICKET-062).
"""

import json

import httpx
import pytest

from axiom.backends.base import LLMConnectionError
from axiom.backends.universal import UniversalClient
from axiom.config import (
    AppConfig,
    build_llm_from_config,
    get_builtin_keys,
    register_builtin_keys,
    uses_builtin_keys,
)
from core.builtin_keys import (
    BUILTIN_MAX_INPUT_PRICE,
    BUILTIN_MAX_OUTPUT_PRICE,
    FIREWORKS_MODEL_PRICES,
    affordable_builtin_models,
    fireworks_builtin_keys,
    is_affordable_on_builtin,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    """Each test starts with an empty builtin-key registry."""
    register_builtin_keys("fireworks", [])
    yield
    register_builtin_keys("fireworks", [])


# ---------------------------------------------------------------------------
# Key pool (decoding + registry)
# ---------------------------------------------------------------------------

class TestKeyPool:
    def test_decodes_four_plausible_fireworks_keys(self) -> None:
        keys = fireworks_builtin_keys()
        assert len(keys) == 4
        assert len(set(keys)) == 4
        for key in keys:
            assert key.startswith("fw_") and len(key) > 10

    def test_keys_are_not_in_clear_text_in_the_module(self) -> None:
        """The scraper deterrent: no decoded key appears in the source."""
        from pathlib import Path
        import core.builtin_keys as mod
        source = Path(mod.__file__).read_text(encoding="utf-8")
        for key in fireworks_builtin_keys():
            assert key not in source

    def test_registry_round_trip(self) -> None:
        register_builtin_keys("fireworks", ["k1", "", "  ", "k2"])
        assert get_builtin_keys("fireworks") == ["k1", "k2"]
        register_builtin_keys("fireworks", [])
        assert get_builtin_keys("fireworks") == []

    def test_uses_builtin_keys(self) -> None:
        cfg = AppConfig(llm_backend="fireworks", fireworks_api_key="")
        assert uses_builtin_keys(cfg) is False  # nothing registered
        register_builtin_keys("fireworks", ["k1"])
        assert uses_builtin_keys(cfg) is True
        assert uses_builtin_keys(
            AppConfig(llm_backend="fireworks", fireworks_api_key="mine")
        ) is False  # user key wins
        assert uses_builtin_keys(AppConfig(llm_backend="gemini")) is False

    def test_build_llm_uses_registered_pool_when_no_user_key(self) -> None:
        register_builtin_keys("fireworks", ["k1", "k2", "k3"])
        llm = build_llm_from_config(AppConfig(llm_backend="fireworks"))
        assert isinstance(llm, UniversalClient)
        assert llm._api_keys == ["k1", "k2", "k3"]
        assert llm.api_key == "k1"

    def test_build_llm_prefers_user_key_over_pool(self) -> None:
        register_builtin_keys("fireworks", ["k1"])
        llm = build_llm_from_config(
            AppConfig(llm_backend="fireworks", fireworks_api_key="mine")
        )
        assert llm._api_keys == ["mine"]

    def test_build_llm_still_raises_without_pool_nor_key(self) -> None:
        with pytest.raises(ValueError, match="no API key"):
            build_llm_from_config(AppConfig(llm_backend="fireworks"))


# ---------------------------------------------------------------------------
# Affordability filter
# ---------------------------------------------------------------------------

class TestAffordability:
    def test_known_cheap_models_pass(self) -> None:
        assert is_affordable_on_builtin("accounts/fireworks/models/gpt-oss-120b")
        assert is_affordable_on_builtin("accounts/fireworks/models/gpt-oss-20b")
        assert is_affordable_on_builtin("accounts/fireworks/models/deepseek-v4-flash")

    def test_flagships_fail(self) -> None:
        assert not is_affordable_on_builtin("accounts/fireworks/models/kimi-k2p6")
        assert not is_affordable_on_builtin("accounts/fireworks/models/glm-5p1")

    def test_unknown_model_is_not_affordable(self) -> None:
        assert not is_affordable_on_builtin("accounts/fireworks/models/brand-new")

    def test_affordable_list_respects_caps(self) -> None:
        models = affordable_builtin_models()
        assert models, "the beta needs at least one affordable model"
        for m in models:
            prices = FIREWORKS_MODEL_PRICES[m]
            assert prices[0] <= BUILTIN_MAX_INPUT_PRICE
            assert prices[1] <= BUILTIN_MAX_OUTPUT_PRICE

    def test_default_fireworks_model_is_affordable(self) -> None:
        """The zero-config default must run on the shared keys."""
        assert is_affordable_on_builtin(AppConfig().fireworks_model)


# ---------------------------------------------------------------------------
# Key rotation in UniversalClient
# ---------------------------------------------------------------------------

def _mock_llm(handler, keys: list[str]) -> UniversalClient:
    """UniversalClient whose httpx client routes to a MockTransport."""
    llm = UniversalClient(
        base_url="https://fw.test/v1",
        api_key=keys[0],
        model_name="m",
        fallback_api_keys=keys[1:],
    )
    llm._client = httpx.Client(
        base_url="https://fw.test/v1",
        headers=llm._get_headers(),
        transport=httpx.MockTransport(handler),
    )
    return llm


def _completion_body(text: str = "ok") -> dict:
    return {"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}


class TestKeyRotation:
    def test_complete_rotates_to_next_key_on_429(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.headers["Authorization"] == "Bearer dead":
                return httpx.Response(429, json={"error": "quota"})
            return httpx.Response(200, json=_completion_body("hello"))

        llm = _mock_llm(handler, ["dead", "alive"])
        result = llm.complete([{"role": "user", "content": "hi"}])
        assert result.narrative_text == "hello"
        assert llm.api_key == "alive"  # sticky switch

    def test_rotation_is_sticky_across_calls(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.headers["Authorization"])
            if request.headers["Authorization"] == "Bearer dead":
                return httpx.Response(401, json={"error": "revoked"})
            return httpx.Response(200, json=_completion_body())

        llm = _mock_llm(handler, ["dead", "alive"])
        llm.complete([{"role": "user", "content": "1"}])
        llm.complete([{"role": "user", "content": "2"}])
        assert calls == ["Bearer dead", "Bearer alive", "Bearer alive"]

    def test_exhausted_pool_raises_with_provider_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(402, json={"error": "payment required"})

        llm = _mock_llm(handler, ["k1", "k2"])
        with pytest.raises(LLMConnectionError, match="402"):
            llm.complete([{"role": "user", "content": "hi"}])
        assert llm.api_key == "k2"  # both were tried

    def test_no_rotation_on_server_error(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.headers["Authorization"])
            return httpx.Response(500, json={"error": "boom"})

        llm = _mock_llm(handler, ["k1", "k2"])
        with pytest.raises(LLMConnectionError):
            llm.complete([{"role": "user", "content": "hi"}])
        assert calls == ["Bearer k1"]

    def test_stream_rotates_before_first_token(self) -> None:
        sse = (
            b'data: {"choices": [{"delta": {"content": "tok"}}]}\n\n'
            b"data: [DONE]\n\n"
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.headers["Authorization"] == "Bearer dead":
                return httpx.Response(429, json={"error": "quota"})
            return httpx.Response(200, content=sse)

        llm = _mock_llm(handler, ["dead", "alive"])
        tokens = list(llm.stream_tokens([{"role": "user", "content": "hi"}]))
        assert tokens == ["tok"]
        assert llm.api_key == "alive"

    def test_list_models_rotates(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.headers["Authorization"] == "Bearer dead":
                return httpx.Response(403, json={"error": "suspended"})
            return httpx.Response(200, json={"data": [{"id": "m1"}]})

        llm = _mock_llm(handler, ["dead", "alive"])
        assert llm.list_models() == ["m1"]


# ---------------------------------------------------------------------------
# Model picker entries (settings dialog helper, no Qt needed)
# ---------------------------------------------------------------------------

class TestFireworksModelEntries:
    def test_merges_listing_with_price_table(self) -> None:
        from ui.settings_dialog import _fireworks_model_entries

        listed_only = "accounts/fireworks/models/not-in-price-table"
        entries = _fireworks_model_entries([listed_only], builtin=False)
        ids = [mid for mid, _ in entries]
        assert listed_only in ids
        assert "accounts/fireworks/models/gpt-oss-20b" in ids  # from the table

    def test_builtin_mode_keeps_only_affordable(self) -> None:
        from ui.settings_dialog import _fireworks_model_entries

        entries = _fireworks_model_entries(
            ["accounts/fireworks/models/kimi-k2p6"], builtin=True
        )
        ids = [mid for mid, _ in entries]
        assert ids and set(ids) == set(affordable_builtin_models())
        assert "accounts/fireworks/models/kimi-k2p6" not in ids

    def test_prices_shown_when_known(self) -> None:
        from ui.settings_dialog import _fireworks_model_entries

        entries = dict(_fireworks_model_entries([], builtin=True))
        label = entries["accounts/fireworks/models/gpt-oss-120b"]
        assert "$0.15" in label and "$0.60" in label


# ---------------------------------------------------------------------------
# Zero-config first launch
# ---------------------------------------------------------------------------

class TestBetaDefaults:
    def test_first_launch_defaults_to_fireworks(self, tmp_path, monkeypatch) -> None:
        from axiom import paths
        from core.builtin_keys import apply_beta_defaults

        monkeypatch.setenv("AXIOM_CONFIG_DIR", str(tmp_path))
        apply_beta_defaults()
        settings = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert settings["llm_backend"] == "fireworks"

    def test_existing_settings_left_alone(self, tmp_path, monkeypatch) -> None:
        from core.builtin_keys import apply_beta_defaults

        monkeypatch.setenv("AXIOM_CONFIG_DIR", str(tmp_path))
        (tmp_path / "settings.json").write_text(
            '{"llm_backend": "gemini"}', encoding="utf-8"
        )
        apply_beta_defaults()
        settings = json.loads((tmp_path / "settings.json").read_text(encoding="utf-8"))
        assert settings["llm_backend"] == "gemini"


# ---------------------------------------------------------------------------
# Master switch: retire the shared-key offering without deleting anything
# ---------------------------------------------------------------------------

class TestKillSwitch:
    """BUILTIN_KEYS_ENABLED = False turns the whole shared-key offering off
    (keys/code stay in place) so the expired beta pool can be retired by
    flipping one flag (TICKET-062 item 2 cleanup)."""

    def test_register_is_noop_when_disabled(self, monkeypatch) -> None:
        import core.builtin_keys as mod

        monkeypatch.setattr(mod, "BUILTIN_KEYS_ENABLED", False)
        mod.register_builtin_providers()
        assert get_builtin_keys("fireworks") == []

    def test_register_populates_pool_when_enabled(self, monkeypatch) -> None:
        import core.builtin_keys as mod

        monkeypatch.setattr(mod, "BUILTIN_KEYS_ENABLED", True)
        mod.register_builtin_providers()
        assert get_builtin_keys("fireworks") == fireworks_builtin_keys()

    def test_beta_default_skipped_when_disabled(self, tmp_path, monkeypatch) -> None:
        import core.builtin_keys as mod

        monkeypatch.setenv("AXIOM_CONFIG_DIR", str(tmp_path))
        monkeypatch.setattr(mod, "BUILTIN_KEYS_ENABLED", False)
        mod.apply_beta_defaults()
        # No settings written → fresh install keeps the standard backend default.
        assert not (tmp_path / "settings.json").exists()

    def test_disabled_pool_makes_fireworks_require_user_key(self, monkeypatch) -> None:
        """With the offering retired, a fireworks user with no key gets the
        clear 'add your key' error instead of silently using shared keys."""
        import core.builtin_keys as mod

        monkeypatch.setattr(mod, "BUILTIN_KEYS_ENABLED", False)
        mod.register_builtin_providers()
        cfg = AppConfig(llm_backend="fireworks", fireworks_api_key="")
        with pytest.raises(ValueError, match="no API key"):
            build_llm_from_config(cfg)
