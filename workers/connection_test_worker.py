"""
workers/connection_test_worker.py

Lightweight QThread worker for testing LLM backend connectivity.

Used exclusively by the Settings dialog "Test Connection" buttons.
Calls LLMBackend.is_available() off the main thread and emits the result.

THREADING RULE: is_available() may perform a network call — it MUST NOT
run on the main thread.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from axiom.backends.base import LLMBackend


class ConnectionTestWorker(QThread):
    """Tests whether an LLM backend is reachable.

    Signals:
        result_ready(bool, str): (is_available, human-readable message).

    Args:
        llm:         The LLMBackend instance to test.
        probe_model: When True, validate the configured model with a real
                     1-token completion instead of the /models listing. Use it
                     for cloud providers: their /models is not authoritative
                     (Fireworks only lists the account's own models, not the
                     public serverless catalog), while a tiny paid call is the
                     ground truth and surfaces the provider's exact error.
    """

    result_ready = Signal(bool, str)

    def __init__(self, llm: LLMBackend, probe_model: bool = False) -> None:
        super().__init__()
        self._llm = llm
        self._probe_model = probe_model

    def run(self) -> None:
        """Call is_available() and emit result_ready.  Never raises."""
        try:
            available = self._llm.is_available()
            if not available:
                self.result_ready.emit(False, "✗ Backend is unreachable.")
                return
            problem = self._probe() if self._probe_model else self._check_model()
            if problem:
                self.result_ready.emit(False, problem)
            else:
                self.result_ready.emit(True, "✓ Connected successfully.")
        except Exception as exc:
            self.result_ready.emit(False, f"✗ Error: {exc}")

    def _probe(self) -> str | None:
        """Ground-truth model check: a 1-token completion.

        Negligible cost, only runs when the user clicks "Test Connection".
        Catches everything the listing can't: unknown/retired model, key
        without inference permission, exhausted credits…
        """
        try:
            self._llm.complete([{"role": "user", "content": "ping"}], max_tokens=1)
            return None
        except Exception as exc:
            return f"✗ {exc}"

    def _check_model(self) -> str | None:
        """Verify the configured model exists on the server, when listable.

        Used for the local/universal backend, where /models is authoritative
        (Ollama/LM Studio list exactly what is installed) and where a real
        generation probe could be slow (cold model load). Returns an error
        message, or None when the model is fine or the backend can't list.
        """
        list_models = getattr(self._llm, "list_models", None)
        model = getattr(self._llm, "model_name", "")
        if list_models is None or not model:
            return None
        try:
            ids = list_models()
        except Exception:
            return None
        if not ids:
            return None  # endpoint reachable but unlistable: stay permissive
        for mid in ids:
            # Ollama lists "name:tag" (e.g. llama3.2:latest) for model "llama3.2".
            if mid == model or mid.split(":")[0] == model:
                return None
        return f"✗ Connected, but model '{model}' was not found on this server."
