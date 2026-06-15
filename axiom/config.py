"""
core/config.py

Application configuration model for Axiom AI.

Stores user preferences (LLM backend, model names, API keys, Chronicler
interval) in a JSON file at ~/.config/AxiomAI/settings.json.

This module is pure Python with no UI dependencies — it can be imported
by workers and backend code safely.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from axiom import paths
from axiom.backends.base import LLMBackend
from axiom.logger import logger
from axiom.paths import CONFIG_DIR, SETTINGS_FILE, GLOBAL_DB_FILE


_CONFIG_DIR: Path = CONFIG_DIR
_CONFIG_FILE: Path = SETTINGS_FILE
GLOBAL_DB_FILE: Path = GLOBAL_DB_FILE


# Resolution honours an injected config_dir (Étape 5) when set; otherwise falls
# back to the module-level globals above — which tests patch directly, and which
# default to the machine-global location (GUI behaviour unchanged).
def _resolve_config_dir() -> Path:
    return paths.get_config_dir() if paths.has_config_override() else _CONFIG_DIR


def _resolve_config_file() -> Path:
    return paths.get_settings_file() if paths.has_config_override() else _CONFIG_FILE


def _resolve_global_db_file() -> Path:
    return paths.get_global_db_file() if paths.has_config_override() else GLOBAL_DB_FILE


@dataclass
class AppConfig:
    """User preferences for Axiom AI.

    Attributes:
        llm_backend:         Active backend — "universal", "gemini", or one of
                             the OpenAI-compatible cloud providers: "claude",
                             "venice", "fireworks", "openai", "openrouter".
        universal_base_url:  Base URL for Universal API (e.g. OpenAI-compatible).
        universal_api_key:   Optional API key for Universal API.
        universal_model:     Model identifier for Universal API.
        gemini_api_key:      Google Gemini API key (may be empty).
        gemini_model:        Gemini model identifier.
        anthropic_api_key:   Anthropic API key for the "claude" backend.
        anthropic_model:     Claude model identifier (e.g. claude-opus-4-8).
        venice_api_key:      Venice AI API key for the "venice" backend.
        venice_model:        Venice AI model identifier.
        fireworks_api_key:   Fireworks AI API key for the "fireworks" backend.
        fireworks_model:     Fireworks AI model identifier.
        openai_api_key:      OpenAI API key for the "openai" backend.
        openai_model:        OpenAI model identifier.
        openrouter_api_key:  OpenRouter API key for the "openrouter" backend.
        openrouter_model:    OpenRouter model identifier (e.g. openrouter/auto).
        extraction_model:    Model used specifically for data extraction (Populate).
        time_model:          Model used by the Timekeeper to deduce elapsed time.
        timekeeper_enabled:  When True, a dedicated second LLM call (the Timekeeper)
                             deduces the in-game minutes elapsed each turn. When
                             False, that extra call is skipped and the time is
                             estimated from the scene pace alone (cheaper, less
                             precise). See Pilier 5 / TICKET-015.
        chronicler_interval: LEGACY — player turns between Chronicler runs. No
                             longer used for triggering (the Chronicler is now
                             driven by in-game minutes); kept for backward
                             compatibility with older settings files.
        chronicler_minutes_interval: In-game minutes between Chronicler runs. The
                             Chronicler fires once whenever the world clock crosses
                             a multiple of this value, so a single long time-skip
                             triggers exactly one off-screen simulation.
        ui_font_size:        Font size for the chat UI.
        enable_audio:        Whether background ambiance is enabled.
        doc_tooltips_enabled: Whether the GUI shows the documentation tooltips
                             when hovering interface elements (TICKET-057).
        rag_chunk_count:     Number of memory chunks to retrieve for RAG.
        llm_requests_per_minute: Soft rate limit applied to Gemini calls
                             (TICKET-031). 0 = unlimited. Free tier example:
                             10 req/min per model — set 9 to stay under it.
        gemini_fallback_model: Model tried when the primary Gemini model is
                             still quota-exhausted (429) after retries.
                             Google quotas are per-model, so a different model
                             usually still has budget. Empty = no fallback.
        basic_prompt:        Custom user-provided system instructions.
        image_generation_enabled: Whether narrative image generation is enabled.
        image_backend:       Image generation backend ("mock", "stable_diffusion", or "comfyui").
        image_api_url:       API base URL for the local image generator.
        image_width:         Generated image width in pixels.
        image_height:        Generated image height in pixels.
        image_steps:         Denoising steps for the image generation.
        image_cfg_scale:     Classifier Free Guidance scale.
        image_comfyui_workflow: Optional path to a ComfyUI workflow JSON file or a serialized workflow JSON string.
        image_gemini_model:  Gemini image model used by the "gemini" image backend.
        image_timeout:       Max seconds to wait for a local image backend
                             (SD WebUI request / ComfyUI polling) per image.
    """

    llm_backend: str = "universal"
    universal_base_url: str = "http://localhost:11434/v1"
    universal_api_key: str = ""
    universal_model: str = "llama3.2"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"
    venice_api_key: str = ""
    venice_model: str = "zai-org-glm-4.7"
    fireworks_api_key: str = ""
    # NB: Fireworks retires serverless models aggressively — an unknown model
    # = 404 on /chat/completions while /models still answers 200. deepseek-v3p1
    # (previous default) died that way; gpt-oss-120b verified live 2026-06-12,
    # and cheap enough for the built-in beta keys (TICKET-062).
    fireworks_model: str = "accounts/fireworks/models/gpt-oss-120b"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openrouter_api_key: str = ""
    openrouter_model: str = "openrouter/auto"
    extraction_model: str = "llama3.1:8b"
    time_model: str = "llama3.2:1b"
    timekeeper_enabled: bool = True
    chronicler_interval: int = 50
    chronicler_minutes_interval: int = 720
    ui_font_size: int = 14
    enable_audio: bool = True
    doc_tooltips_enabled: bool = True
    rag_chunk_count: int = 5
    language: str = "en"
    basic_prompt: str = ""
    llm_requests_per_minute: int = 0
    gemini_fallback_model: str = ""


    # Image generation settings
    image_generation_enabled: bool = False
    image_backend: str = "mock"
    image_api_url: str = "http://127.0.0.1:7860"
    image_width: int = 512
    image_height: int = 512
    image_steps: int = 20
    image_cfg_scale: float = 7.0
    image_comfyui_workflow: str = ""
    image_gemini_model: str = "gemini-2.5-flash-image"
    image_timeout: int = 180


# OpenAI-compatible cloud text providers selectable in the Cloud settings tab.
# Gemini keeps its own native client (quota resilience, fallback model); every
# provider below goes through UniversalClient with a preset base URL.
# value = (base_url, api-key field name, model field name, max stop sequences)
# Venice, Fireworks, OpenAI and OpenRouter all reject more than 4 "stop"
# sequences with a 400 (their /models endpoint answers fine, so the connection
# test passes and only real generation fails) — None = no documented limit.
OPENAI_COMPAT_PROVIDERS: dict[str, tuple[str, str, str, int | None]] = {
    "claude": ("https://api.anthropic.com/v1", "anthropic_api_key", "anthropic_model", None),
    "venice": ("https://api.venice.ai/api/v1", "venice_api_key", "venice_model", 4),
    "fireworks": ("https://api.fireworks.ai/inference/v1", "fireworks_api_key", "fireworks_model", 4),
    "openai": ("https://api.openai.com/v1", "openai_api_key", "openai_model", 4),
    "openrouter": ("https://openrouter.ai/api/v1", "openrouter_api_key", "openrouter_model", 4),
}

# Every cloud backend (the Cloud tab of the settings dialog).
CLOUD_BACKENDS: tuple[str, ...] = ("gemini", *OPENAI_COMPAT_PROVIDERS)


# ---------------------------------------------------------------------------
# Built-in key pools (TICKET-062)
#
# The published engine ships with NO key. An embedding application (the Axiom
# AI GUI during the public beta) can register a pool of shared keys for a
# provider; they are used — with automatic rotation on auth/quota errors —
# whenever the user has not entered their own key for that provider.
# Bearer-auth providers only (rotation swaps the Authorization header).
# ---------------------------------------------------------------------------

_BUILTIN_KEYS: dict[str, list[str]] = {}


def register_builtin_keys(provider: str, keys: list[str]) -> None:
    """Register shared fallback keys for an OpenAI-compatible provider.

    Args:
        provider: One of OPENAI_COMPAT_PROVIDERS (e.g. "fireworks").
        keys:     Ordered key pool; empty entries are dropped. An empty list
                  unregisters the provider.
    """
    cleaned = [k.strip() for k in keys if k and k.strip()]
    if cleaned:
        _BUILTIN_KEYS[provider] = cleaned
    else:
        _BUILTIN_KEYS.pop(provider, None)


def get_builtin_keys(provider: str) -> list[str]:
    """Return the registered key pool for a provider ([] when none)."""
    return list(_BUILTIN_KEYS.get(provider, []))


def uses_builtin_keys(config: AppConfig) -> bool:
    """True when the active backend will run on the registered shared keys
    (provider with a registered pool and no user key configured)."""
    backend = config.llm_backend.lower().strip()
    return (
        backend in OPENAI_COMPAT_PROVIDERS
        and not getattr(config, OPENAI_COMPAT_PROVIDERS[backend][1]).strip()
        and bool(_BUILTIN_KEYS.get(backend))
    )


# Cache de load_config (QA-042.1) : tr() et les chemins chauds rechargent la
# config en boucle — sans cache, chaque appel relisait settings.json ET
# refaisait un connect sqlite (create_global_db). Invalidation par mtime du
# fichier, clé = chemin résolu (AXIOM_CONFIG_DIR injectable dans les tests).
_CONFIG_CACHE: dict[str, tuple[int, AppConfig]] = {}
_GLOBAL_DB_READY: set[str] = set()


def load_config() -> AppConfig:
    """Load configuration from the settings file.

    Returns sensible defaults if the file does not exist or is malformed.
    Never raises. The result is cached as long as the file's mtime does not
    change (`save_config` goes through the file: automatic invalidation).

    Returns:
        AppConfig populated from disk, or a default AppConfig on any error.
    """
    from axiom.schema import create_global_db
    config_file = _resolve_config_file()

    global_db = str(_resolve_global_db_file())
    if global_db not in _GLOBAL_DB_READY:
        try:
            create_global_db(global_db)
            _GLOBAL_DB_READY.add(global_db)
        except Exception:
            # Best-effort: config still loads without the global DB (personas).
            # Trace it so a real provisioning failure isn't completely invisible.
            logger.debug("Global DB provisioning failed at %s.", global_db, exc_info=True)

    if not config_file.exists():
        _CONFIG_CACHE.pop(str(config_file), None)
        return AppConfig()

    try:
        mtime = config_file.stat().st_mtime_ns
    except OSError:
        mtime = -1
    cached = _CONFIG_CACHE.get(str(config_file))
    if cached is not None and cached[0] == mtime:
        return cached[1]

    try:
        raw = json.loads(config_file.read_text(encoding="utf-8"))
        # Migrate old ollama settings if universal is missing
        if "ollama_base_url" in raw and "universal_base_url" not in raw:
            old_url = raw.pop("ollama_base_url")
            # If they had the standard ollama URL, upgrade it to the /v1 endpoint
            if old_url.endswith("11434"):
                old_url += "/v1"
            elif old_url.endswith("11434/"):
                old_url += "v1"
            raw["universal_base_url"] = old_url
        if "ollama_model" in raw and "universal_model" not in raw:
            raw["universal_model"] = raw.pop("ollama_model")
        if raw.get("llm_backend") == "ollama":
            raw["llm_backend"] = "universal"

        # Only accept known keys — ignore unknown keys gracefully
        known = {f for f in AppConfig.__dataclass_fields__}
        filtered = {k: v for k, v in raw.items() if k in known}
        config = AppConfig(**filtered)
        _CONFIG_CACHE[str(config_file)] = (mtime, config)
        return config
    except Exception:
        return AppConfig()


def save_config(config: AppConfig) -> None:
    """Persist an AppConfig to the settings file.

    Creates the config directory if it does not exist.

    Args:
        config: The configuration to save.

    Raises:
        OSError: If the file cannot be written (propagated to the caller).
    """
    _resolve_config_dir().mkdir(parents=True, exist_ok=True)
    _resolve_config_file().write_text(
        json.dumps(asdict(config), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _cloud_main_model(config: AppConfig) -> str | None:
    """Main model of the active cloud backend, or None on universal/local."""
    backend = config.llm_backend.lower().strip()
    if backend == "gemini":
        return config.gemini_model
    if backend in OPENAI_COMPAT_PROVIDERS:
        return getattr(config, OPENAI_COMPAT_PROVIDERS[backend][2])
    return None


def resolve_extraction_model(config: AppConfig) -> str:
    """Pick the model name for auxiliary LLM calls (hero decision, extraction).

    `extraction_model` is an Ollama-style local model name; it only makes sense
    for the universal/Ollama backend. On a cloud backend (Gemini, Claude,
    Venice, Fireworks, OpenAI) there is no separate local model, so sending
    `extraction_model` ("llama3.1:8b") to the provider yields a 404. Fall back
    to the provider's main model in that case.
    """
    return _cloud_main_model(config) or config.extraction_model


def resolve_time_model(config: AppConfig) -> str:
    """Return the correct time model identifier based on the active backend.

    On a cloud backend the local time_model identifier cannot be used, so we
    fall back to the provider's main model.
    """
    return _cloud_main_model(config) or config.time_model


def build_llm_from_config(config: AppConfig, model_override: str | None = None) -> LLMBackend:
    """Instantiate and return the correct LLMBackend for the given config.

    Args:
        config:         The current AppConfig.
        model_override: Optional model identifier to use instead of the default.

    Returns:
        A concrete LLMBackend instance ready for use.

    Raises:
        ValueError: If config.llm_backend is not "universal", "gemini", or one
            of the OpenAI-compatible cloud providers (claude, venice,
            fireworks, openai, openrouter).
    """
    from axiom.backends.universal import UniversalClient
    from axiom.backends.gemini import GeminiClient

    backend = config.llm_backend.lower().strip()

    # Treat old "ollama" config as "universal"
    if backend == "ollama" or backend == "universal":
        return UniversalClient(
            base_url=config.universal_base_url,
            api_key=config.universal_api_key,
            model_name=model_override if model_override else config.universal_model,
        )

    if backend in OPENAI_COMPAT_PROVIDERS:
        base_url, key_field, model_field, max_stops = OPENAI_COMPAT_PROVIDERS[backend]
        api_key = getattr(config, key_field).strip()
        fallback_keys: list[str] = []
        if not api_key:
            # No user key: fall back to the registered shared pool, with the
            # remaining keys as rotation spares (TICKET-062).
            builtin = get_builtin_keys(backend)
            if builtin:
                api_key, fallback_keys = builtin[0], builtin[1:]
            else:
                raise ValueError(
                    f"'{backend}' backend selected but no API key is configured. "
                    "Add your key in File → Settings → Cloud."
                )
        extra_headers = None
        if backend == "claude":
            # Anthropic's OpenAI-compat layer accepts the native x-api-key on
            # /chat/completions, and GET /models (connection test) accepts
            # ONLY it (a bare Bearer is rejected) — authenticate natively and
            # skip the Authorization header.
            extra_headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
            api_key = ""
        elif backend == "openrouter":
            # Optional attribution headers (shown in OpenRouter dashboards).
            extra_headers = {"X-Title": "Axiom AI"}
        return UniversalClient(
            base_url=base_url,
            api_key=api_key,
            model_name=model_override if model_override else getattr(config, model_field),
            extra_headers=extra_headers,
            max_stop_sequences=max_stops,
            fallback_api_keys=fallback_keys,
        )

    if backend == "gemini":
        if not config.gemini_api_key:
            raise ValueError(
                "Gemini backend selected but no API key is configured. "
                "Add your key in File → Settings → Cloud."
            )
        return GeminiClient(
            api_key=config.gemini_api_key,
            model_name=model_override if model_override else config.gemini_model,
            requests_per_minute=config.llm_requests_per_minute,
            fallback_model=config.gemini_fallback_model,
        )

    raise ValueError(
        f"Unknown LLM backend: '{config.llm_backend}'. "
        f"Expected 'universal' or one of: {', '.join(CLOUD_BACKENDS)}."
    )
