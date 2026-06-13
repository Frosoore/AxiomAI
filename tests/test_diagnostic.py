"""
tests/test_diagnostic.py

Unit tests for tools/diagnostic.py — the beta self-diagnostic.

Network-free: the backend reachability check is exercised via --offline, the
test-suite runner via a mocked subprocess. Data-dir writes are redirected to a
tmp path so the real config is never touched.
"""

import json
import subprocess
from types import SimpleNamespace

import pytest

from tools import diagnostic as D


@pytest.fixture(autouse=True)
def _sandbox_dirs(tmp_path, monkeypatch):
    """Redirect config + data roots to tmp so checks never touch real dirs."""
    monkeypatch.setenv("AXIOM_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("AXIOM_DATA_DIR", str(tmp_path / "data"))
    yield


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestOverallStatus:
    def _sections(self, *statuses):
        sec = D.Section("S")
        for i, s in enumerate(statuses):
            sec.add(f"c{i}", s)
        return [sec]

    def test_all_ok(self):
        assert D.overall_status(self._sections(D.OK, D.OK)) == D.OK

    def test_warn_beats_ok(self):
        assert D.overall_status(self._sections(D.OK, D.WARN)) == D.WARN

    def test_fail_beats_warn(self):
        assert D.overall_status(self._sections(D.WARN, D.FAIL, D.OK)) == D.FAIL

    def test_empty_is_ok(self):
        assert D.overall_status([]) == D.OK


class TestReportFormatting:
    def test_report_has_sections_and_overall(self):
        sec = D.Section("Demo")
        sec.add("thing", D.OK, "fine")
        sec.add("other", D.FAIL, "broken")
        report = D.format_report([sec])
        assert "[Demo]" in report
        assert "thing" in report and "fine" in report
        assert "Overall:" in report and D.FAIL in report

    def test_json_is_valid_and_structured(self):
        sec = D.Section("Demo")
        sec.add("thing", D.WARN, "meh")
        payload = json.loads(D._to_json([sec]))
        assert payload["overall"] == D.WARN
        assert payload["sections"][0]["title"] == "Demo"
        assert payload["sections"][0]["results"][0]["name"] == "thing"


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

class TestChecks:
    def test_environment_reports_python_ok(self):
        sec = D._check_environment()
        names = {r.name for r in sec.results}
        assert "Python version" in names and "Platform" in names
        py = next(r for r in sec.results if r.name == "Python version")
        assert py.status == D.OK  # the test runner is on a supported Python

    def test_offline_backend_is_skipped(self):
        sec = D._check_backend(offline=True)
        assert sec.results[0].status == D.WARN
        assert "skipped" in sec.results[0].detail

    def test_data_dirs_are_writable_in_sandbox(self):
        sec = D._check_data_dirs()
        assert all(r.status == D.OK for r in sec.results), [
            (r.name, r.detail) for r in sec.results
        ]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

class TestRunDiagnostics:
    def test_offline_run_has_core_sections_no_tests(self):
        sections = D.run_diagnostics(run_tests=False, offline=True)
        titles = [s.title for s in sections]
        assert "Configuration" in titles and "Backend connectivity" in titles
        assert "Test suite" not in titles

    def test_run_tests_appends_test_section(self, monkeypatch):
        # Don't actually launch pytest — stub the batch runner.
        monkeypatch.setattr(
            D, "_check_tests",
            lambda: D.Section("Test suite", [D.CheckResult("Main batch", D.OK, "1 passed")]),
        )
        sections = D.run_diagnostics(run_tests=True, offline=True)
        assert sections[-1].title == "Test suite"


# ---------------------------------------------------------------------------
# Test-suite batch runner (mocked subprocess)
# ---------------------------------------------------------------------------

class TestTestBatchRunner:
    def test_passing_batch_is_ok(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(
            returncode=0, stdout="710 passed in 12.3s\n", stderr=""))
        r = D._run_test_batch(["tests/"], "Main")
        assert r.status == D.OK and "710 passed" in r.detail

    def test_failing_batch_is_fail(self, monkeypatch):
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: SimpleNamespace(
            returncode=1, stdout="3 failed, 700 passed in 12s\n", stderr=""))
        r = D._run_test_batch(["tests/"], "Main")
        assert r.status == D.FAIL and "failed" in r.detail

    def test_missing_pytest_is_warn(self, monkeypatch):
        def _boom(*a, **k):
            raise FileNotFoundError()
        monkeypatch.setattr(subprocess, "run", _boom)
        r = D._run_test_batch(["tests/"], "Main")
        assert r.status == D.WARN and "pytest" in r.detail


# ---------------------------------------------------------------------------
# CLI entry point — exit code mirrors severity
# ---------------------------------------------------------------------------

class TestMainExitCode:
    def test_exit_zero_on_ok(self, monkeypatch, capsys):
        monkeypatch.setattr(D, "run_diagnostics",
                            lambda **k: [D.Section("S", [D.CheckResult("c", D.OK)])])
        assert D.main([]) == 0

    def test_exit_two_on_fail(self, monkeypatch):
        monkeypatch.setattr(D, "run_diagnostics",
                            lambda **k: [D.Section("S", [D.CheckResult("c", D.FAIL)])])
        assert D.main([]) == 2

    def test_json_flag_outputs_json(self, monkeypatch, capsys):
        monkeypatch.setattr(D, "run_diagnostics",
                            lambda **k: [D.Section("S", [D.CheckResult("c", D.WARN)])])
        D.main(["--json"])
        out = capsys.readouterr().out
        assert json.loads(out)["overall"] == D.WARN

    def test_output_file_written(self, monkeypatch, tmp_path):
        monkeypatch.setattr(D, "run_diagnostics",
                            lambda **k: [D.Section("S", [D.CheckResult("c", D.OK)])])
        out = tmp_path / "report.txt"
        D.main(["--output", str(out)])
        assert out.exists() and "Overall" in out.read_text(encoding="utf-8")
