"""Mental-model storage for "living" memory mode (Hindsight §7.8).

A **mental model** is a curated, synthetic profile — one per subject (a character,
or ``""`` for the world) — that sits *above* the beliefs in the recall hierarchy:

    mental model  →  beliefs (observations)  →  facts  →  raw narrative chunks
    (most synthetic)                                       (most raw)

Where a belief is one durable statement, a mental model is a short paragraph that
distils *all* of a subject's beliefs into "who this is now": their relationships,
goals, grudges and how they have changed. The narrator reads it first, so a long
campaign's accumulated memory lands as a coherent character note rather than a
pile of disjointed facts.

Idea adapted from Hindsight (MIT, ``reflect/``): their reflect agent maintains
curated *mental models* above the raw memories. We keep the **principle of a
synthetic top layer** but drop the heavy tool-calling agent — for a single-player
game one regenerated paragraph per subject is enough.

This module is the *deterministic* storage + rollback layer (no LLM, no network).
The LLM that writes the summary lives in :mod:`axiom.reflect`; the background job
that calls it lives in the app's worker layer.

**Rollback.** A mental model is fully reconstructible from the beliefs it was
built from (which themselves roll back correctly), so rewinding to turn N only has
to: drop every model *created* after N, and flag the survivors ``stale`` (clamping
``updated_turn_id``) so the next refresh regenerates them from the rewound beliefs.
There is at most one model per ``(save_id, subject)`` — refresh is an UPSERT.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from axiom.schema import ensure_mental_models_table, get_connection


@dataclass
class MentalModel:
    """One curated profile for a subject (a character, or "" for the world).

    ``sources`` is a list of the ``observation_id`` values the summary was built
    from (kept for traceability / future link expansion; the rollback key is the
    turn ids, which the beliefs themselves carry).
    """

    subject: str
    summary: str
    sources: list[int] = field(default_factory=list)
    created_turn_id: int = 0
    updated_turn_id: int = 0
    stale: bool = False
    model_id: int | None = None


def _loads_list(raw) -> list:
    try:
        val = json.loads(raw) if raw else []
        return val if isinstance(val, list) else []
    except (ValueError, TypeError):
        return []


def _normalise_sources(sources) -> list[int]:
    out: list[int] = []
    for s in sources or []:
        try:
            out.append(int(s))
        except (TypeError, ValueError):
            continue
    return out


def _row_to_model(row) -> MentalModel:
    return MentalModel(
        subject=row["subject"],
        summary=row["summary"],
        sources=_normalise_sources(_loads_list(row["sources"])),
        created_turn_id=int(row["created_turn_id"]),
        updated_turn_id=int(row["updated_turn_id"]),
        stale=bool(row["stale"]),
        model_id=int(row["model_id"]),
    )


def upsert_mental_model(
    db_path: str,
    save_id: str,
    subject: str,
    summary: str,
    turn_id: int,
    sources: list[int] | None = None,
) -> int | None:
    """Create or refresh the mental model for ``subject``. Returns its ``model_id``.

    There is at most one model per ``(save_id, subject)``: an existing one is
    updated in place (``created_turn_id`` preserved), otherwise a new one is
    inserted. Blank summaries are skipped (never overwrite a profile with nothing).
    """
    summary = (summary or "").strip()
    if not summary:
        return None
    src = _normalise_sources(sources)
    with get_connection(db_path) as conn:
        ensure_mental_models_table(conn)
        row = conn.execute(
            "SELECT model_id, created_turn_id FROM Mental_Models "
            "WHERE save_id = ? AND subject = ?;",
            (save_id, subject or ""),
        ).fetchone()
        if row is not None:
            conn.execute(
                "UPDATE Mental_Models SET summary = ?, sources = ?, "
                "updated_turn_id = ?, stale = 0 WHERE model_id = ?;",
                (summary, json.dumps(src), int(turn_id), row["model_id"]),
            )
            conn.commit()
            return int(row["model_id"])
        cur = conn.execute(
            """
            INSERT INTO Mental_Models
                (save_id, subject, summary, sources, created_turn_id,
                 updated_turn_id, stale)
            VALUES (?, ?, ?, ?, ?, ?, 0);
            """,
            (save_id, subject or "", summary, json.dumps(src),
             int(turn_id), int(turn_id)),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_mental_models(
    db_path: str,
    save_id: str,
    *,
    max_turn_id: int | None = None,
    subject: str | None = None,
    limit: int | None = None,
) -> list[MentalModel]:
    """Fetch a save's mental models, most recently updated first.

    Args:
        max_turn_id: Only models created at turns ``<= max_turn_id`` (honours the
            rewind horizon). ``None`` = no bound.
        subject: Keep only the model for this subject (case-insensitive). ``""``
            keeps the world-level model.
        limit: Cap the number of rows returned.
    """
    sql = "SELECT * FROM Mental_Models WHERE save_id = ?"
    params: list[object] = [save_id]
    if max_turn_id is not None:
        sql += " AND created_turn_id <= ?"
        params.append(max_turn_id)
    sql += " ORDER BY updated_turn_id DESC, model_id DESC"
    # Push the cap into SQL only when there is no case-insensitive subject filter.
    if limit is not None and subject is None:
        sql += " LIMIT ?"
        params.append(int(limit))

    with get_connection(db_path) as conn:
        ensure_mental_models_table(conn)
        rows = conn.execute(sql, params).fetchall()

    models = [_row_to_model(r) for r in rows]
    if subject is not None:
        needle = subject.strip().lower()
        models = [m for m in models if m.subject.strip().lower() == needle]
        if limit is not None:
            models = models[:limit]
    return models


def count_mental_models(db_path: str, save_id: str) -> int:
    """Number of stored mental models for a save (cheap COUNT)."""
    with get_connection(db_path) as conn:
        ensure_mental_models_table(conn)
        row = conn.execute(
            "SELECT COUNT(*) FROM Mental_Models WHERE save_id = ?;", (save_id,)
        ).fetchone()
    return int(row[0])


def stale_subjects(
    db_path: str, save_id: str, *, max_turn_id: int | None = None, limit: int = 5
) -> list[str]:
    """Subjects whose model is flagged ``stale`` (oldest update first).

    A rewind flags survivors stale; this lets the refresh job find and regenerate
    them even when their beliefs do not change again. Capped so a long backlog
    never floods one consolidation pass.
    """
    sql = "SELECT subject FROM Mental_Models WHERE save_id = ? AND stale = 1"
    params: list[object] = [save_id]
    if max_turn_id is not None:
        sql += " AND created_turn_id <= ?"
        params.append(max_turn_id)
    sql += " ORDER BY updated_turn_id ASC LIMIT ?"
    params.append(int(limit))
    with get_connection(db_path) as conn:
        ensure_mental_models_table(conn)
        rows = conn.execute(sql, params).fetchall()
    return [r["subject"] for r in rows]


def rollback_mental_models(conn, save_id: str, target_turn_id: int) -> dict[str, int]:
    """Roll a save's mental models back to their state at ``target_turn_id``.

    Operates on an already-open connection so ``CheckpointManager.rewind`` can run
    it inside the same transaction as the Event_Log / Facts / Observations deletes.

    Rule (see module docstring):
      - model ``created_turn_id > target`` → did not exist yet → DELETE;
      - else, if it was last refreshed after the target, clamp ``updated_turn_id``
        to ``target`` and flag ``stale`` so the next refresh regenerates it from
        the rewound beliefs (the old summary stays as a graceful fallback meanwhile).

    Returns ``{"deleted": n, "updated": m}``.
    """
    ensure_mental_models_table(conn)
    deleted = conn.execute(
        "DELETE FROM Mental_Models WHERE save_id = ? AND created_turn_id > ?;",
        (save_id, target_turn_id),
    ).rowcount or 0
    updated = conn.execute(
        "UPDATE Mental_Models SET stale = 1, updated_turn_id = ? "
        "WHERE save_id = ? AND updated_turn_id > ?;",
        (target_turn_id, save_id, target_turn_id),
    ).rowcount or 0
    return {"deleted": int(deleted), "updated": int(updated)}


def rollback_mental_models_standalone(
    db_path: str, save_id: str, target_turn_id: int
) -> dict[str, int]:
    """Standalone variant of :func:`rollback_mental_models` (opens its own conn)."""
    with get_connection(db_path) as conn:
        result = rollback_mental_models(conn, save_id, target_turn_id)
        conn.commit()
    return result
