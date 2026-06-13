"""
ui/diagnostic_dialog.py

TICKET-062 item 4 — the in-app "Help → Diagnostic" dialog.

A thin GUI over tools.diagnostic: it runs the health checks (off the main
thread via DiagnosticWorker), shows a copyable report, and lets the tester
optionally run the full test suite, copy the report to the clipboard, or save
it to a file to attach to a bug report. All diagnostic logic lives in
tools/diagnostic.py — this is presentation only.
"""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from core.localization import tr
from workers.diagnostic_worker import DiagnosticWorker


class DiagnosticDialog(QDialog):
    """Runs and displays the self-diagnostic report."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("diagnostic_title"))
        self.setMinimumSize(620, 560)
        self._worker: DiagnosticWorker | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("diagnostic_intro")))

        self._report = QPlainTextEdit()
        self._report.setReadOnly(True)
        self._report.setFont(QFont("monospace"))
        self._report.setPlainText(tr("diagnostic_running"))
        layout.addWidget(self._report)

        # Action buttons.
        actions = QHBoxLayout()
        self._refresh_btn = QPushButton(tr("diagnostic_refresh"))
        self._refresh_btn.clicked.connect(lambda: self._start(run_tests=False))
        self._tests_btn = QPushButton(tr("diagnostic_run_tests"))
        self._tests_btn.clicked.connect(lambda: self._start(run_tests=True))
        self._copy_btn = QPushButton(tr("diagnostic_copy"))
        self._copy_btn.clicked.connect(self._copy)
        self._save_btn = QPushButton(tr("diagnostic_save"))
        self._save_btn.clicked.connect(self._save)
        for btn in (self._refresh_btn, self._tests_btn, self._copy_btn, self._save_btn):
            actions.addWidget(btn)
        actions.addStretch()
        layout.addLayout(actions)

        self._status = QLabel("")
        layout.addWidget(self._status)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

        # Auto-run the fast health checks on open.
        self._start(run_tests=False)

    # ------------------------------------------------------------------

    def _set_busy(self, busy: bool) -> None:
        for btn in (self._refresh_btn, self._tests_btn, self._copy_btn, self._save_btn):
            btn.setEnabled(not busy)
        self._status.setText(tr("diagnostic_running") if busy else "")

    def _start(self, *, run_tests: bool) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self._set_busy(True)
        if run_tests:
            self._report.setPlainText(tr("diagnostic_running_tests"))
        self._worker = DiagnosticWorker(run_tests=run_tests)
        self._worker.report_ready.connect(self._on_report)
        self._worker.start()

    def _on_report(self, report: str, overall: str) -> None:  # noqa: ARG002
        self._report.setPlainText(report)
        self._set_busy(False)

    def _copy(self) -> None:
        QApplication.clipboard().setText(self._report.toPlainText())
        self._status.setText(tr("diagnostic_copied"))

    def _save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, tr("diagnostic_save"), "axiom_diagnostic.txt", "Text (*.txt)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(self._report.toPlainText() + "\n")
            self._status.setText(tr("diagnostic_saved"))
        except OSError as exc:
            self._status.setText(f"{exc}")
