"""
tests/test_vector_threading.py

Regression test for the torch+Qt segfault hit on the first narrative turn.

Root cause: the embedding model's first encode runs on a worker QThread and
lazily dlopen()s libtriton.so; doing that off the main thread under Qt is a
native segfault. Fix: `axiom.memory.preload_embedding_runtime()`, called on the
main thread at startup (see main.py), forces that dlopen onto the main thread.

A segfault kills the whole process, so we cannot assert it in-process: we run
the realistic GUI threading scenario in a subprocess and check its exit code.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCENARIO = Path(__file__).resolve().parent / "_vector_qthread_scenario.py"

# Heavy native deps; skip cleanly where they (or Qt) are unavailable.
pytest.importorskip("torch", reason="torch required for the embedding runtime")
pytest.importorskip("PySide6.QtMultimedia", reason="Qt multimedia required")
pytest.importorskip("chromadb", reason="chromadb required for VectorMemory")


def _run_scenario(mode: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    return subprocess.run(
        [sys.executable, str(_SCENARIO), mode],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


def test_vector_query_on_qthread_under_qt_does_not_segfault() -> None:
    """With the main-thread preload, a turn's vector ops survive under Qt.

    This is the path a real narrative turn takes (model built on one worker
    thread, queried/embedded on another while QtMultimedia is live). It must
    exit cleanly — a negative return code means a native crash (segfault).
    """
    result = _run_scenario("preload")
    assert result.returncode == 0, (
        f"Scenario crashed (returncode={result.returncode}). "
        f"A negative code is a native segfault.\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
