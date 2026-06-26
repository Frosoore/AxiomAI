"""Tests for axiom/logger.py — debug mode, session log lifecycle, reconfigure."""

import logging
import tempfile
from pathlib import Path
from logging.handlers import RotatingFileHandler

import pytest
import axiom.logger as alog


@pytest.fixture(autouse=True)
def _isolate_logger():
    """Reset the logger between tests so handlers don't accumulate."""
    log = logging.getLogger("Axiom AI")
    log.handlers.clear()
    alog._is_debug = False
    alog._errors_occurred = False
    alog._session_log_path = None
    yield
    log.handlers.clear()
    alog._is_debug = False
    alog._errors_occurred = False
    alog._session_log_path = None


class TestSetupLogger:
    def test_creates_console_handler_at_info(self):
        alog.setup_logger()
        console = [h for h in logging.getLogger("Axiom AI").handlers
                   if isinstance(h, logging.StreamHandler)
                   and not isinstance(h, logging.FileHandler)]
        assert len(console) == 1
        assert console[0].level == logging.INFO

    def test_creates_rotating_file_handler_at_debug(self):
        alog.setup_logger()
        rotating = [h for h in logging.getLogger("Axiom AI").handlers
                    if isinstance(h, RotatingFileHandler)]
        assert len(rotating) == 1
        assert rotating[0].level == logging.DEBUG

    def test_creates_session_log_handler_at_error(self):
        alog.setup_logger()
        session = [h for h in logging.getLogger("Axiom AI").handlers
                   if isinstance(h, alog._SessionLogHandler)]
        assert len(session) == 1
        assert session[0].level == logging.ERROR

    def test_is_idempotent(self):
        a = alog.setup_logger()
        b = alog.setup_logger()
        assert a is b
        assert len(a.handlers) == len(b.handlers)


class TestDebugMode:
    def test_is_debug_false_by_default(self):
        assert alog.is_debug() is False

    def test_enable_debug_mode_sets_flag(self):
        alog.enable_debug_mode()
        assert alog.is_debug() is True

    def test_enable_debug_mode_upgrades_console_to_debug(self):
        alog.setup_logger()
        console = [h for h in logging.getLogger("Axiom AI").handlers
                   if isinstance(h, logging.StreamHandler)
                   and not isinstance(h, logging.FileHandler)][0]
        assert console.level == logging.INFO
        alog.enable_debug_mode()
        assert console.level == logging.DEBUG

    def test_enable_debug_mode_does_not_change_file_handlers(self):
        alog.setup_logger()
        rotating = [h for h in logging.getLogger("Axiom AI").handlers
                    if isinstance(h, RotatingFileHandler)][0]
        old_level = rotating.level
        alog.enable_debug_mode()
        assert rotating.level == old_level


class TestSessionLogLifecycle:
    def test_session_log_created_on_setup(self):
        import os
        tmp = Path(tempfile.mkdtemp())
        os.environ["AXIOM_DATA_DIR"] = str(tmp)
        try:
            alog.setup_logger()
            assert alog._session_log_path is not None
            assert alog._session_log_path.parent.exists()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
            del os.environ["AXIOM_DATA_DIR"]

    def test_session_log_deleted_on_clean_exit(self):
        import os
        tmp = Path(tempfile.mkdtemp())
        os.environ["AXIOM_DATA_DIR"] = str(tmp)
        try:
            alog.setup_logger()
            assert alog._session_log_path is not None
            alog._session_log_path.write_text("")
            alog._errors_occurred = False
            alog._cleanup_session_log()
            assert not alog._session_log_path.exists()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
            del os.environ["AXIOM_DATA_DIR"]

    def test_session_log_preserved_when_errors_occurred(self):
        import os
        tmp = Path(tempfile.mkdtemp())
        os.environ["AXIOM_DATA_DIR"] = str(tmp)
        try:
            alog.setup_logger()
            assert alog._session_log_path is not None
            alog._session_log_path.write_text("error content")
            alog._errors_occurred = True
            alog._cleanup_session_log()
            assert alog._session_log_path.exists()
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
            del os.environ["AXIOM_DATA_DIR"]

    def test_session_handler_sets_errors_occurred_on_emit(self):
        import os
        tmp = Path(tempfile.mkdtemp())
        os.environ["AXIOM_DATA_DIR"] = str(tmp)
        try:
            alog.setup_logger()
            alog._errors_occurred = False
            logging.getLogger("Axiom AI").error("test error")
            assert alog._errors_occurred is True
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
            del os.environ["AXIOM_DATA_DIR"]


class TestReconfigure:
    def test_reconfigure_repoints_file_handlers(self):
        import os
        tmp1 = Path(tempfile.mkdtemp())
        tmp2 = Path(tempfile.mkdtemp())
        os.environ["AXIOM_DATA_DIR"] = str(tmp1)
        try:
            alog.setup_logger()
            rotating_before = [h for h in logging.getLogger("Axiom AI").handlers
                               if isinstance(h, RotatingFileHandler)]
            session_before = [h for h in logging.getLogger("Axiom AI").handlers
                              if isinstance(h, alog._SessionLogHandler)]
            assert len(rotating_before) == 1
            assert len(session_before) == 1

            alog.reconfigure(log_dir=str(tmp2 / "logs"))

            rotating_after = [h for h in logging.getLogger("Axiom AI").handlers
                              if isinstance(h, RotatingFileHandler)]
            session_after = [h for h in logging.getLogger("Axiom AI").handlers
                             if isinstance(h, alog._SessionLogHandler)]
            assert len(rotating_after) == 1
            assert len(session_after) == 1
            assert rotating_after[0] is not rotating_before[0]
            assert session_after[0] is not session_before[0]
        finally:
            import shutil
            shutil.rmtree(tmp1, ignore_errors=True)
            shutil.rmtree(tmp2, ignore_errors=True)
            del os.environ["AXIOM_DATA_DIR"]
