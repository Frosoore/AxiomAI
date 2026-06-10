"""
core/paths.py

Centralised path management for Axiom AI.
Ensures cross-platform compatibility by using OS-specific standard directories.
"""

import os
import sys
from pathlib import Path

def get_app_config_dir() -> Path:
    """Return the standard directory for application configuration files."""
    if sys.platform == "win32":
        # %APPDATA%\AxiomAI
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "AxiomAI"
    # Fallback/Linux/macOS: ~/.config/AxiomAI
    return Path.home() / ".config" / "AxiomAI"

def get_app_cache_dir() -> Path:
    """Return the standard directory for non-essential data (logs, etc)."""
    if sys.platform == "win32":
        # %LOCALAPPDATA%\AxiomAI
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / "AxiomAI"
    # Fallback/Linux/macOS: ~/.cache/AxiomAI
    return Path.home() / ".cache" / "AxiomAI"

def get_app_data_dir() -> Path:
    """Return the standard directory for user-created content (universes, saves)."""
    # For AxiomAI, we keep universes in ~/AxiomAI to make them easy to find/backup for users
    return Path.home() / "AxiomAI"

# Shared Constants (machine-global defaults, computed once)
CONFIG_DIR = get_app_config_dir()
CACHE_DIR = get_app_cache_dir()
DATA_DIR = get_app_data_dir()

# Specific Files/Subdirs
SETTINGS_FILE = CONFIG_DIR / "settings.json"
GLOBAL_DB_FILE = CONFIG_DIR / "global.db"
LOG_DIR = CACHE_DIR / "logs"
UNIVERSES_DIR = DATA_DIR / "universes"
SAVES_DIR = DATA_DIR / "saves"
VECTOR_DIR = DATA_DIR / "vector"


# ---------------------------------------------------------------------------
# Path injection (Pilier 1, Étape 5)
#
# Two independent roots can be overridden so the engine is embeddable:
#   - data_dir   : per-game data (vector store, logs).
#   - config_dir : cross-cutting config (settings.json, global.db).
#
# Hybrid policy: if not configured, both fall back to the machine-global
# defaults above — so the GUI app is unchanged and an API key entered once is
# shared across universes. Embedders/tests opt into isolation explicitly, via
# configure(...) or the AXIOM_DATA_DIR / AXIOM_CONFIG_DIR environment variables.
# Resolution is lazy (getters below), never frozen at import.
# ---------------------------------------------------------------------------

_data_root_override: Path | None = None
_config_root_override: Path | None = None


def configure(*, data_dir: "str | os.PathLike | None" = None,
              config_dir: "str | os.PathLike | None" = None) -> None:
    """Inject path roots. Only the arguments provided are changed.

    Args:
        data_dir:   Root for per-game data (vector, logs). None leaves it.
        config_dir: Root for cross-cutting config (settings.json, global.db).
    """
    global _data_root_override, _config_root_override
    if data_dir is not None:
        _data_root_override = Path(data_dir)
    if config_dir is not None:
        _config_root_override = Path(config_dir)


def reset() -> None:
    """Clear all injected overrides (back to defaults / env). Used by tests."""
    global _data_root_override, _config_root_override
    _data_root_override = None
    _config_root_override = None


def _data_root() -> Path:
    if _data_root_override is not None:
        return _data_root_override
    env = os.environ.get("AXIOM_DATA_DIR")
    return Path(env) if env else DATA_DIR


def _config_root() -> Path:
    if _config_root_override is not None:
        return _config_root_override
    env = os.environ.get("AXIOM_CONFIG_DIR")
    return Path(env) if env else CONFIG_DIR


def has_config_override() -> bool:
    """True if a config root was injected (via configure or env var)."""
    return _config_root_override is not None or bool(os.environ.get("AXIOM_CONFIG_DIR"))


def get_vector_dir() -> Path:
    """Vector store root, honouring an injected/env data_dir."""
    return _data_root() / "vector"


def get_saves_dir() -> Path:
    """Racine des sauvegardes séparées (§7.6), honore data_dir injecté/env."""
    return _data_root() / "saves"


def get_log_dir() -> Path:
    """Log directory. Defaults to the machine-global cache root (legacy
    location); under an injected/env data_dir, logs move to ``<data_dir>/logs``."""
    if _data_root_override is not None or os.environ.get("AXIOM_DATA_DIR"):
        return _data_root() / "logs"
    return CACHE_DIR


def get_config_dir() -> Path:
    """Config directory, honouring an injected/env config_dir."""
    return _config_root()


def get_settings_file() -> Path:
    return _config_root() / "settings.json"


def get_global_db_file() -> Path:
    return _config_root() / "global.db"
