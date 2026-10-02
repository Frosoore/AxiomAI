"""mods/axiom.ui.qt/main.py

Implementation of official Desktop Qt UI mod for Axiom AI.
Provides the public 'qt_ui' service and manages UI slots for sidebar widgets
and settings tabs.
"""

from __future__ import annotations

import sys
from typing import Any

from axiom.kernel.context import ModContext
from axiom.logger import logger

_service_instance: QtUIService | None = None


def get_qt_service() -> QtUIService | None:
    """Return the currently registered QtUIService instance, if any."""
    return _service_instance


class QtUIService:
    """Public service exposed by axiom.ui.qt."""

    def __init__(self, ctx: ModContext) -> None:
        self._ctx = ctx

    def get_sidebar_widgets(self) -> list[Any]:
        """Aggregate sidebar widgets contributed by other mods."""
        if self._ctx is not None:
            return self._ctx.get_slot_contributions("axiom.ui.qt:sidebar_widget")
        return []

    def get_settings_tabs(self) -> list[Any]:
        """Aggregate settings tabs contributed by other mods."""
        if self._ctx is not None:
            return self._ctx.get_slot_contributions("axiom.ui.qt:settings_tab")
        return []

    def launch_gui(self, argv: list[str] | None = None) -> int:
        """Launch the desktop PySide6 GUI."""
        if argv is not None:
            old_argv = sys.argv
            sys.argv = [sys.argv[0]] + list(argv)
            try:
                import main
                return main.main()
            finally:
                sys.argv = old_argv
        import main
        return main.main()


def init(ctx: ModContext) -> None:
    """Mod entry point."""
    global _service_instance
    service = QtUIService(ctx)
    _service_instance = service
    ctx.register_service("qt_ui", service)
    logger.info("Mod 'axiom.ui.qt' initialized successfully.")
