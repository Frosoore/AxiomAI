"""
tools/diagnostic.py

Axiom AI self-diagnostic — fast health checks (+ optional test suite).

Designed for beta testers: it runs WITHOUT the GUI and prints a copyable
report they can paste into a bug report. The same `run_diagnostics()` function
backs the in-app "Help → Diagnostic" dialog (added later), so the logic lives
here once.

Usage
-----
    python -m tools.diagnostic            # fast health checks (~seconds)
    python -m tools.diagnostic --tests    # + the pytest suite, in 2 batches
    python -m tools.diagnostic --offline  # skip the network/backend check
    python -m tools.diagnostic --json     # machine-readable output

What it checks (each → OK / WARN / FAIL, never crashes the whole report):
  * Python & OS, virtualenv.
  * Versions of the heavy dependencies (torch, chromadb, PySide6, …).
  * Whether torch's native libraries actually LOAD (on Windows a missing MS
    Visual C++ Redistributable makes the import fail and disables memory).
  * Whether the embedding model is already cached (a cold first turn otherwise
    downloads it; on a broken-IPv6 host that stall is what makes the narrative
    seem to never arrive — see axiom/memory.py).
  * The saved config: backend, model, whether a key is set (never its value),
    Timekeeper, shared-beta-key mode.
  * That the data directories are writable.
  * That the configured LLM backend actually answers (the #1 cause of "it
    doesn't work").
  * Optionally, the test suite (split into 2 batches to dodge the known
    Qt-multimedia/triton segfault, TICKET-067).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Make the project root importable when run as a loose script.
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

OK = "OK"
WARN = "WARN"
FAIL = "FAIL"

_GLYPH = {OK: "✅", WARN: "⚠️ ", FAIL: "❌"}

# Minimum supported Python (matches pyproject / run.sh — tomllib floor).
_MIN_PYTHON = (3, 11)
# Heavy deps worth reporting a version for (import name → friendly label).
_REPORTED_PACKAGES: dict[str, str] = {
    "torch": "torch",
    "chromadb": "chromadb",
    "sentence_transformers": "sentence-transformers",
    "PySide6": "PySide6",
    "httpx": "httpx",
    "google.genai": "google-genai",
    "requests": "requests",
}
# Embedding model repo (see axiom/memory.py::_EMBEDDING_MODEL).
_EMBEDDING_REPO = "sentence-transformers/all-MiniLM-L6-v2"


def _tr(key: str, **kwargs) -> str:
    """Localize a report string, tolerant of an engine-only context.

    The report content (section titles, check names, sentence-form details) is
    translated into the app's current language. Pure data — versions, paths,
    model ids, backend names, raw exception messages — is left as-is by the
    callers (it isn't language). If the app's i18n layer can't be imported (a
    bare engine checkout), we fall back to the key so the report still renders.
    """
    try:
        from core.localization import tr
        return tr(key, **kwargs)
    except Exception:  # noqa: BLE001 — diagnostics must never crash
        return key


def _maybe_reexec_in_venv() -> None:
    """Re-launch this diagnostic inside the project's virtualenv when needed.

    The #1 reason ``python -m tools.diagnostic`` looks broken is that a tester
    runs it with the *system* interpreter: the heavy deps (torch, chromadb,
    google-genai, …) live in the project's ``.venv`` (created by run.sh/run.bat),
    so every dependency check screams "not importable" even though the app runs
    fine. The app itself always runs from ``.venv``, so the diagnostic should
    reflect THAT environment.

    If the project ``.venv`` exists and we aren't already its interpreter, we
    ``exec`` the venv's python on this very file (by path, so the current working
    directory doesn't matter). ``AXIOM_DIAG_REEXEC`` guards against any loop, and
    ``--no-venv`` opts out entirely.
    """
    if os.environ.get("AXIOM_DIAG_REEXEC") == "1":
        return
    if "--no-venv" in sys.argv:
        return
    # Candidate interpreter inside the project venv (POSIX then Windows layout).
    candidates = [
        _ROOT / ".venv" / "bin" / "python",
        _ROOT / ".venv" / "bin" / "python3",
        _ROOT / ".venv" / "Scripts" / "python.exe",
    ]
    venv_py = next((p for p in candidates if p.exists()), None)
    if venv_py is None:
        return  # no project venv → run in place (deps may be installed globally)
    # Are we already running *from* this venv? Compare prefixes, not the resolved
    # executables: a venv's bin/python is a symlink to the base interpreter, so
    # resolving it would wrongly equate the venv with the bare system python.
    venv_dir = (_ROOT / ".venv").resolve()
    try:
        already_in_venv = Path(sys.prefix).resolve() == venv_dir
    except OSError:
        already_in_venv = False
    if already_in_venv:
        return  # already the right interpreter
    env = dict(os.environ)
    env["AXIOM_DIAG_REEXEC"] = "1"
    print(_tr("diag_using_venv", path=str(venv_py)), file=sys.stderr)
    try:
        os.execve(str(venv_py), [str(venv_py), str(Path(__file__).resolve()),
                                 *sys.argv[1:]], env)
    except OSError as exc:  # exec failed → carry on with the current interpreter
        print(_tr("diag_venv_reexec_failed", exc=exc), file=sys.stderr)


@dataclass
class CheckResult:
    """One diagnostic line."""
    name: str
    status: str  # OK | WARN | FAIL
    detail: str = ""


@dataclass
class Section:
    """A named group of checks.

    `warnings_text` / `failures_text` carry the *full* pytest warning summary
    and failure logs for the test-suite section, so the GUI can show them in
    their own copyable windows (the report only shows counts/names).
    """
    title: str
    results: list[CheckResult] = field(default_factory=list)
    warnings_text: str = ""
    failures_text: str = ""

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.results.append(CheckResult(name, status, detail))


# ---------------------------------------------------------------------------
# Individual check groups — each returns a Section, never raises.
# ---------------------------------------------------------------------------

def _check_environment() -> Section:
    sec = Section(_tr("diag_sec_environment"))
    v = sys.version_info
    pyver = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= _MIN_PYTHON:
        sec.add(_tr("diag_check_python"), OK, pyver)
    else:
        sec.add(_tr("diag_check_python"), FAIL,
                _tr("diag_python_too_old", pyver=pyver,
                    min=f"{_MIN_PYTHON[0]}.{_MIN_PYTHON[1]}"))
    sec.add(_tr("diag_check_platform"), OK,
            f"{platform.system()} {platform.release()} ({platform.machine()})")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    sec.add(_tr("diag_check_venv"), OK if in_venv else WARN,
            sys.prefix if in_venv else _tr("diag_venv_none"))
    return sec


def _check_packages() -> Section:
    sec = Section(_tr("diag_sec_dependencies"))
    import importlib
    for module_name, label in _REPORTED_PACKAGES.items():
        try:
            mod = importlib.import_module(module_name)
            version = getattr(mod, "__version__", None)
            if version is None:
                # google.genai exposes its version on the top package.
                top = importlib.import_module(module_name.split(".")[0])
                version = getattr(top, "__version__", "present")
            sec.add(label, OK, str(version))
        except Exception as exc:  # noqa: BLE001 — report, never abort
            sec.add(label, WARN, _tr("diag_not_importable", exc=exc))
    return sec


def _check_embedding_runtime() -> Section:
    """Verify torch's native libraries actually LOAD (not just that it's installed).

    On Windows, torch ships fine via pip but its DLLs (torch_python.dll & co.)
    need the Microsoft Visual C++ Redistributable. Without it the import raises
    OSError (WinError 126) — semantic memory then silently degrades to a no-op
    (axiom/memory.py). This surfaces that as an actionable FAIL.
    """
    sec = Section(_tr("diag_sec_embedding_runtime"))
    try:
        import torch  # noqa: F401
        sec.add(_tr("diag_check_torch_native"), OK, _tr("diag_torch_loaded"))
    except ImportError as exc:
        sec.add(_tr("diag_check_torch_native"), WARN,
                _tr("diag_torch_not_installed", exc=exc))
    except OSError as exc:  # e.g. WinError 126: a dependent DLL is missing
        hint = _tr("diag_torch_hint_win") if sys.platform == "win32" else ""
        sec.add(_tr("diag_check_torch_native"), FAIL,
                _tr("diag_torch_load_failed", exc=exc, hint=hint))
    return sec


def _check_embedding_cache() -> Section:
    sec = Section(_tr("diag_sec_embedding_model"))
    try:
        from huggingface_hub import try_to_load_from_cache
        # modules.json is small and always present in a complete snapshot.
        hit = try_to_load_from_cache(_EMBEDDING_REPO, "modules.json")
        if isinstance(hit, str) and Path(hit).exists():
            sec.add(_tr("diag_check_embedding_cached"), OK, _tr("diag_embed_offline"))
        else:
            sec.add(_tr("diag_check_embedding_cached"), WARN, _tr("diag_embed_not_cached"))
    except Exception as exc:  # noqa: BLE001
        sec.add(_tr("diag_check_embedding_cached"), WARN,
                _tr("diag_embed_cache_error", exc=exc))
    return sec


def _backend_model_and_keyfield(cfg) -> tuple[str, str]:
    """Resolve the active backend's model id and the config attribute that
    holds its API key (mirrors build_llm_from_config's branching)."""
    from axiom.config import OPENAI_COMPAT_PROVIDERS
    backend = cfg.llm_backend.lower().strip()
    if backend in OPENAI_COMPAT_PROVIDERS:
        _, key_field, model_field, _ = OPENAI_COMPAT_PROVIDERS[backend]
        return str(getattr(cfg, model_field, "?")), key_field
    if backend == "gemini":
        return str(getattr(cfg, "gemini_model", "?")), "gemini_api_key"
    return str(getattr(cfg, "universal_model", "?")), "universal_api_key"


def _check_config() -> Section:
    sec = Section(_tr("diag_sec_configuration"))
    try:
        from axiom.config import load_config, uses_builtin_keys
    except Exception as exc:  # noqa: BLE001
        sec.add(_tr("diag_check_load_settings"), FAIL,
                _tr("diag_cfg_import_error", exc=exc))
        return sec
    try:
        cfg = load_config()
    except Exception as exc:  # noqa: BLE001
        sec.add(_tr("diag_check_load_settings"), FAIL,
                _tr("diag_cfg_unreadable", exc=exc))
        return sec

    sec.add(_tr("diag_check_backend"), OK, cfg.llm_backend)
    model, key_field = _backend_model_and_keyfield(cfg)
    sec.add(_tr("diag_check_model"), OK, model)

    builtin = False
    try:
        builtin = uses_builtin_keys(cfg)
    except Exception:
        pass
    if builtin:
        sec.add(_tr("diag_check_api_key"), OK, _tr("diag_key_builtin"))
    else:
        has_key = bool(str(getattr(cfg, key_field, "")).strip())
        sec.add(_tr("diag_check_api_key"), OK if has_key else WARN,
                _tr("diag_key_personal") if has_key else _tr("diag_key_none"))
    sec.add(_tr("diag_check_timekeeper"), OK,
            _tr("diag_timekeeper_enabled") if cfg.timekeeper_enabled
            else _tr("diag_timekeeper_disabled"))
    return sec


def _check_data_dirs() -> Section:
    sec = Section(_tr("diag_sec_data_dirs"))
    try:
        from axiom import paths
    except Exception as exc:  # noqa: BLE001
        sec.add(_tr("diag_check_paths_module"), FAIL,
                _tr("diag_not_importable", exc=exc))
        return sec
    targets = {
        "diag_dir_config": paths.get_app_config_dir,
        "diag_dir_saves": paths.get_saves_dir,
        "diag_dir_vector": paths.get_vector_dir,
        "diag_dir_assets": paths.get_assets_dir,
    }
    for key, getter in targets.items():
        try:
            d = Path(getter())
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".diag_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            sec.add(_tr(key), OK, str(d))
        except Exception as exc:  # noqa: BLE001
            sec.add(_tr(key), FAIL, _tr("diag_not_writable", exc=exc))
    return sec


def _check_backend(offline: bool) -> Section:
    sec = Section(_tr("diag_sec_backend"))
    if offline:
        sec.add(_tr("diag_check_reachability"), WARN, _tr("diag_backend_skipped"))
        return sec
    try:
        from axiom.config import load_config, build_llm_from_config
        cfg = load_config()
        llm = build_llm_from_config(cfg)
    except Exception as exc:  # noqa: BLE001
        sec.add(_tr("diag_check_build_backend"), FAIL, str(exc))
        return sec
    try:
        ok = bool(llm.is_available())
        sec.add(_tr("diag_check_reachability"), OK if ok else FAIL,
                _tr("diag_backend_responded", backend=cfg.llm_backend) if ok
                else _tr("diag_backend_no_response", backend=cfg.llm_backend))
    except Exception as exc:  # noqa: BLE001
        sec.add(_tr("diag_check_reachability"), FAIL, f"{cfg.llm_backend}: {exc}")
    return sec


@dataclass
class _BatchOutcome:
    """What one pytest batch produced: the report lines plus the raw texts the
    GUI shows in dedicated windows (warnings summary, full failure log)."""
    results: list[CheckResult]
    warnings: str = ""
    log: str = ""


def _extract_warnings_block(stdout: str) -> str:
    """Return pytest's 'warnings summary' section verbatim (without its header),
    or "" if there were no warnings. pytest prints it even on a passing run."""
    out: list[str] = []
    collecting = False
    for line in stdout.splitlines():
        stripped = line.strip()
        is_header = bool(re.match(r"^=+ .* =+$", stripped))
        if is_header and "warnings summary" in stripped:
            collecting = True
            continue
        if collecting:
            # The block ends at the "-- Docs:" footer or the next section header.
            if stripped.startswith("-- Docs:") or is_header:
                break
            out.append(line)
    return "\n".join(out).strip()


def _run_test_batch(args: list[str], label: str) -> _BatchOutcome:
    """Run one pytest invocation and report pass/fail.

    The first result line is the summary; on failure, one extra line per
    failing/erroring test (so a tester sees *which* tests broke, not just a
    count). `warnings`/`log` carry the full texts the GUI opens in their own
    copyable windows.
    """
    try:
        env = dict(os.environ)
        # Skip the HF Hub network check during tests (axiom/memory.py fix).
        env.setdefault("HF_HUB_OFFLINE", "1")
        proc = subprocess.run(
            # -rfE → a "short test summary info" block listing FAILED/ERROR
            # node ids, which we parse below for the per-test detail lines.
            [sys.executable, "-m", "pytest", *args, "-q", "--no-header", "-rfE"],
            cwd=str(_ROOT), capture_output=True, text=True, env=env, timeout=1800,
        )
    except FileNotFoundError:
        return _BatchOutcome([CheckResult(label, WARN, _tr("diag_pytest_missing"))])
    except subprocess.TimeoutExpired:
        return _BatchOutcome([CheckResult(label, FAIL, _tr("diag_pytest_timeout"))])

    # pytest's last non-empty stdout line is the summary (e.g. "710 passed in …").
    summary = ""
    for line in reversed(proc.stdout.splitlines()):
        if line.strip():
            summary = line.strip().strip("=").strip()
            break
    status = OK if proc.returncode == 0 else FAIL
    results = [CheckResult(label, status, summary or f"exit code {proc.returncode}")]
    warnings = _extract_warnings_block(proc.stdout)
    log = ""

    if status != OK:
        # Failure: surface each failing/erroring test by node id. The -rfE
        # summary lines look like "FAILED tests/x.py::test - AssertionError: …"
        # or "ERROR tests/y.py - ImportError: …"; keep the reason, drop prefix.
        for line in proc.stdout.splitlines():
            stripped = line.strip()
            for prefix, tag in (("FAILED ", "failed"), ("ERROR ", "error")):
                if stripped.startswith(prefix):
                    results.append(CheckResult(stripped[len(prefix):].strip(), FAIL, tag))
                    break
        # The full output (tracebacks included) is the "log" the GUI shows and
        # that we also drop on disk for the CLI / a bug report.
        log = (proc.stdout or "") + (
            "\n--- stderr ---\n" + proc.stderr if proc.stderr else "")
        try:
            safe = "".join(c if c.isalnum() else "_" for c in label).lower()
            log_path = Path(tempfile.gettempdir()) / f"axiom_diag_{safe}.log"
            log_path.write_text(log, encoding="utf-8")
            results.append(CheckResult(_tr("diag_check_full_log"), WARN, str(log_path)))
        except OSError:
            pass

    return _BatchOutcome(results, warnings, log)


def _check_tests() -> Section:
    sec = Section(_tr("diag_sec_tests"))
    warnings_blocks: list[str] = []
    log_blocks: list[str] = []
    # Two batches dodge the Qt-multimedia → triton segfault (TICKET-067):
    # everything except the audio test, then the audio test alone.
    for args, label in (
        (["tests/", "--ignore=tests/test_ambiance_manager.py"], _tr("diag_test_main_batch")),
        (["tests/test_ambiance_manager.py"], _tr("diag_test_audio_batch")),
    ):
        outcome = _run_test_batch(args, label)
        sec.results.extend(outcome.results)
        if outcome.warnings:
            warnings_blocks.append(f"===== {label} =====\n{outcome.warnings}")
        if outcome.log:
            log_blocks.append(f"===== {label} =====\n{outcome.log}")
    sec.warnings_text = "\n\n".join(warnings_blocks)
    sec.failures_text = "\n\n".join(log_blocks)
    return sec


# ---------------------------------------------------------------------------
# Orchestration + reporting
# ---------------------------------------------------------------------------

def run_diagnostics(*, run_tests: bool = False, offline: bool = False) -> list[Section]:
    """Run every health check and return the sections (GUI + CLI share this)."""
    # Mirror the app's startup so the config/backend checks see the SAME runtime
    # a real launch would: register the shared beta-key pool (a zero-config
    # tester relies on it — without this the backend check would falsely fail on
    # "no API key"). Never applies beta defaults: diagnostics must not mutate
    # settings.
    try:
        from core.builtin_keys import register_builtin_providers
        register_builtin_providers()
    except Exception:  # noqa: BLE001 — engine-only context: just skip
        pass

    sections = [
        _check_environment(),
        _check_packages(),
        _check_embedding_runtime(),
        _check_embedding_cache(),
        _check_config(),
        _check_data_dirs(),
        _check_backend(offline),
    ]
    if run_tests:
        sections.append(_check_tests())
    return sections


def collect_artifacts(sections: list[Section]) -> tuple[str, str]:
    """Aggregate the full warnings text and failure logs across all sections.

    Returns ``(warnings_text, failures_text)`` — either may be "" when there is
    nothing to show. The GUI uses these to populate its 'Warnings' and 'Failed
    tests' windows.
    """
    warnings = "\n\n".join(s.warnings_text for s in sections if s.warnings_text)
    failures = "\n\n".join(s.failures_text for s in sections if s.failures_text)
    return warnings, failures


def overall_status(sections: list[Section]) -> str:
    """Worst status across all checks (FAIL > WARN > OK)."""
    statuses = [r.status for sec in sections for r in sec.results]
    if FAIL in statuses:
        return FAIL
    if WARN in statuses:
        return WARN
    return OK


def format_report(sections: list[Section]) -> str:
    """Render a copyable plain-text report."""
    from axiom import __version__ as engine_version
    lines = [
        _tr("diag_report_title"),
        _tr("diag_report_engine_version", version=engine_version),
        "=" * 50,
    ]
    for sec in sections:
        lines.append("")
        lines.append(f"[{sec.title}]")
        for r in sec.results:
            glyph = _GLYPH.get(r.status, "?")
            detail = f"  ({r.detail})" if r.detail else ""
            lines.append(f"  {glyph} {r.name}{detail}")
    lines.append("")
    lines.append("=" * 50)
    overall = overall_status(sections)
    lines.append(f"{_tr('diag_report_overall')} {_GLYPH[overall]} {overall}")
    return "\n".join(lines)


def _to_json(sections: list[Section]) -> str:
    payload = {
        "overall": overall_status(sections),
        "sections": [
            {"title": s.title, "results": [asdict(r) for r in s.results]}
            for s in sections
        ],
    }
    return json.dumps(payload, indent=2)


def _run_gui() -> int:
    """Open the standalone graphical diagnostic window and block until closed.

    Reuses the in-app DiagnosticDialog so the GUI and the menu entry stay
    identical. Returns 0 on a clean open, 1 if the GUI stack is unavailable
    (e.g. PySide6 missing or no display) — the message tells the tester to fall
    back to the text mode.
    """
    try:
        from PySide6.QtWidgets import QApplication
        from ui.diagnostic_dialog import DiagnosticDialog
    except Exception as exc:  # noqa: BLE001
        print(_tr("diag_gui_unavailable", exc=exc), file=sys.stderr)
        return 1
    app = QApplication.instance() or QApplication(sys.argv)
    DiagnosticDialog().exec()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tools.diagnostic",
        description="Axiom AI self-diagnostic (health checks + optional tests).",
    )
    parser.add_argument("--tests", action="store_true",
                        help="also run the pytest suite (2 batches, slower)")
    parser.add_argument("--offline", action="store_true",
                        help="skip the network/backend reachability check")
    parser.add_argument("--json", action="store_true",
                        help="machine-readable JSON output")
    parser.add_argument("--output", metavar="FILE",
                        help="also write the report to FILE")
    parser.add_argument("--gui", action="store_true",
                        help="open the graphical diagnostic window (same checks, "
                             "with buttons to run the tests / copy / save)")
    parser.add_argument("--no-venv", action="store_true",
                        help="do not auto-switch to the project's .venv interpreter "
                             "(diagnose the current interpreter as-is)")
    args = parser.parse_args(argv)

    # --gui: launch the standalone diagnostic window. It shares ALL its logic
    # with the in-app "Help → Diagnostic" dialog (ui/diagnostic_dialog.py), so a
    # tester gets the exact same report — failed-test list and log path included
    # — whether they open it from Axiom or run this from a terminal.
    if args.gui:
        return _run_gui()

    # The report uses ✅/⚠️/❌ glyphs. On Windows a redirected/piped stdout
    # defaults to cp1252 and would crash on those with UnicodeEncodeError;
    # force UTF-8 (errors="replace" as a last resort on exotic streams).
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

    sections = run_diagnostics(run_tests=args.tests, offline=args.offline)
    report = _to_json(sections) if args.json else format_report(sections)
    print(report)
    if args.output:
        try:
            Path(args.output).write_text(report + "\n", encoding="utf-8")
        except OSError as exc:
            print(f"(could not write {args.output}: {exc})", file=sys.stderr)
    # Exit code mirrors severity: 0 OK, 1 WARN, 2 FAIL — handy for scripts/CI.
    return {OK: 0, WARN: 1, FAIL: 2}[overall_status(sections)]


if __name__ == "__main__":
    # Before anything else, make sure we're the project venv's interpreter so the
    # dependency/backend checks reflect the environment the app actually runs in
    # (a tester running this with the bare system python is the #1 false alarm).
    # Done here (not in main()) so programmatic callers / tests never re-exec.
    _maybe_reexec_in_venv()
    raise SystemExit(main())
