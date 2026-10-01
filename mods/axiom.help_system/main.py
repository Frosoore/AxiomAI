"""mods/axiom.help_system/main.py

Implementation of official Integrated Help & Tooltips mod for Axiom AI.
Registers the 'help_system' service and manages lifecycle (installing tooltip gate,
providing access to documentation dialogs).
"""

from __future__ import annotations

from typing import Any
from PySide6.QtWidgets import QApplication

from axiom.kernel.context import ModContext
from axiom.logger import logger
from mods.axiom.help_system.ui import help_system, help_dialogs


class HelpSystemService:
    """Public service exposed by axiom.help_system."""

    def __init__(self, ctx: ModContext) -> None:
        self._ctx = ctx

    def get_pages(self) -> dict[str, tuple[str, ...]]:
        """Return the documentation pages registry."""
        return help_system.PAGES

    def install_gate(self, app: QApplication | None = None) -> None:
        """Install tooltip gate on the given or current QApplication."""
        target_app = app or QApplication.instance()
        if target_app is not None:
            help_system.install_tooltip_gate(target_app)

    def uninstall_gate(self, app: QApplication | None = None) -> None:
        """Uninstall tooltip gate."""
        target_app = app or QApplication.instance()
        if target_app is not None:
            help_system.uninstall_tooltip_gate(target_app)

    def is_available(self) -> bool:
        """Return True when service is active."""
        return True


_service_instance: HelpSystemService | None = None


def get_service() -> HelpSystemService | None:
    """Return active HelpSystemService instance if mod is loaded."""
    return _service_instance


def init(ctx: ModContext) -> None:
    """Mod entry point."""
    global _service_instance
    service = HelpSystemService(ctx)
    _service_instance = service
    ctx.register_service("help_system", service)

    # Automatically install the tooltip gate if QApplication is already running
    app = QApplication.instance()
    if app is not None:
        service.install_gate(app)

    logger.info("Mod 'axiom.help_system' initialized successfully.")
