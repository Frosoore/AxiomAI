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
        llm_backend:         Active backend — "universal" or "gemini".
        universal_base_url:  Base URL for Universal API (e.g. OpenAI-compatible).
        universal_api_key:   Optional API key for Universal API.
        universal_model:     Model identifier for Universal API.
        gemini_api_key:      Google Gemini API key (may be empty).
        gemini_model:        Gemini model identifier.
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
        rag_chunk_count:     Number of memory chunks to retrieve for RAG.
        llm_requests_per_minute: Soft rate limit applied to Gemini calls
                             (TICKET-031). 0 = unlimited. Free tier example:
                             10 req/min per model — set 9 to stay under it.
        gemini_fallback_model: Model tried when the primary Gemini model is
                             still quota-exhausted (429) after retries.
                             Google quotas are per-model, so a different model
                             usually still has budget. Empty = no fallback.
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
    extraction_model: str = "llama3.1:8b"
    time_model: str = "llama3.2:1b"
    timekeeper_enabled: bool = True
    chronicler_interval: int = 50
    chronicler_minutes_interval: int = 720
    ui_font_size: int = 14
    enable_audio: bool = True
    rag_chunk_count: int = 5
    language: str = "en"
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


# Cache de load_config (QA-042.1) : tr() et les chemins chauds rechargent la
# config en boucle — sans cache, chaque appel relisait settings.json ET
# refaisait un connect sqlite (create_global_db). Invalidation par mtime du
# fichier, clé = chemin résolu (AXIOM_CONFIG_DIR injectable dans les tests).
_CONFIG_CACHE: dict[str, tuple[int, AppConfig]] = {}
_GLOBAL_DB_READY: set[str] = set()


def load_config() -> AppConfig:
    """Load configuration from the settings file.

    Returns sensible defaults if the file does not exist or is malformed.
    Never raises. Le résultat est mis en cache tant que le mtime du fichier
    ne change pas (`save_config` passe par le fichier : invalidation auto).

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
            pass

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


def resolve_extraction_model(config: AppConfig) -> str:
    """Pick the model name for auxiliary LLM calls (hero decision, extraction).

    `extraction_model` is an Ollama-style local model name; it only makes sense
    for the universal/Ollama backend. On the Gemini backend there is no separate
    local model, so sending `extraction_model` ("llama3.1:8b") to the Gemini API
    yields a 404. Fall back to the configured `gemini_model` in that case.
    """
    if config.llm_backend.lower().strip() == "gemini":
        return config.gemini_model
    return config.extraction_model


def resolve_time_model(config: AppConfig) -> str:
    """Return the correct time model identifier based on the active backend.
    
    If the backend is Gemini, the local time_model identifier cannot be used,
    so we fall back to the gemini_model.
    """
    if config.llm_backend.lower().strip() == "gemini":
        return config.gemini_model
    return config.time_model


def build_llm_from_config(config: AppConfig, model_override: str | None = None) -> LLMBackend:
    """Instantiate and return the correct LLMBackend for the given config.

    Args:
        config:         The current AppConfig.
        model_override: Optional model identifier to use instead of the default.

    Returns:
        A concrete LLMBackend instance ready for use.

    Raises:
        ValueError: If config.llm_backend is not "universal" or "gemini".
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

    if backend == "gemini":
        if not config.gemini_api_key:
            raise ValueError(
                "Gemini backend selected but no API key is configured. "
                "Add your key in File → Settings → Cloud (Gemini)."
            )
        return GeminiClient(
            api_key=config.gemini_api_key,
            model_name=model_override if model_override else config.gemini_model,
            requests_per_minute=config.llm_requests_per_minute,
            fallback_model=config.gemini_fallback_model,
        )

    raise ValueError(
        f"Unknown LLM backend: '{config.llm_backend}'. "
        "Expected 'universal' or 'gemini'."
    )
