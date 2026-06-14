"""
tests/test_diagnostic_dialog.py

GUI tests for the in-app diagnostic (TICKET-062 item 4): the DiagnosticWorker
and the DiagnosticDialog. The real network/test-suite logic lives in
tools/diagnostic.py (covered by test_diagnostic.py); here we mock it so these
tests stay fast and offline.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QObject, Signal

from tools import diagnostic as D


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class TestDiagnosticWorker:
    def test_run_emits_formatted_report(self, monkeypatch):
        from workers.diagnostic_worker import DiagnosticWorker

        sec = D.Section("S", [D.CheckResult("c", D.WARN, "d")])
        monkeypatch.setattr(D, "run_diagnostics", lambda **k: [sec])

        worker = DiagnosticWorker(run_tests=False)
        got: list[tuple[str, str]] = []
        worker.report_ready.connect(lambda r, o: got.append((r, o)))
        worker.run()  # synchronous: exercise the body without a real thread

        assert len(got) == 1
        report, overall = got[0]
        assert overall == D.WARN
        assert "[S]" in report and "Overall" in report

    def test_run_passes_flags_through(self, monkeypatch):
        from workers.diagnostic_worker import DiagnosticWorker

        seen = {}
        monkeypatch.setattr(D, "run_diagnostics",
                            lambda **k: seen.update(k) or [D.Section("S")])
        DiagnosticWorker(run_tests=True, offline=True).run()
        assert seen == {"run_tests": True, "offline": True}

    def test_run_never_raises(self, monkeypatch):
        from workers.diagnostic_worker import DiagnosticWorker

        def _boom(**k):
            raise RuntimeError("kaboom")
        monkeypatch.setattr(D, "run_diagnostics", _boom)

        worker = DiagnosticWorker()
        got: list[tuple[str, str]] = []
        worker.report_ready.connect(lambda r, o: got.append((r, o)))
        worker.run()

        assert got and got[0][1] == "FAIL" and "kaboom" in got[0][0]


# ---------------------------------------------------------------------------
# Dialog — fake worker so construction never spawns a thread or hits network
# ---------------------------------------------------------------------------

class _FakeWorker(QObject):
    report_ready = Signal(str, str)
    artifacts_ready = Signal(str, str)

    def __init__(self, **kwargs) -> None:
        super().__init__()
        self.kwargs = kwargs

    def isRunning(self) -> bool:
        return False

    def start(self) -> None:  # no-op: tests drive the signals manually
        pass


@pytest.fixture
def dialog(monkeypatch):
    monkeypatch.setattr("ui.diagnostic_dialog.DiagnosticWorker", _FakeWorker)
    from ui.diagnostic_dialog import DiagnosticDialog
    dlg = DiagnosticDialog()
    yield dlg
    dlg.deleteLater()


class TestDiagnosticDialog:
    def test_constructs_and_auto_starts(self, dialog):
        # The fake start() is a no-op, so the placeholder text is still showing.
        assert dialog.windowTitle()
        assert dialog._worker is not None
        assert dialog._worker.kwargs == {"run_tests": False}

    def test_report_updates_widget_and_reenables(self, dialog):
        dialog._set_busy(True)
        dialog._worker.report_ready.emit("FULL REPORT", "OK")
        assert dialog._report.toPlainText() == "FULL REPORT"
        assert dialog._refresh_btn.isEnabled()
        assert dialog._tests_btn.isEnabled()

    def test_run_tests_button_requests_tests(self, dialog):
        dialog._start(run_tests=True)
        assert dialog._worker.kwargs == {"run_tests": True}

    def test_copy_puts_report_on_clipboard(self, dialog):
        from PySide6.QtWidgets import QApplication
        dialog._worker.report_ready.emit("COPY ME", "OK")
        dialog._copy()
        assert QApplication.clipboard().text() == "COPY ME"

    def test_detail_buttons_disabled_without_artifacts(self, dialog):
        # No test run yet → nothing to show.
        assert not dialog._warnings_btn.isEnabled()
        assert not dialog._failures_btn.isEnabled()

    def test_artifacts_enable_only_relevant_buttons(self, dialog):
        # Warnings present, no failures.
        dialog._worker.artifacts_ready.emit("some warnings", "")
        assert dialog._warnings_btn.isEnabled()
        assert not dialog._failures_btn.isEnabled()
        # Both present.
        dialog._worker.artifacts_ready.emit("w", "the failure log")
        assert dialog._warnings_btn.isEnabled()
        assert dialog._failures_btn.isEnabled()

    def test_show_failures_opens_window_with_text(self, dialog):
        dialog._worker.artifacts_ready.emit("", "FULL TRACEBACK HERE")
        dialog._show_failures()
        assert dialog._child_windows, "a child window should have opened"
        win = dialog._child_windows[-1]
        assert "FULL TRACEBACK HERE" in win._view.toPlainText()
        win.close()

    def test_child_window_copy_all(self, dialog):
        from PySide6.QtWidgets import QApplication
        dialog._worker.artifacts_ready.emit("warn A\nwarn B", "")
        dialog._show_warnings()
        win = dialog._child_windows[-1]
        win._copy()
        assert QApplication.clipboard().text() == "warn A\nwarn B"
        win.close()
