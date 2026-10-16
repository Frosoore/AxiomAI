"""mods/axiom.illustrations/storage.py

Save data of axiom.illustrations (generated PNG assets). Declared in mod.toml
and run by the kernel even while the mod is disabled.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from mods.axiom.illustrations.main import get_illustrations_service


def rewind_assets(conn: sqlite3.Connection | None, save_id: str, target_turn: int) -> int:
    return get_illustrations_service().truncate_assets(save_id, target_turn)


def fork_assets(
    conn: sqlite3.Connection | None,
    src_save_id: str,
    dst_save_id: str,
    target_turn: int,
    *,
    id_maps: dict[str, dict[Any, Any]] | None = None,
) -> int:
    return get_illustrations_service().fork_assets(src_save_id, dst_save_id, target_turn)
