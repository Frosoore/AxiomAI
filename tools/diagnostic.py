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


@dataclass
class CheckResult:
    """One diagnostic line."""
    name: str
    status: str  # OK | WARN | FAIL
    detail: str = ""


@dataclass
class Section:
    """A named group of checks."""
    title: str
    results: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.results.append(CheckResult(name, status, detail))


# ---------------------------------------------------------------------------
# Individual check groups — each returns a Section, never raises.
# ---------------------------------------------------------------------------

def _check_environment() -> Section:
    sec = Section("Environment")
    v = sys.version_info
    pyver = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= _MIN_PYTHON:
        sec.add("Python version", OK, pyver)
    else:
        sec.add("Python version", FAIL,
                f"{pyver} — Axiom needs ≥ {_MIN_PYTHON[0]}.{_MIN_PYTHON[1]}")
    sec.add("Platform", OK, f"{platform.system()} {platform.release()} ({platform.machine()})")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    sec.add("Virtualenv", OK if in_venv else WARN,
            sys.prefix if in_venv else "not running inside a virtualenv")
    return sec


def _check_packages() -> Section:
    sec = Section("Dependencies")
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
            sec.add(label, WARN, f"not importable: {exc}")
    return sec


def _check_embedding_runtime() -> Section:
    """Verify torch's native libraries actually LOAD (not just that it's installed).

    On Windows, torch ships fine via pip but its DLLs (torch_python.dll & co.)
    need the Microsoft Visual C++ Redistributable. Without it the import raises
    OSError (WinError 126) — semantic memory then silently degrades to a no-op
    (axiom/memory.py). This surfaces that as an actionable FAIL.
    """
    sec = Section("Embedding runtime")
    try:
        import torch  # noqa: F401
        sec.add("torch native libraries", OK, "loaded")
    except ImportError as exc:
        sec.add("torch native libraries", WARN,
                f"torch not installed ({exc}) — semantic memory will be disabled")
    except OSError as exc:  # e.g. WinError 126: a dependent DLL is missing
        hint = ""
        if sys.platform == "win32":
            hint = (" — install the Microsoft Visual C++ Redistributable (x64) from "
                    "microsoft.com (search 'vc_redist.x64.exe'), then relaunch")
        sec.add("torch native libraries", FAIL,
                f"installed but failed to load its native libraries: {exc}{hint}. "
                "Semantic memory stays disabled until fixed (the game still runs).")
    return sec


def _check_embedding_cache() -> Section:
    sec = Section("Embedding model")
    try:
        from huggingface_hub import try_to_load_from_cache
        # modules.json is small and always present in a complete snapshot.
        hit = try_to_load_from_cache(_EMBEDDING_REPO, "modules.json")
        if isinstance(hit, str) and Path(hit).exists():
            sec.add("all-MiniLM-L6-v2 cached", OK,
                    "loads offline (no HF Hub round-trip)")
        else:
            sec.add("all-MiniLM-L6-v2 cached", WARN,
                    "not cached yet — the first turn downloads it (~90 MB); "
                    "a slow/blocked network can make that first turn hang")
    except Exception as exc:  # noqa: BLE001
        sec.add("all-MiniLM-L6-v2 cached", WARN, f"could not check cache: {exc}")
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
    sec = Section("Configuration")
    try:
        from axiom.config import load_config, uses_builtin_keys
    except Exception as exc:  # noqa: BLE001
        sec.add("Load settings", FAIL, f"cannot import config: {exc}")
        return sec
    try:
        cfg = load_config()
    except Exception as exc:  # noqa: BLE001
        sec.add("Load settings", FAIL, f"settings unreadable: {exc}")
        return sec

    sec.add("Backend", OK, cfg.llm_backend)
    model, key_field = _backend_model_and_keyfield(cfg)
    sec.add("Model", OK, model)

    builtin = False
    try:
        builtin = uses_builtin_keys(cfg)
    except Exception:
        pass
    if builtin:
        sec.add("API key", OK, "using shared beta keys (no personal key set)")
    else:
        has_key = bool(str(getattr(cfg, key_field, "")).strip())
        sec.add("API key", OK if has_key else WARN,
                "personal key set" if has_key
                else "no key set for this backend — set one in Settings → Cloud")
    sec.add("Timekeeper", OK, "enabled" if cfg.timekeeper_enabled else "disabled")
    return sec


def _check_data_dirs() -> Section:
    sec = Section("Data directories")
    try:
        from axiom import paths
    except Exception as exc:  # noqa: BLE001
        sec.add("paths module", FAIL, f"not importable: {exc}")
        return sec
    targets = {
        "Config": paths.get_app_config_dir,
        "Saves": paths.get_saves_dir,
        "Vector store": paths.get_vector_dir,
        "Assets": paths.get_assets_dir,
    }
    for label, getter in targets.items():
        try:
            d = Path(getter())
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".diag_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            sec.add(label, OK, str(d))
        except Exception as exc:  # noqa: BLE001
            sec.add(label, FAIL, f"not writable: {exc}")
    return sec


def _check_backend(offline: bool) -> Section:
    sec = Section("Backend connectivity")
    if offline:
        sec.add("Reachability", WARN, "skipped (--offline)")
        return sec
    try:
        from axiom.config import load_config, build_llm_from_config
        cfg = load_config()
        llm = build_llm_from_config(cfg)
    except Exception as exc:  # noqa: BLE001
        sec.add("Build backend", FAIL, str(exc))
        return sec
    try:
        ok = bool(llm.is_available())
        sec.add("Reachability", OK if ok else FAIL,
                f"{cfg.llm_backend} responded" if ok
                else f"{cfg.llm_backend} did not respond — check the key/model/URL")
    except Exception as exc:  # noqa: BLE001
        sec.add("Reachability", FAIL, f"{cfg.llm_backend}: {exc}")
    return sec


def _run_test_batch(args: list[str], label: str) -> CheckResult:
    """Run one pytest invocation and summarise pass/fail from its return code."""
    try:
        env = dict(os.environ)
        # Skip the HF Hub network check during tests (axiom/memory.py fix).
        env.setdefault("HF_HUB_OFFLINE", "1")
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", *args, "-q", "--no-header"],
            cwd=str(_ROOT), capture_output=True, text=True, env=env, timeout=1800,
        )
    except FileNotFoundError:
        return CheckResult(label, WARN, "pytest not installed (pip install -r requirements-dev.txt)")
    except subprocess.TimeoutExpired:
        return CheckResult(label, FAIL, "timed out after 30 min")
    # pytest's last non-empty stdout line is the summary (e.g. "710 passed in …").
    summary = ""
    for line in reversed(proc.stdout.splitlines()):
        if line.strip():
            summary = line.strip().strip("=").strip()
            break
    status = OK if proc.returncode == 0 else FAIL
    return CheckResult(label, status, summary or f"exit code {proc.returncode}")


def _check_tests() -> Section:
    sec = Section("Test suite")
    # Two batches dodge the Qt-multimedia → triton segfault (TICKET-067):
    # everything except the audio test, then the audio test alone.
    sec.results.append(_run_test_batch(
        ["tests/", "--ignore=tests/test_ambiance_manager.py"], "Main batch"))
    sec.results.append(_run_test_batch(
        ["tests/test_ambiance_manager.py"], "Audio batch"))
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
        "Axiom AI — Diagnostic report",
        f"Engine version: {engine_version}",
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
    lines.append(f"Overall: {_GLYPH[overall_status(sections)]} {overall_status(sections)}")
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
    args = parser.parse_args(argv)

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
    raise SystemExit(main())
