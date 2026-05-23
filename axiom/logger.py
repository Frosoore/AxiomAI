"""
core/logger.py

Centralised logging for Axiom AI.
Provides a unified logger that writes to both console and a persistent file.
"""

import sys
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

from axiom import paths

_LOG_NAME = "axiom_ai.log"


def _resolve_log_file() -> Path:
    """Current log file path, resolved lazily from the (possibly injected) log dir."""
    return paths.get_log_dir() / _LOG_NAME


def _add_file_handler(logger: logging.Logger, log_file: Path) -> None:
    """Attach a rotating file handler writing to ``log_file`` (best-effort)."""
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            str(log_file), maxBytes=1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
        ))
        logger.addHandler(file_handler)
    except OSError:
        # Fallback if file logging is impossible
        print(f"Warning: Could not initialize file logging at {log_file}", file=sys.stderr)


def setup_logger(name: str = "Axiom AI") -> logging.Logger:
    """Initialize and return the global Axiom AI logger."""
    logger = logging.getLogger(name)

    # Avoid duplicate handlers if already setup
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # 1. Console Handler (INFO level)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(console)

    # 2. File Handler (DEBUG level, Rotating) — path resolved lazily.
    _add_file_handler(logger, _resolve_log_file())

    return logger


def reconfigure(name: str = "Axiom AI", log_dir: "str | Path | None" = None) -> logging.Logger:
    """Re-point the file handler after a path injection.

    Removes the current rotating file handler (if any) and attaches a new one
    under ``log_dir`` (or, if None, the lazily-resolved ``paths.get_log_dir()``).
    The console handler is left intact. Used by `Session(data_dir=...)`.
    """
    logger = logging.getLogger(name)
    for handler in list(logger.handlers):
        if isinstance(handler, RotatingFileHandler):
            logger.removeHandler(handler)
            handler.close()
    target = Path(log_dir) / _LOG_NAME if log_dir is not None else _resolve_log_file()
    _add_file_handler(logger, target)
    return logger


# Singleton instance for easy access
logger = setup_logger()
