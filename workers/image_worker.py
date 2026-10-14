"""workers/image_worker.py

QThread worker for asynchronous scene image generation.
Delegates generation logic to the illustrations service or ImageGenerator
off the Qt main thread so the UI never freezes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, Signal

from axiom.logger import logger


class ImageWorker(QThread):
    """Asynchronous worker for generating a scene illustration."""

    image_generated = Signal(object)  # Path | str | None
    error_occurred = Signal(str)

    def __init__(
        self,
        illus_svc: Any,
        save_id: str,
        turn_id: int,
        narrative_text: str,
        cfg: Any = None,
        llm: Any = None,
        location_desc: str = "",
        character_desc: str = "",
        game_state_tag: str = "",
        data_root: Path | None = None,
    ) -> None:
        super().__init__()
        self._illus_svc = illus_svc
        self._save_id = save_id
        self._turn_id = turn_id
        self._narrative_text = narrative_text
        self._cfg = cfg
        self._llm = llm
        self._location_desc = location_desc
        self._character_desc = character_desc
        self._game_state_tag = game_state_tag
        self._data_root = data_root

    def run(self) -> None:
        try:
            if self._data_root is not None and hasattr(self._illus_svc, "remember_root"):
                self._illus_svc.remember_root(self._save_id, self._data_root)

            img_path = self._illus_svc.generate_turn_image(
                save_id=self._save_id,
                turn_id=self._turn_id,
                narrative_text=self._narrative_text,
                location_desc=self._location_desc,
                character_desc=self._character_desc,
                game_state_tag=self._game_state_tag,
                cfg=self._cfg,
                llm=self._llm,
                force=True,
            )
            self.image_generated.emit(img_path)
        except Exception as exc:
            logger.warning("[ImageWorker] Error generating image: %s", exc)
            self.error_occurred.emit(str(exc))
