"""tests/test_web_server_startup.py

`main_web.run_server` doit charger les mods au démarrage (revue 2026-10-03,
4-DOC-ET-RUNTIME I3) : l'import `axiom.kernel.bootstrap` n'existait pas, l'erreur
était avalée et le serveur démarrait sans aucun mod.
"""

from __future__ import annotations

import threading
import time
import urllib.request

import pytest


def test_run_server_bootstraps_mods(monkeypatch):
    import main_web
    from axiom.kernel import registry as kernel_registry

    started: list = []

    class _CapturingServer(main_web.ThreadingHTTPServer):
        def __init__(self, address, handler):
            # Port 0 : l'OS choisit un port libre.
            super().__init__((address[0], 0), handler)
            started.append(self)

    monkeypatch.setattr(main_web, "ThreadingHTTPServer", _CapturingServer)
    monkeypatch.setattr(main_web.webbrowser, "open", lambda *a, **k: True)
    kernel_registry.set_active_registry(None)

    errors: list = []
    monkeypatch.setattr(
        main_web.logger, "exception",
        lambda msg, *a, **k: errors.append(msg % a if a else msg),
    )

    result: list = []
    thread = threading.Thread(target=lambda: result.append(main_web.run_server(0)), daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 60
        while not started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert started, f"le serveur n'a pas démarré (result={result})"
        server = started[0]

        assert errors == [], errors
        reg = kernel_registry.get_active_registry()
        assert reg is not None, "aucun mod n'a été chargé au démarrage du serveur"
        assert reg.get_service("web_ui") is not None
        assert reg.has_hook("axiom.kernel:execute_step")

        port = server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=10) as resp:
            assert resp.status == 200
    finally:
        for server in started:
            server.shutdown()
            server.server_close()
        thread.join(timeout=10)
        kernel_registry.set_active_registry(None)

    assert result == [0]
