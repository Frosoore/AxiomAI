"""
ui/diagnostic_dialog.py

TICKET-062 item 4 — the in-app "Help → Diagnostic" dialog.

A thin GUI over tools.diagnostic: it runs the health checks (off the main
thread via DiagnosticWorker), shows a copyable report, and lets the tester
optionally run the full test suite, copy the report to the clipboard, or save
it to a file to attach to a bug report. All diagnostic logic lives in
tools/diagnostic.py — this is presentation only.

When the test suite runs, two extra buttons open dedicated, copyable windows:
one listing every warning, one with the full log of the failed tests — the
report itself only shows counts/names.
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


class _TextWindow(QDialog):
    """A simple read-only window showing a block of text with a Copy button.

    Used for the warnings list and the failed-tests log: both can be long, so
    they get their own scrollable, copyable window instead of cramming the
    report.
    """

    def __init__(self, title: str, text: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(720, 520)

        layout = QVBoxLayout(self)
        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        self._view.setFont(QFont("monospace"))
        self._view.setPlainText(text)
        layout.addWidget(self._view)

        actions = QHBoxLayout()
        self._copy_btn = QPushButton(tr("diagnostic_copy_all"))
        self._copy_btn.clicked.connect(self._copy)
        actions.addWidget(self._copy_btn)
        self._copied = QLabel("")
        actions.addWidget(self._copied)
        actions.addStretch()
        layout.addLayout(actions)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)

    def _copy(self) -> None:
        QApplication.clipboard().setText(self._view.toPlainText())
        self._copied.setText(tr("diagnostic_copied"))


class DiagnosticDialog(QDialog):
    """Runs and displays the self-diagnostic report."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("diagnostic_title"))
        self.setMinimumSize(620, 560)
        self._worker: DiagnosticWorker | None = None
        # Raw texts from the last test run, shown in their own windows.
        self._warnings_text = ""
        self._failures_text = ""
        # Keep references so child windows aren't garbage-collected while open.
        self._child_windows: list[_TextWindow] = []

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

        # Second row: open the warnings / failed-tests windows (only meaningful
        # after a test run, so disabled until there's something to show).
        detail_actions = QHBoxLayout()
        self._warnings_btn = QPushButton(tr("diagnostic_view_warnings"))
        self._warnings_btn.clicked.connect(self._show_warnings)
        self._failures_btn = QPushButton(tr("diagnostic_view_failures"))
        self._failures_btn.clicked.connect(self._show_failures)
        self._warnings_btn.setEnabled(False)
        self._failures_btn.setEnabled(False)
        for btn in (self._warnings_btn, self._failures_btn):
            detail_actions.addWidget(btn)
        detail_actions.addStretch()
        layout.addLayout(detail_actions)

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
        # A fresh run invalidates the previous warnings/failures.
        self._warnings_text = ""
        self._failures_text = ""
        self._warnings_btn.setEnabled(False)
        self._failures_btn.setEnabled(False)
        if run_tests:
            self._report.setPlainText(tr("diagnostic_running_tests"))
        self._worker = DiagnosticWorker(run_tests=run_tests)
        self._worker.report_ready.connect(self._on_report)
        # The fake worker used in tests may not expose this signal.
        if hasattr(self._worker, "artifacts_ready"):
            self._worker.artifacts_ready.connect(self._on_artifacts)
        self._worker.start()

    def _on_report(self, report: str, overall: str) -> None:  # noqa: ARG002
        self._report.setPlainText(report)
        self._set_busy(False)

    def _on_artifacts(self, warnings: str, failures: str) -> None:
        self._warnings_text = warnings
        self._failures_text = failures
        self._warnings_btn.setEnabled(bool(warnings))
        self._failures_btn.setEnabled(bool(failures))

    def _open_text_window(self, title: str, text: str) -> None:
        win = _TextWindow(title, text, self)
        self._child_windows.append(win)
        win.finished.connect(lambda _=0, w=win: self._child_windows.remove(w)
                             if w in self._child_windows else None)
        win.show()

    def _show_warnings(self) -> None:
        if self._warnings_text:
            self._open_text_window(tr("diagnostic_view_warnings"), self._warnings_text)

    def _show_failures(self) -> None:
        if self._failures_text:
            self._open_text_window(tr("diagnostic_view_failures"), self._failures_text)

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
