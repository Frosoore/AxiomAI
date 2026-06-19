"""Consolidated-belief storage for "living" memory mode (Phase 3).

Where :mod:`axiom.facts` stores the atomic, immutable facts extracted each turn,
this module stores **observations** — synthetic *beliefs* that evolve as facts
accumulate (a Hindsight-inspired idea: an NPC remembers a betrayal hundreds of
turns later and revises its opinion). A belief carries:

- ``statement`` — the canonical belief, one sentence;
- ``subject``   — the entity it is about / who holds it ("" = the world);
- ``sources``   — the supporting facts as ``[{"fact_id", "turn_id"}]``;
- ``proof_count`` — cached ``len(sources)``;
- ``history``   — JSON trail of CREATE/UPDATE/DELETE changes.

This is the *deterministic* storage + rollback layer (no LLM, no network). The
LLM consolidation that decides CREATE/UPDATE/DELETE lives in
``axiom.consolidate``; the background job that calls it lives in the app layer.

**Rollback (the hard part, solved).** Beliefs derive from several turns, so a
plain ``turn_id`` column is not enough. The ``sources`` turn ids are the rollback
key: rewinding to turn N drops every belief *created* after N and, for the
survivors, keeps only the sources at turns ``<= N``, recomputing ``proof_count``
and flagging ``stale`` so the next consolidation pass re-examines them. Beliefs
thus roll back atomically with the facts/events they were built from.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from axiom.schema import ensure_observations_table, get_connection

# --- Belief trends (deterministic, no LLM) ----------------------------------
# Idea adapted from Hindsight (MIT, reflect/observations.py::compute_trend): a
# belief's *direction* — is it gaining ground, fading, going stale? — can be read
# straight off the turn distribution of its supporting sources, for free. Their
# axis is wall-clock days; ours is ``turn_id`` (the engine's native time line, so
# it stays correct across rewinds). Surfaced in the prompt so the narrator can
# tell an intensifying grudge from a fading one. (TICKET-081)
TREND_STABLE = "stable"
TREND_STRENGTHENING = "strengthening"
TREND_WEAKENING = "weakening"
TREND_NEW = "new"
TREND_STALE = "stale"

# Turn windows: a source within the last _TREND_RECENT_TURNS counts as "recent";
# everything before that is "older" (the older band has no lower bound — every
# remaining source counts). To compare like with like we normalise each band by a
# span: recent over _TREND_RECENT_TURNS turns, older over a nominal
# (_TREND_OLD_TURNS - _TREND_RECENT_TURNS) turns, so a 1:3 ratio mirrors
# Hindsight's 30/90-day split.
_TREND_RECENT_TURNS = 15
_TREND_OLD_TURNS = 45


def compute_trend(
    source_turns,
    now_turn: int | None,
    *,
    recent_turns: int = _TREND_RECENT_TURNS,
    old_turns: int = _TREND_OLD_TURNS,
) -> str:
    """Classify a belief's trend from the turn ids of its supporting sources.

    Returns one of the ``TREND_*`` constants:

    - ``NEW``           — every source falls in the recent window;
    - ``STRENGTHENING`` — denser recent evidence than older (ratio > 1.5);
    - ``WEAKENING``     — sparser recent evidence than older (ratio < 0.5);
    - ``STALE``         — no source in the recent window (may be outdated);
    - ``STABLE``        — steady, or trend unknown (no sources / no current turn).

    Deterministic and side-effect free. ``now_turn`` is the current turn (the
    rewind horizon during replay), so the trend is always read at the right "now".
    """
    turns = [int(t) for t in source_turns if t is not None]
    if not turns or now_turn is None:
        return TREND_STABLE  # no signal → neutral

    recent_cutoff = now_turn - recent_turns
    recent = [t for t in turns if t > recent_cutoff]
    if not recent:
        return TREND_STALE
    older = [t for t in turns if t <= recent_cutoff]  # everything before "recent"
    if not older:
        return TREND_NEW

    recent_density = len(recent) / recent_turns if recent_turns > 0 else 0.0
    older_period = old_turns - recent_turns
    older_density = len(older) / older_period if older_period > 0 else 0.0
    if older_density == 0.0:
        return TREND_NEW

    ratio = recent_density / older_density
    if ratio > 1.5:
        return TREND_STRENGTHENING
    if ratio < 0.5:
        return TREND_WEAKENING
    return TREND_STABLE


@dataclass
class Observation:
    """One consolidated belief.

    ``sources`` is a list of ``{"fact_id": int, "turn_id": int}`` dicts — the
    facts backing the belief and the turns they came from (the rollback key).
    """

    statement: str
    subject: str = ""
    proof_count: int = 1
    sources: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)
    created_turn_id: int = 0
    updated_turn_id: int = 0
    stale: bool = False
    observation_id: int | None = None

    def trend(self, now_turn: int | None) -> str:
        """This belief's trend at ``now_turn`` (see :func:`compute_trend`)."""
        return compute_trend((s.get("turn_id") for s in self.sources), now_turn)


