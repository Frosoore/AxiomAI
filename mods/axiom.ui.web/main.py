"""mods/axiom.ui.web/main.py

Implementation of official Web UI mod for Axiom AI.
Provides the public 'web_ui' service and manages UI slots for side panels,
settings tabs, and action buttons.
"""

from __future__ import annotations

import threading
from typing import Any

from axiom.kernel.context import ModContext
from axiom.logger import logger


class WebUIService:
    """Public service exposed by axiom.ui.web."""

    def __init__(self, ctx: ModContext) -> None:
        self._ctx = ctx
        self._server = None
        self._server_thread: threading.Thread | None = None

    def get_side_panels(self) -> list[Any]:
        """Aggregate side panels contributed by other mods."""
        if self._ctx is not None:
            return self._ctx.get_slot_contributions("axiom.ui.web:side_panel")
        return []

    def get_settings_tabs(self) -> list[Any]:
        """Aggregate settings tabs contributed by other mods."""
        if self._ctx is not None:
            return self._ctx.get_slot_contributions("axiom.ui.web:settings_tab")
        return []

    def get_action_buttons(self) -> list[Any]:
        """Aggregate action buttons contributed by other mods."""
        if self._ctx is not None:
            return self._ctx.get_slot_contributions("axiom.ui.web:action_button")
        return []

    def enrich_session_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """Inject web UI slot contributions into a session start/state snapshot."""
        panels = self.get_side_panels()
        if panels:
            snapshot["side_panels"] = panels
        buttons = self.get_action_buttons()
        if buttons:
            snapshot["action_buttons"] = buttons
        return snapshot

    def start_server(self, port: int = 8000, background: bool = True) -> Any:
        """Launch the web UI HTTP server."""
        from http.server import ThreadingHTTPServer
        import main_web

        server = ThreadingHTTPServer(("127.0.0.1", port), main_web.AxiomWebHandler)
        self._server = server

        if background:
            # Jobs owned by the mod (D11): disabling the mod stops the server.
            thread = self._ctx.spawn_job(server.serve_forever, name="axiom.ui.web:server")
            self._ctx.spawn_job(self._stop_on_cleanup, server, name="axiom.ui.web:stopper")
            self._server_thread = thread
            logger.info("Web UI server running in background on http://127.0.0.1:%d", port)
            return server
        else:
            logger.info("Web UI server starting synchronously on http://127.0.0.1:%d", port)
            server.serve_forever()
            return server

    def _stop_on_cleanup(self, server: Any) -> None:
        self._ctx.stop_event.wait()
        if self._server is server:
            self.stop_server()

    def stop_server(self) -> None:
        """Shut down the HTTP server if running."""
        if self._server:
            try:
                self._server.shutdown()
                self._server.server_close()
                logger.info("Web UI server stopped.")
            except Exception as err:
                logger.error("Error stopping web UI server: %s", err)
            finally:
                self._server = None
                self._server_thread = None


def init(ctx: ModContext) -> None:
    """Mod entry point."""
    service = WebUIService(ctx)
    ctx.register_service("web_ui", service)
    logger.info("Mod 'axiom.ui.web' initialized successfully.")
