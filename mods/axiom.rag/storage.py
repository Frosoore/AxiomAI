"""mods/axiom.rag/storage.py

External save data of axiom.rag (semantic vector memory in ChromaDB). Declared
in mod.toml and run by the kernel even while the mod is disabled.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from mods.axiom.rag.main import get_rag_service


def rewind_rag(conn: sqlite3.Connection | None, save_id: str, target_turn: int) -> int:
    return get_rag_service().rollback(save_id, target_turn)


def fork_rag(
    conn: sqlite3.Connection | None,
    src_save_id: str,
    dst_save_id: str,
    target_turn: int,
    *,
    id_maps: dict[str, dict[Any, Any]] | None = None,
) -> int:
    return get_rag_service().fork(src_save_id, dst_save_id, target_turn)