def _loads_list(raw) -> list:
    try:
        val = json.loads(raw) if raw else []
        return val if isinstance(val, list) else []
    except (ValueError, TypeError):
        return []


def _normalise_sources(sources) -> list[dict]:
    """Coerce arbitrary input into a clean ``[{"fact_id", "turn_id"}]`` list."""
    out: list[dict] = []
    for s in sources or []:
        if not isinstance(s, dict):
            continue
        try:
            turn = int(s.get("turn_id"))
        except (TypeError, ValueError):
            continue
        fid = s.get("fact_id")
        try:
            fid = int(fid) if fid is not None else None
        except (TypeError, ValueError):
            fid = None
        out.append({"fact_id": fid, "turn_id": turn})
    return out


def _row_to_observation(row) -> Observation:
    return Observation(
        statement=row["statement"],
        subject=row["subject"],
        proof_count=int(row["proof_count"]),
        sources=_normalise_sources(_loads_list(row["sources"])),
        history=_loads_list(row["history"]),
        created_turn_id=int(row["created_turn_id"]),
        updated_turn_id=int(row["updated_turn_id"]),
        stale=bool(row["stale"]),
        observation_id=int(row["observation_id"]),
    )


def insert_observation(
    db_path: str,
    save_id: str,
    obs: Observation,
) -> int | None:
    """Persist a single new belief. Returns its ``observation_id`` (or ``None``).

    Blank statements are skipped (an empty belief is never written). ``proof_count``
    is derived from ``sources`` so it can never disagree with them.
    """
    statement = (obs.statement or "").strip()
    if not statement:
        return None
    sources = _normalise_sources(obs.sources)
    proof = max(int(obs.proof_count or 0), len(sources), 1)
    with get_connection(db_path) as conn:
        ensure_observations_table(conn)
        cur = conn.execute(
            """
            INSERT INTO Observations
                (save_id, subject, statement, proof_count, sources, history,
                 created_turn_id, updated_turn_id, stale)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                save_id,
                obs.subject or "",
                statement,
                proof,
                json.dumps(sources, ensure_ascii=False),
                json.dumps(list(obs.history or []), ensure_ascii=False),
                int(obs.created_turn_id or 0),
                int(obs.updated_turn_id or obs.created_turn_id or 0),
                1 if obs.stale else 0,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_observations(
    db_path: str,
    save_id: str,
    *,
    max_turn_id: int | None = None,
    subject: str | None = None,
    limit: int | None = None,
) -> list[Observation]:
    """Fetch a save's beliefs, most recently updated first.

    Args:
        max_turn_id: Only beliefs created at turns ``<= max_turn_id`` (honours the
            history window / rewind horizon). ``None`` = no bound.
        subject: Keep only beliefs whose ``subject`` matches (case-insensitive).
            ``None`` = no filter; ``""`` keeps the world-level beliefs.
        limit: Cap the number of rows returned.
    """
    sql = "SELECT * FROM Observations WHERE save_id = ?"
    params: list[object] = [save_id]
    if max_turn_id is not None:
        sql += " AND created_turn_id <= ?"
        params.append(max_turn_id)
    sql += " ORDER BY updated_turn_id DESC, observation_id DESC"
    # Push the cap into SQL when there is no subject post-filter (rows are dropped
    # in Python after the case-insensitive subject match otherwise).
    if limit is not None and subject is None:
        sql += " LIMIT ?"
        params.append(int(limit))

    with get_connection(db_path) as conn:
        ensure_observations_table(conn)
        rows = conn.execute(sql, params).fetchall()

    obs = [_row_to_observation(r) for r in rows]
    if subject is not None:
        needle = subject.strip().lower()
        obs = [o for o in obs if o.subject.strip().lower() == needle]
        if limit is not None:
            obs = obs[:limit]
    return obs


def count_observations(db_path: str, save_id: str) -> int:
    """Number of stored beliefs for a save (cheap COUNT)."""
    with get_connection(db_path) as conn:
        ensure_observations_table(conn)
        row = conn.execute(
            "SELECT COUNT(*) FROM Observations WHERE save_id = ?;", (save_id,)
        ).fetchone()
    return int(row[0])


def rollback_observations(conn, save_id: str, target_turn_id: int) -> dict[str, int]:
    """Roll a save's beliefs back to their state at ``target_turn_id``.

    Operates on an already-open connection so ``CheckpointManager.rewind`` can run
    it inside the same transaction as the Event_Log / Facts deletes (atomic).

    Rule (see module docstring):
      - belief ``created_turn_id > target`` → it did not exist yet → DELETE;
      - else keep its sources at turns ``<= target``; if any were dropped (an
        UPDATE absorbed a now-rewound fact) recompute ``proof_count``, clamp
        ``updated_turn_id`` to ``<= target`` and flag ``stale`` for the next
        consolidation pass.

    Returns ``{"deleted": n, "updated": m}``.
    """
    ensure_observations_table(conn)
    rows = conn.execute(
        "SELECT observation_id, sources, created_turn_id, updated_turn_id "
        "FROM Observations WHERE save_id = ?;",
        (save_id,),
    ).fetchall()

    deleted = 0
    updated = 0
    for row in rows:
        obs_id = row["observation_id"]
        if int(row["created_turn_id"]) > target_turn_id:
            conn.execute(
                "DELETE FROM Observations WHERE observation_id = ?;", (obs_id,)
            )
            deleted += 1
            continue
        sources = _normalise_sources(_loads_list(row["sources"]))
        live = [s for s in sources if s["turn_id"] <= target_turn_id]
        clamp_needed = int(row["updated_turn_id"]) > target_turn_id
        if len(live) == len(sources) and not clamp_needed:
            continue  # untouched by this rewind
        if not live:
            # No surviving source despite created <= target (defensive): drop it.
            conn.execute(
                "DELETE FROM Observations WHERE observation_id = ?;", (obs_id,)
            )
            deleted += 1
            continue
        new_updated = min(int(row["updated_turn_id"]), target_turn_id)
        conn.execute(
            "UPDATE Observations SET sources = ?, proof_count = ?, "
            "updated_turn_id = ?, stale = 1 WHERE observation_id = ?;",
            (json.dumps(live, ensure_ascii=False), len(live), new_updated, obs_id),
        )
        updated += 1
    return {"deleted": deleted, "updated": updated}


def _merge_sources(existing: list[dict], new: list[dict]) -> list[dict]:
    """Union of two source lists, de-duplicated by fact_id (turn_id kept)."""
    seen: set = set()
    out: list[dict] = []
    for s in (*existing, *new):
        key = s.get("fact_id")
        if key is not None and key in seen:
            continue
        if key is not None:
            seen.add(key)
        out.append(s)
    return out


def apply_consolidation(
    db_path: str,
    save_id: str,
    turn_id: int,
    actions: list,
    fact_turn_map: dict[int, int],
) -> dict[str, int]:
    """Apply consolidator actions (CREATE/UPDATE/DELETE) to the beliefs store.

    Deterministic: it just executes the decisions the LLM already made (the LLM
    call lives in ``axiom.consolidate``). ``fact_turn_map`` maps each cited
    ``fact_id`` to its ``turn_id`` so new sources carry the turn (the rollback
    key). Unknown belief ids / empty statements are skipped. Returns counts.

    Args:
        turn_id: The turn this consolidation pass runs at — stamped as the
            ``updated_turn_id`` (and ``created_turn_id`` for new beliefs).
    """
    created = updated = deleted = 0
    with get_connection(db_path) as conn:
        ensure_observations_table(conn)
        for a in actions:
            kind = getattr(a, "kind", "")
            fact_ids = [int(f) for f in getattr(a, "source_fact_ids", []) or []]
            new_sources = [
                {"fact_id": fid, "turn_id": int(fact_turn_map[fid])}
                for fid in fact_ids if fid in fact_turn_map
            ]
            if kind == "create":
                statement = (getattr(a, "statement", "") or "").strip()
                if not statement or not new_sources:
                    continue
                created_turn = min(s["turn_id"] for s in new_sources)
                history = [{"turn": turn_id, "action": "create"}]
                conn.execute(
                    """
                    INSERT INTO Observations
                        (save_id, subject, statement, proof_count, sources, history,
                         created_turn_id, updated_turn_id, stale)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0);
                    """,
                    (
                        save_id, getattr(a, "subject", "") or "", statement,
                        len(new_sources), json.dumps(new_sources, ensure_ascii=False),
                        json.dumps(history, ensure_ascii=False),
                        created_turn, turn_id,
                    ),
                )
                created += 1
            elif kind == "update":
                obs_id = getattr(a, "observation_id", None)
                row = conn.execute(
                    "SELECT sources, history, statement FROM Observations "
                    "WHERE observation_id = ? AND save_id = ?;",
                    (obs_id, save_id),
                ).fetchone()
                if row is None:
                    continue
                statement = (getattr(a, "statement", "") or "").strip() or row["statement"]
                merged = _merge_sources(
                    _normalise_sources(_loads_list(row["sources"])), new_sources
                )
                history = _loads_list(row["history"])
                history.append({"turn": turn_id, "action": "update"})
                conn.execute(
                    "UPDATE Observations SET statement = ?, sources = ?, "
                    "proof_count = ?, history = ?, updated_turn_id = ?, stale = 0 "
                    "WHERE observation_id = ?;",
                    (
                        statement, json.dumps(merged, ensure_ascii=False), len(merged),
                        json.dumps(history, ensure_ascii=False), turn_id, obs_id,
                    ),
                )
                updated += 1
            elif kind == "delete":
                obs_id = getattr(a, "observation_id", None)
                cur = conn.execute(
                    "DELETE FROM Observations WHERE observation_id = ? AND save_id = ?;",
                    (obs_id, save_id),
                )
                deleted += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        conn.commit()
    return {"created": created, "updated": updated, "deleted": deleted}


def rollback_observations_standalone(
    db_path: str, save_id: str, target_turn_id: int
) -> dict[str, int]:
    """Standalone variant of :func:`rollback_observations` (opens its own conn).

    The in-session rewind path uses the connection-based variant so events,
    facts and beliefs roll back in one transaction; this helper is for tests and
    out-of-band cleanup.
    """
    with get_connection(db_path) as conn:
        result = rollback_observations(conn, save_id, target_turn_id)
        conn.commit()
    return result
