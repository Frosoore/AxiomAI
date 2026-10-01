"""mods/axiom.sillytavern/main.py

Implementation of official SillyTavern character card importer mod for Axiom AI.
Provides character data extraction from SillyTavern PNG and JSON cards,
and exposes the 'sillytavern' service.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any
from PIL import Image

from axiom.kernel.context import ModContext
from axiom.logger import logger


def parse_st_card(filepath: str | Path) -> dict:
    """Extract character data from a SillyTavern character card (PNG or JSON).

    Args:
        filepath: Path to the .png or .json file.

    Returns:
        A dictionary containing the parsed character data.

    Raises:
        ValueError: If file format is unsupported, metadata is missing, or JSON is invalid.
    """
    path = Path(filepath)
    ext = path.suffix.lower()

    if ext == ".json":
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if "data" in data and isinstance(data["data"], dict):
                    return data["data"]
                return data
        except Exception as exc:
            raise ValueError(f"Failed to parse JSON card: {exc}") from exc

    elif ext == ".png":
        try:
            with Image.open(path) as img:
                info = img.info
                chara_base64 = info.get("chara")

                if not chara_base64:
                    raise ValueError("PNG does not contain 'chara' metadata (Not a valid ST card).")

                decoded_bytes = base64.b64decode(chara_base64)
                data = json.loads(decoded_bytes.decode("utf-8"))

                if "data" in data and isinstance(data["data"], dict):
                    return data["data"]
                return data

        except Exception as exc:
            raise ValueError(f"Failed to extract/parse metadata from PNG: {exc}") from exc

    else:
        raise ValueError(f"Unsupported file extension: {ext}")


class SillyTavernService:
    """Public service provided by the axiom.sillytavern mod."""

    def __init__(self, ctx: ModContext) -> None:
        self._ctx = ctx

    def parse_card(self, filepath: str | Path) -> dict:
        """Parse card using mod parser."""
        return parse_st_card(filepath)

    def is_available(self) -> bool:
        """Return True if the service is active."""
        return True


_service_instance: SillyTavernService | None = None


def get_service() -> SillyTavernService | None:
    """Return active SillyTavernService instance if mod is loaded."""
    return _service_instance


def init(ctx: ModContext) -> None:
    """Mod entry point."""
    global _service_instance
    service = SillyTavernService(ctx)
    _service_instance = service
    ctx.register_service("sillytavern", service)
    logger.info("Mod 'axiom.sillytavern' initialized successfully.")
