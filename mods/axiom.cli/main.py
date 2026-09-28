"""mods/axiom.cli/main.py

Implementation of official Terminal CLI UI mod for Axiom AI.
Provides the public 'cli_play' service for text-adventure in terminal.
"""

from __future__ import annotations

from typing import Any

from axiom.kernel.context import ModContext
from axiom.logger import logger


class CliPlayService:
    """Public service exposed by axiom.cli."""

    def __init__(self, ctx: ModContext) -> None:
        self._ctx = ctx

    def run_play(self, args: Any) -> int:
        """Run terminal play command from CLI arguments."""
        from axiom.cli.play import run_play
        return run_play(args)

    def play_loop(self, session: Any, reader: Any = None, writer: Any = None, error_writer: Any = None) -> int:
        """Execute text-adventure game loop."""
        import sys
        from axiom.cli.play import play_loop
        r = reader if reader is not None else sys.stdin.readline
        w = writer if writer is not None else sys.stdout
        ew = error_writer if error_writer is not None else sys.stderr
        return play_loop(session, read_line=r, out=w, err=ew)


def init(ctx: ModContext) -> None:
    """Mod entry point."""
    service = CliPlayService(ctx)
    ctx.register_service("cli_play", service)
    logger.info("Mod 'axiom.cli' initialized successfully.")
