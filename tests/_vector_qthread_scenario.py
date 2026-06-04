"""
tests/_vector_qthread_scenario.py

Subprocess payload for `tests/test_vector_threading.py`.

Reproduces, headless (QT_QPA_PLATFORM=offscreen), the exact threading shape of a
real GUI turn that used to segfault:

  * a QApplication is running, with QtMultimedia audio players live (ambiance);
  * VectorMemory (sentence-transformers / torch) is built on one QThread
    (like VectorInitWorker);
  * it is then queried + embedded on another QThread (like NarrativeWorker),
    whose first encode lazily dlopen()s libtriton.so.

That off-main-thread dlopen under Qt is a native segfault. The fix is to call
`axiom.memory.preload_embedding_runtime()` on the MAIN thread first.

Usage:
    python tests/_vector_qthread_scenario.py preload     # expect clean exit 0
    python tests/_vector_qthread_scenario.py nopreload   # may segfault (pre-fix)
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "preload"

    if mode == "preload":
        # The fix under test: front-load torch's native runtime on the main thread.
        from axiom.memory import preload_embedding_runtime
        preload_embedding_runtime()

    from PySide6.QtCore import QThread, QTimer
    from PySide6.QtWidgets import QApplication
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
    from axiom.memory import VectorMemory

    app = QApplication(sys.argv)

    # Mimic AmbianceManager: live multimedia players + audio outputs.
    out = QAudioOutput()
    player = QMediaPlayer()
    player.setAudioOutput(out)

    persist_dir = tempfile.mkdtemp(prefix="axiom_vec_test_")
    state: dict = {}

    class InitWorker(QThread):
        """Builds VectorMemory + loads the model off the main thread."""

        def run(self) -> None:
            vm = VectorMemory(persist_dir=persist_dir)
            vm.embed_chunk("save1", 1, "The hero enters a dark forest.")
            self.vm = vm

    class TurnWorker(QThread):
        """Queries + embeds on a *different* thread (first triton dlopen here)."""

        def __init__(self, vm: VectorMemory) -> None:
            super().__init__()
            self._vm = vm
            self.ok = False

        def run(self) -> None:
            self._vm.query("save1", "forest", k=5, current_turn_id=2)
            self._vm.embed_chunk("save1", 2, "A wolf appears.")
            self.ok = True

    init_worker = InitWorker()
    init_worker.start()
    init_worker.wait()

    def run_turn() -> None:
        turn = TurnWorker(init_worker.vm)
        state["turn"] = turn
        turn.finished.connect(lambda: app.exit(0 if turn.ok else 2))
        turn.start()

    QTimer.singleShot(50, run_turn)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
