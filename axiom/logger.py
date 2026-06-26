"""
axiom/logger.py

Centralised logging for Axiom AI.

Two modes:
  --debug       Developer mode: console shows DEBUG, full verbosity.
  (default)     User mode: console shows INFO. ERROR/CRITICAL written to a
                session log file that is auto-deleted on graceful exit.

A rotating persistent log (DEBUG, 1 MB x 5) is always active.
"""

import sys
import atexit
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

from axiom import paths

_LOG_NAME = "axiom_ai.log"
_SESSION_LOG_NAME = "axiom_session.log"

_is_debug = False
_errors_occurred = False
_session_log_path: Path | None = None


def _resolve_log_file() -> Path:
    return paths.get_log_dir() / _LOG_NAME


def _resolve_session_log_file() -> Path:
    return paths.get_log_dir() / _SESSION_LOG_NAME


def _add_rotating_handler(logger: logging.Logger, log_file: Path, level: int = logging.DEBUG) -> None:
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            str(log_file), maxBytes=1024 * 1024, backupCount=5, encoding="utf-8"
        )
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
        ))
        logger.addHandler(handler)
    except OSError:
        print(f"Warning: Could not initialize file logging at {log_file}", file=sys.stderr)


class _SessionLogHandler(logging.FileHandler):
    """FileHandler that tracks whether any record was emitted.

    Used for the session log: if no ERROR/CRITICAL was logged during the
    session, the file is deleted on graceful exit.
    """

    def emit(self, record: logging.LogRecord) -> None:
        global _errors_occurred
        _errors_occurred = True
        super().emit(record)


def _cleanup_session_log() -> None:
    global _errors_occurred, _session_log_path
    if _session_log_path is not None and _session_log_path.exists() and not _errors_occurred:
        try:
            _session_log_path.unlink()
        except OSError:
            pass


def _add_session_handler(logger: logging.Logger, log_file: Path) -> None:
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handler = _SessionLogHandler(str(log_file), encoding="utf-8")
        handler.setLevel(logging.ERROR)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
        ))
        logger.addHandler(handler)
    except OSError:
        print(f"Warning: Could not initialize session logging at {log_file}", file=sys.stderr)


def setup_logger(name: str = "Axiom AI") -> logging.Logger:
    """Initialize and return the global Axiom AI logger."""
    global _session_log_path
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # 1. Console handler (INFO by default, upgraded to DEBUG in debug mode)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logger.addHandler(console)

    # 2. Persistent rotating file handler (always DEBUG)
    _add_rotating_handler(logger, _resolve_log_file(), logging.DEBUG)

    # 3. Session log handler (ERROR+CRITICAL, auto-cleaned on graceful exit)
    _session_log_path = _resolve_session_log_file()
    _add_session_handler(logger, _session_log_path)

    atexit.register(_cleanup_session_log)

    return logger


def enable_debug_mode(name: str = "Axiom AI") -> None:
    """Switch console output to DEBUG level for developer use."""
    global _is_debug
    _is_debug = True
    logger = logging.getLogger(name)
    for handler in logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setLevel(logging.DEBUG)


def is_debug() -> bool:
    """Return True if debug mode is active."""
    return _is_debug


def reconfigure(name: str = "Axiom AI", log_dir: "str | Path | None" = None) -> logging.Logger:
    """Re-point the file handlers after a path injection.

    Removes the current rotating file handler and session handler (if any) and
    attaches new ones under ``log_dir`` (or, if None, the lazily-resolved
    ``paths.get_log_dir()``). The console handler is left intact.
    """
    global _session_log_path
    logger = logging.getLogger(name)
    for handler in list(logger.handlers):
        if isinstance(handler, (RotatingFileHandler, _SessionLogHandler)):
            logger.removeHandler(handler)
            handler.close()
    target = Path(log_dir) / _LOG_NAME if log_dir is not None else _resolve_log_file()
    _add_rotating_handler(logger, target)
    _session_log_path = Path(log_dir) / _SESSION_LOG_NAME if log_dir is not None else _resolve_session_log_file()
    _add_session_handler(logger, _session_log_path)
    return logger


logger = setup_logger()
