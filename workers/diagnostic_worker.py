"""
workers/diagnostic_worker.py

QThread shell around tools.diagnostic.run_diagnostics() (TICKET-062 item 4).

The diagnostic performs a network call (backend reachability) and may launch
the test suite as a subprocess, so it MUST run off the main thread. This worker
runs it and emits the finished report + overall status as Qt signals; the GUI
dialog (ui/diagnostic_dialog.py) renders them.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class DiagnosticWorker(QThread):
    """Runs the self-diagnostic off the main thread.

    Signals:
        report_ready(str, str): (formatted text report, overall status string).

    Args:
        run_tests: Also run the pytest suite (2 batches) — slow.
        offline:   Skip the network/backend reachability check.
    """

    report_ready = Signal(str, str)

    def __init__(self, *, run_tests: bool = False, offline: bool = False) -> None:
        super().__init__()
        self._run_tests = run_tests
        self._offline = offline

    def run(self) -> None:
        """Run every check and emit the report.  Never raises."""
        from tools.diagnostic import run_diagnostics, format_report, overall_status
        try:
            sections = run_diagnostics(run_tests=self._run_tests, offline=self._offline)
            self.report_ready.emit(format_report(sections), overall_status(sections))
        except Exception as exc:  # noqa: BLE001 — a diagnostic must never crash the app
            self.report_ready.emit(f"Diagnostic failed to run: {exc}", "FAIL")
