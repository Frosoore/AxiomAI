"""Structured-fact storage for "living" memory mode.

In living mode the engine distils each turn's narrative into atomic **facts**
(a who/what/when/where/why model adapted from Hindsight) and stores them here,
tagged with the ``turn_id`` that produced them. The turn tag makes rollback
trivial — rewinding to turn N simply drops every fact from a later turn — and
keeps the facts in lockstep with the event log they were derived from.

This module is the *deterministic* storage layer: no LLM, no network. The LLM
extraction that produces the facts lives in ``axiom.factextract``; the background
job that calls it lives in the app's worker layer. Facts live in the same SQLite
database as ``Event_Log`` / ``State_Cache`` (keyed by ``save_id`` + ``turn_id``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from axiom.schema import ensure_facts_table, get_connection

# Recognised fact categories (free text is tolerated but these are the intent):
#   world      — a fact about the world/NPCs ("the bridge at Voss collapsed")
#   experience — something the player lived through ("the player swore an oath")
#   assistant  — something narrated/said by the game ("the narrator hinted at...")
FACT_TYPES: tuple[str, ...] = ("world", "experience", "assistant")


@dataclass
class Fact:
    """One atomic fact extracted from the narrative.

    ``statement`` is the canonical one-sentence form used for recall/embedding;
    the who/what/when/where/why fields are the structured decomposition.
    """

    statement: str
    fact_type: str = "world"
    who: str = ""
    what: str = ""
    when: str = ""
    where: str = ""
    why: str = ""
    entities: list[str] = field(default_factory=list)
    turn_id: int | None = None
    fact_id: int | None = None

    def __post_init__(self) -> None:
        if self.fact_type not in FACT_TYPES:
            self.fact_type = "world"


def _row_to_fact(row) -> Fact:
    try:
        entities = json.loads(row["entities"]) if row["entities"] else []
        if not isinstance(entities, list):
            entities = []
    except (ValueError, TypeError):
        entities = []
    return Fact(
        statement=row["statement"],
        fact_type=row["fact_type"],
        who=row["who"],
        what=row["what"],
        when=row["fact_when"],
        where=row["fact_where"],
        why=row["why"],
        entities=[str(e) for e in entities],
        turn_id=row["turn_id"],
        fact_id=row["fact_id"],
    )


def insert_facts(db_path: str, save_id: str, turn_id: int, facts: list[Fact]) -> list[int]:
    """Persist a turn's extracted facts. Returns the new ``fact_id`` values.

    Empty statements are skipped (an extractor that found nothing is normal and
    must not write blank rows). Idempotency is the caller's concern: re-extracting
    a turn should first ``rollback_facts`` to that turn.

    Side effect: each ``Fact`` that is actually inserted has its ``fact_id`` and
    ``turn_id`` set in place, so the caller can use the objects directly without
    re-aligning a separate id list (skipped/blank facts keep ``fact_id=None``).
    """
    if not facts:
        return []
    new_ids: list[int] = []
    with get_connection(db_path) as conn:
        ensure_facts_table(conn)
        for f in facts:
            statement = (f.statement or "").strip()
            if not statement:
                continue
            cur = conn.execute(
                """
                INSERT INTO Facts
                    (save_id, turn_id, fact_type, who, what, fact_when,
                     fact_where, why, entities, statement)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    save_id,
                    turn_id,
                    f.fact_type if f.fact_type in FACT_TYPES else "world",
                    f.who or "",
                    f.what or "",
                    f.when or "",
                    f.where or "",
                    f.why or "",
                    json.dumps(list(f.entities or []), ensure_ascii=False),
                    statement,
                ),
            )
            f.fact_id = int(cur.lastrowid)
            f.turn_id = turn_id
            new_ids.append(f.fact_id)
        conn.commit()
    return new_ids


def get_facts(
    db_path: str,
    save_id: str,
    *,
    max_turn_id: int | None = None,
    entity: str | None = None,
    limit: int | None = None,
) -> list[Fact]:
    """Fetch a save's facts, most recent first.

    Args:
        max_turn_id: Only facts from turns ``<= max_turn_id`` (honours the
            history window / rewind horizon). ``None`` = no upper bound.
        entity: Keep only facts whose ``entities`` list contains this name
            (case-insensitive exact match). ``None`` = no filter.
        limit: Cap the number of rows returned.
    """
    sql = "SELECT * FROM Facts WHERE save_id = ?"
    params: list[object] = [save_id]
    if max_turn_id is not None:
        sql += " AND turn_id <= ?"
        params.append(max_turn_id)
    sql += " ORDER BY turn_id DESC, fact_id DESC"
    # Push the cap into SQL when there is no post-filter, so we don't materialise
    # the whole table just to slice it. With an entity filter the cap must stay in
    # Python (rows are dropped *after* the JSON entities match).
    if limit is not None and entity is None:
        sql += " LIMIT ?"
        params.append(int(limit))

    with get_connection(db_path) as conn:
        ensure_facts_table(conn)
        rows = conn.execute(sql, params).fetchall()

    facts = [_row_to_fact(r) for r in rows]
    if entity is not None:
        needle = entity.strip().lower()
        facts = [f for f in facts if any(e.lower() == needle for e in f.entities)]
        if limit is not None:
            facts = facts[:limit]
    return facts


def count_facts(db_path: str, save_id: str) -> int:
    """Number of stored facts for a save (cheap COUNT)."""
    with get_connection(db_path) as conn:
        ensure_facts_table(conn)
        row = conn.execute(
            "SELECT COUNT(*) FROM Facts WHERE save_id = ?;", (save_id,)
        ).fetchone()
    return int(row[0])


def rollback_facts(db_path: str, save_id: str, target_turn_id: int) -> int:
    """Delete a save's facts from turns after ``target_turn_id``. Returns the count.

    Standalone helper (opens its own connection). The in-session rewind path
    deletes facts inside ``CheckpointManager.rewind``'s own transaction instead,
    so events and facts roll back atomically.
    """
    with get_connection(db_path) as conn:
        ensure_facts_table(conn)
        row = conn.execute(
            "SELECT COUNT(*) FROM Facts WHERE save_id = ? AND turn_id > ?;",
            (save_id, target_turn_id),
        ).fetchone()
        deleted = int(row[0])
        conn.execute(
            "DELETE FROM Facts WHERE save_id = ? AND turn_id > ?;",
            (save_id, target_turn_id),
        )
        conn.commit()
    return deleted
