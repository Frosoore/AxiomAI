"""core/st_parser.py

Decoupled re-export shim for SillyTavern character card parser.
Canonical implementation is in mods.axiom.sillytavern.main.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from axiom.config import load_config
from axiom.kernel.loader import is_mod_enabled


def parse_st_card(filepath: str | Path) -> dict[str, Any]:
    """Extract character data from a SillyTavern character card (PNG or JSON).

    Raises:
        RuntimeError: If axiom.sillytavern mod is disabled or missing.
        ValueError: If file parsing fails or format is unsupported.
    """
    if not is_mod_enabled("axiom.sillytavern", load_config()):
        raise RuntimeError("SillyTavern Card Importer mod (axiom.sillytavern) is disabled.")
    from mods.axiom.sillytavern.main import parse_st_card as mod_parse_st_card
    return mod_parse_st_card(filepath)
