"""mods/axiom.providers/main.py

Official mod: axiom.providers (LLM Drivers & Inference Providers)
Provides:
1. Native inference drivers for Gemini, Ollama, Universal OpenAI-compatible endpoints.
2. Extensible slot 'axiom.providers:drivers' (collect) allowing third-party mods to add new AI providers.
3. Exclusive slot contribution 'axiom.turn:llm_backend' resolving the active LLM backend.
4. Public service 'providers' for connectivity testing and model listing.
"""

from __future__ import annotations

from typing import Any, Callable

from axiom.backends.base import LLMBackend
from axiom.config import AppConfig, load_config
from axiom.kernel.context import ModContext
from axiom.kernel.registry import SlotRule
from axiom.logger import logger


def gemini_driver(cfg: AppConfig, model_override: str | None = None) -> LLMBackend:
    """Driver builder for Google Gemini."""
    from axiom.backends.gemini import GeminiClient
    key = cfg.gemini_api_key.strip()
    if not key:
        from axiom.config import get_builtin_keys
        builtin = get_builtin_keys("gemini")
        key = builtin[0] if builtin else ""
    return GeminiClient(
        api_key=key,
        model_name=model_override or cfg.gemini_model,
        requests_per_minute=getattr(cfg, "llm_requests_per_minute", 0),
        fallback_model=getattr(cfg, "gemini_fallback_model", None) or None,
    )


def universal_driver(cfg: AppConfig, model_override: str | None = None) -> LLMBackend:
    """Driver builder for Ollama / Universal OpenAI-compatible local endpoints."""
    from axiom.backends.universal import UniversalClient
    return UniversalClient(
        base_url=cfg.universal_base_url,
        api_key=cfg.universal_api_key,
        model_name=model_override or cfg.universal_model,
    )


class ProvidersService:
    """Public service exposed by axiom.providers."""

    def __init__(self, ctx: ModContext | None = None) -> None:
        self._ctx = ctx
        self._drivers: dict[str, Callable[[AppConfig, str | None], LLMBackend]] = {}

    def register_driver(self, name: str, builder: Callable[[AppConfig, str | None], LLMBackend]) -> None:
        self._drivers[name.lower().strip()] = builder

    def get_driver(self, name: str) -> Callable[[AppConfig, str | None], LLMBackend] | None:
        clean = name.lower().strip()
        if clean in self._drivers:
            return self._drivers[clean]

        # Check registered drivers via slot contributions
        if self._ctx is not None:
            for contrib in self._ctx.get_slot_contributions("axiom.providers:drivers"):
                if isinstance(contrib, tuple) and len(contrib) == 2:
                    d_name, builder = contrib
                    if str(d_name).lower().strip() == clean:
                        return builder
                elif isinstance(contrib, dict):
                    if str(contrib.get("id", "")).lower().strip() == clean:
                        return contrib.get("builder")

        return None

    def list_drivers(self) -> list[str]:
        drivers = set(self._drivers.keys())
        if self._ctx is not None:
            for contrib in self._ctx.get_slot_contributions("axiom.providers:drivers"):
                if isinstance(contrib, tuple) and len(contrib) == 2:
                    drivers.add(str(contrib[0]).lower().strip())
                elif isinstance(contrib, dict) and "id" in contrib:
                    drivers.add(str(contrib["id"]).lower().strip())
        return sorted(list(drivers))

    def get_backend(self, config: AppConfig | None = None, model_override: str | None = None) -> LLMBackend:
        cfg = config or load_config()
        backend_name = (getattr(cfg, "llm_backend", "") or "universal").lower().strip()
        driver = self.get_driver(backend_name)
        if driver is not None:
            return driver(cfg, model_override)

        # Fallback to config builder for known legacy or cloud providers
        from axiom.config import build_llm_from_config
        return build_llm_from_config(cfg, model_override=model_override)

    def test_connection(self, driver_name: str, config: AppConfig | None = None) -> bool:
        """Test connectivity of a given driver."""
        try:
            cfg = config or load_config()
            driver = self.get_driver(driver_name)
            if driver:
                backend = driver(cfg, None)
                if hasattr(backend, "test_connection") and callable(backend.test_connection):
                    return bool(backend.test_connection())
            return True
        except Exception as exc:
            logger.debug("[axiom.providers] Connectivity test failed for '%s': %s", driver_name, exc)
            return False

    def list_models(self, driver_name: str, config: AppConfig | None = None) -> list[str]:
        """List available models for a given driver."""
        try:
            cfg = config or load_config()
            driver = self.get_driver(driver_name)
            if driver:
                backend = driver(cfg, None)
                if hasattr(backend, "list_models") and callable(backend.list_models):
                    return list(backend.list_models())
        except Exception:
            pass
        return []


_SERVICE: ProvidersService | None = None


def get_providers_service(ctx: ModContext | None = None) -> ProvidersService:
    """The service of the last loaded instance of this mod (a new one per init)."""
    global _SERVICE
    if _SERVICE is None or (ctx is not None and _SERVICE._ctx is not ctx):
        _SERVICE = ProvidersService(ctx)
    return _SERVICE


def resolve_llm_backend(step_ctx: Any = None) -> LLMBackend:
    """Slot resolver for axiom.turn:llm_backend."""
    svc = get_providers_service()
    return svc.get_backend()


def init(ctx: ModContext) -> None:
    """Entry point for axiom.providers mod."""
    svc = get_providers_service(ctx)

    # 1. Declare slot for drivers
    ctx.declare_slot("axiom.providers:drivers", SlotRule.COLLECT)

    # 2. Register native drivers
    svc.register_driver("gemini", gemini_driver)
    svc.register_driver("ollama", universal_driver)
    svc.register_driver("universal", universal_driver)

    ctx.contribute_slot("axiom.providers:drivers", ("gemini", gemini_driver))
    ctx.contribute_slot("axiom.providers:drivers", ("ollama", universal_driver))
    ctx.contribute_slot("axiom.providers:drivers", ("universal", universal_driver))

    # 3. Register service
    ctx.register_service("providers", svc)

    # 4. Contribute to axiom.turn:llm_backend (bound to this instance's service)
    ctx.contribute_slot("axiom.turn:llm_backend", lambda step_ctx=None: svc.get_backend())

    # 5. Register settings tab contributions
    try:
        from mods.axiom.providers.ui.providers_settings_tabs import (
            UniversalLLMSettingsTab,
            CloudSettingsTab,
        )
        ctx.contribute_slot("axiom.ui.qt:settings_tab", UniversalLLMSettingsTab)
        ctx.contribute_slot("axiom.ui.qt:settings_tab", CloudSettingsTab)
    except Exception as exc:
        logger.debug("[axiom.providers] Could not load settings tabs: %s", exc)

