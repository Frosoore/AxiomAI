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

    # ------------------------------------------------------------------
    # Extension slots (rendered by the SPA: no mod JavaScript is needed)
    #
    # - axiom.ui.web:side_panel   {"id", "title", "render": callable(session) -> str
    #                              | "text": str, "order": int}
    # - axiom.ui.web:action_button {"id", "label", "on_click": callable(session) -> str | None,
    #                              "order": int}
    # - axiom.ui.web:settings_tab {"id", "title", "fields": [{"key", "label",
    #                              "type": "text" | "number" | "bool", "default"}]}
    #   (values stored in the contributing mod's settings, ctx.config)
    # A contribution that raises or is malformed disables its mod (§6.1).
    # ------------------------------------------------------------------
    def _entries(self, slot: str) -> list[tuple[str, dict[str, Any]]]:
        if self._ctx is None:
            return []
        out = []
        for mod_id, contrib in self._ctx.get_slot_entries(slot):
            if not isinstance(contrib, dict) or not contrib.get("id"):
                self._ctx.report_fault(mod_id, f"slot '{slot}'", ValueError(
                    f"expected a dict with an 'id', got {contrib!r}"))
                continue
            out.append((mod_id, contrib))
        out.sort(key=lambda e: int(e[1].get("order", 0) or 0))
        return out

    def _call(self, mod_id: str, slot: str, func: Any, *args: Any) -> tuple[bool, Any]:
        try:
            return True, func(*args)
        except Exception as err:
            self._ctx.report_fault(mod_id, f"slot '{slot}'", err)
            return False, None

    def get_side_panels(self) -> list[dict[str, Any]]:
        """Side panels contributed by other mods (declarations, not rendered)."""
        return [c for _m, c in self._entries("axiom.ui.web:side_panel")]

    def render_side_panels(self, session: Any) -> list[dict[str, str]]:
        """[{id, title, text}] for the current session."""
        slot = "axiom.ui.web:side_panel"
        panels = []
        for mod_id, c in self._entries(slot):
            text = c.get("text", "")
            if callable(c.get("render")):
                ok, text = self._call(mod_id, slot, c["render"], session)
                if not ok:
                    continue
            panels.append({"id": str(c["id"]), "title": str(c.get("title", c["id"])), "text": str(text or "")})
        return panels

    def get_action_buttons(self) -> list[dict[str, str]]:
        """[{id, label}] of the contributed action buttons."""
        return [
            {"id": str(c["id"]), "label": str(c.get("label", c["id"]))}
            for _m, c in self._entries("axiom.ui.web:action_button")
        ]

    def run_action(self, action_id: str, session: Any) -> str:
        """Run a contributed action button; returns the message to show."""
        slot = "axiom.ui.web:action_button"
        for mod_id, c in self._entries(slot):
            if str(c["id"]) == action_id and callable(c.get("on_click")):
                ok, msg = self._call(mod_id, slot, c["on_click"], session)
                if not ok:
                    raise RuntimeError(f"Action '{action_id}' failed; mod '{mod_id}' was disabled.")
                return str(msg or "")
        raise KeyError(action_id)

    def get_settings_tabs(self, config: Any = None) -> list[dict[str, Any]]:
        """[{id, title, mod_id, fields: [{key, label, type, value}]}] with the stored values."""
        tabs = []
        for mod_id, c in self._entries("axiom.ui.web:settings_tab"):
            stored = {}
            if config is not None and isinstance(getattr(config, "mod_settings", None), dict):
                stored = config.mod_settings.get(mod_id, {}) or {}
            fields = []
            for f in c.get("fields", []) or []:
                if not isinstance(f, dict) or not f.get("key"):
                    continue
                ftype = f.get("type", "text")
                if ftype not in ("text", "number", "bool"):
                    ftype = "text"
                fields.append({
                    "key": str(f["key"]),
                    "label": str(f.get("label", f["key"])),
                    "type": ftype,
                    "value": stored.get(f["key"], f.get("default")),
                })
            tabs.append({"id": str(c["id"]), "title": str(c.get("title", c["id"])), "mod_id": mod_id, "fields": fields})
        return tabs

    def save_settings(self, tab_id: str, values: dict[str, Any], config: Any) -> None:
        """Store the values of a contributed settings tab in its mod's settings."""
        for tab in self.get_settings_tabs(config):
            if tab["id"] != tab_id:
                continue
            section = config.mod_settings.setdefault(tab["mod_id"], {})
            for f in tab["fields"]:
                if f["key"] not in values:
                    continue
                v = values[f["key"]]
                if f["type"] == "number":
                    v = float(v) if "." in str(v) else int(v)
                elif f["type"] == "bool":
                    v = bool(v)
                else:
                    v = str(v)
                section[f["key"]] = v
            return
        raise KeyError(tab_id)

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
