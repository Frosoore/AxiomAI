"""mods/axiom.living_memory/storage.py

Storage callbacks for the axiom.living_memory mod.
Handles custom rollback and forking with ID remapping for Observations and Mental_Models.
Invoked by the engine's storage_registry via [storage] declaration even when the mod is disabled.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def _remap_fact_sources(raw: Any, fact_map: dict[Any, Any]) -> str:
    """Rewrite an Observations ``sources`` list ([{fact_id, turn_id}]) with the forked fact ids."""
    try:
        sources = json.loads(raw) if isinstance(raw, str) else (raw or [])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid Observations.sources JSON: {raw!r}") from exc
    out = []
    for src in sources if isinstance(sources, list) else []:
        if not isinstance(src, dict):
            continue
        new = dict(src)
        fid = src.get("fact_id")
        try:
            fid = int(fid) if fid is not None else None
        except (TypeError, ValueError):
            fid = None
        # A fact at a turn after the fork point was not copied: the rollback below
        # drops that source anyway (its turn_id > N). Never keep a source id.
        new["fact_id"] = fact_map.get(fid) if fid is not None else None
        out.append(new)
    return json.dumps(out, ensure_ascii=False)


def rewind_observations(conn: sqlite3.Connection, save_id: str, target_turn: int) -> None:
    from mods.axiom.living_memory.observations import rollback_observations
    rollback_observations(conn, save_id, target_turn)


def fork_observations(
    conn: sqlite3.Connection,
    src_save_id: str,
    dst_save_id: str,
    target_turn: int,
    *,
    id_maps: dict[str, dict[Any, Any]] | None = None,
) -> None:
    """Beliefs at the fork point = copy of the beliefs born <= N, then the same
    rollback as a rewind to N (sources > N dropped, proof_count recomputed,
    updated_turn_id clamped, stale flagged). Custom because ``sources`` holds
    fact ids (JSON) that must follow the forked Facts ids.
    """
    from mods.axiom.living_memory.observations import rollback_observations
    from axiom.schema import ensure_observations_table

    ensure_observations_table(conn)
    fact_map = (id_maps or {}).get("Facts", {})
    obs_map: dict[Any, Any] = {}
    rows = conn.execute(
        "SELECT observation_id, subject, statement, proof_count, sources, history, "
        "created_turn_id, updated_turn_id, stale "
        "FROM Observations WHERE save_id = ? AND created_turn_id <= ? ORDER BY observation_id;",
        (src_save_id, target_turn),
    ).fetchall()
    for r in rows:
        cur = conn.execute(
            "INSERT INTO Observations (save_id, subject, statement, proof_count, sources, "
            "history, created_turn_id, updated_turn_id, stale) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (dst_save_id, r[1], r[2], r[3], _remap_fact_sources(r[4], fact_map), r[5], r[6], r[7], r[8]),
        )
        obs_map[int(r[0])] = cur.lastrowid
    if id_maps is not None:
        id_maps["Observations"] = obs_map
    rollback_observations(conn, dst_save_id, target_turn)


def rewind_mental_models(conn: sqlite3.Connection, save_id: str, target_turn: int) -> None:
    from mods.axiom.living_memory.mental_models import rollback_mental_models
    rollback_mental_models(conn, save_id, target_turn)


def fork_mental_models(
    conn: sqlite3.Connection,
    src_save_id: str,
    dst_save_id: str,
    target_turn: int,
    *,
    id_maps: dict[str, dict[Any, Any]] | None = None,
) -> None:
    """Same rule as the beliefs: copy the models born <= N, then rewind them to N.
    Custom because ``sources`` holds observation ids (JSON)."""
    from mods.axiom.living_memory.mental_models import rollback_mental_models
    from axiom.schema import ensure_mental_models_table

    ensure_mental_models_table(conn)
    obs_map = (id_maps or {}).get("Observations", {})
    rows = conn.execute(
        "SELECT model_id, subject, summary, sources, created_turn_id, updated_turn_id, stale "
        "FROM Mental_Models WHERE save_id = ? AND created_turn_id <= ? ORDER BY model_id;",
        (src_save_id, target_turn),
    ).fetchall()
    model_map: dict[Any, Any] = {}
    for r in rows:
        try:
            sources = json.loads(r[3]) if r[3] else []
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid Mental_Models.sources JSON: {r[3]!r}") from exc
        remapped = []
        for s in sources if isinstance(sources, list) else []:
            try:
                old = int(s)
            except (TypeError, ValueError):
                continue
            if old in obs_map:
                remapped.append(obs_map[old])
        cur = conn.execute(
            "INSERT INTO Mental_Models (save_id, subject, summary, sources, created_turn_id, "
            "updated_turn_id, stale) VALUES (?, ?, ?, ?, ?, ?, ?);",
            (dst_save_id, r[1], r[2], json.dumps(remapped), r[4], r[5], r[6]),
        )
        model_map[int(r[0])] = cur.lastrowid
    if id_maps is not None:
        id_maps["Mental_Models"] = model_map
    rollback_mental_models(conn, dst_save_id, target_turn)
