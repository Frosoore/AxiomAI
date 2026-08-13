"""Headless living-memory distillation (facts → beliefs → mental models).

Used by the Qt ``FactExtractWorker`` and the web server after turns so both
frontends share one pipeline. Never raises to the caller for LLM/storage
failures: returns how many facts were stored (0 is normal).
"""

from __future__ import annotations

from axiom.backends.base import LLMBackend
from axiom.consolidate import consolidate
from axiom.factextract import extract_facts
from axiom.facts import insert_facts
from axiom.observations import apply_consolidation, get_observations

# Cap on how many subjects get a (costly LLM) mental-model refresh in one pass.
_MAX_MODEL_REFRESH = 3


def distil_narrative_to_memory(
    llm: LLMBackend,
    db_path: str,
    save_id: str,
    turn_id: int,
    narrative_text: str,
    *,
    known_entities: list[str] | None = None,
    when_hint: str | None = None,
    max_facts: int = 8,
    consolidate_beliefs: bool = False,
    refresh_mental_models: bool = False,
    raise_on_error: bool = False,
) -> dict[str, int]:
    """Extract facts from ``narrative_text`` and optionally consolidate beliefs.

    Returns:
        Counts dict: ``facts_stored``, ``beliefs_touched``, ``models_refreshed``.
        Soft failures return zeros (unless ``raise_on_error``).

    When ``raise_on_error`` is True (manual Extract now), LLM/storage failures
    propagate so the UI can show a real error instead of a silent 0.
    Background post-turn jobs keep the default soft-fail behaviour.
    """
    empty = {"facts_stored": 0, "beliefs_touched": 0, "models_refreshed": 0}
    text = (narrative_text or "").strip()
    if not text:
        return empty
    try:
        facts = extract_facts(
            llm,
            text,
            known_entities=known_entities or [],
            when_hint=when_hint,
            max_facts=max_facts,
        )
        if not facts:
            return empty
        new_ids = insert_facts(db_path, save_id, turn_id, facts)
        stored_count = len(new_ids)
        beliefs_touched = 0
        models_refreshed = 0
        if consolidate_beliefs and new_ids:
            beliefs_touched, models_refreshed = _run_consolidation(
                llm,
                db_path,
                save_id,
                turn_id,
                facts,
                refresh_mental_models=refresh_mental_models,
                raise_on_error=raise_on_error,
            )
        return {
            "facts_stored": stored_count,
            "beliefs_touched": beliefs_touched,
            "models_refreshed": models_refreshed,
        }
    except Exception:
        if raise_on_error:
            raise
        return empty


def distil_turns_to_memory(
    llm: LLMBackend,
    db_path: str,
    save_id: str,
    turn_texts: list[tuple[int, str]],
    *,
    known_entities: list[str] | None = None,
    when_hint: str | None = None,
    max_facts_per_turn: int = 6,
    consolidate_beliefs: bool = False,
    refresh_mental_models: bool = False,
    raise_on_error: bool = False,
    max_turns: int = 8,
) -> dict[str, int]:
    """Extract facts **one turn at a time** then optionally consolidate once.

    Catch-up / auto extract used to glue 5–12 long narratives into one prompt.
    Reasoning models (deepseek-v4, etc.) then spent the whole token budget on
    CoT and returned empty/truncated JSON → silent 0 facts for the whole
    window. Per-turn extraction is slower but reliable.
    """
    totals = {"facts_stored": 0, "beliefs_touched": 0, "models_refreshed": 0}
    if not turn_texts:
        return totals
    # Oldest first; cap so one background job cannot run forever.
    batch = list(turn_texts)[-max_turns:]
    all_new_facts = []
    last_turn = batch[-1][0]
    for tid, text in batch:
        text = (text or "").strip()
        if not text:
            continue
        try:
            result = distil_narrative_to_memory(
                llm,
                db_path,
                save_id,
                int(tid),
                text,
                known_entities=known_entities,
                when_hint=when_hint,
                max_facts=max_facts_per_turn,
                # Defer consolidation until the full batch is stored.
                consolidate_beliefs=False,
                refresh_mental_models=False,
                raise_on_error=raise_on_error,
            )
            totals["facts_stored"] += int(result.get("facts_stored", 0) or 0)
            last_turn = int(tid)
        except Exception:
            if raise_on_error:
                raise
            continue

    if consolidate_beliefs and totals["facts_stored"] > 0:
        try:
            from axiom.facts import get_facts

            # Consolidate only the freshly written window (recent facts).
            recent = get_facts(
                db_path, save_id, max_turn_id=last_turn, limit=max_facts_per_turn * len(batch)
            )
            b, m = _run_consolidation(
                llm,
                db_path,
                save_id,
                last_turn,
                recent,
                refresh_mental_models=refresh_mental_models,
                raise_on_error=raise_on_error,
            )
            totals["beliefs_touched"] = b
            totals["models_refreshed"] = m
        except Exception:
            if raise_on_error:
                raise
    return totals


def consolidate_facts_to_beliefs(
    llm: LLMBackend,
    db_path: str,
    save_id: str,
    turn_id: int,
    *,
    refresh_mental_models: bool = False,
    raise_on_error: bool = False,
    max_facts: int = 24,
) -> dict[str, int]:
    """Run belief consolidation on **already stored** facts (no re-extract).

    Used when Extract now has nothing new in the narrative buffer but Facts
    exist and Beliefs/Profiles are still empty (e.g. prior pass stored facts
    then soft-failed on consolidation).
    """
    from axiom.facts import get_facts

    facts = get_facts(db_path, save_id, max_turn_id=turn_id, limit=max_facts)
    # get_facts is most-recent-first; consolidator is fine with that order.
    if not facts:
        return {"facts_stored": 0, "beliefs_touched": 0, "models_refreshed": 0}
    beliefs_touched, models_refreshed = _run_consolidation(
        llm,
        db_path,
        save_id,
        turn_id,
        facts,
        refresh_mental_models=refresh_mental_models,
        raise_on_error=raise_on_error,
    )
    return {
        "facts_stored": 0,
        "beliefs_touched": beliefs_touched,
        "models_refreshed": models_refreshed,
    }


def _run_consolidation(
    llm: LLMBackend,
    db_path: str,
    save_id: str,
    turn_id: int,
    facts,
    *,
    refresh_mental_models: bool,
    raise_on_error: bool = False,
) -> tuple[int, int]:
    """Belief consolidation + optional mental-model refresh.

    Returns:
        ``(beliefs_touched, models_refreshed)``.
    """
    try:
        stored = [f for f in facts if f.fact_id is not None]
        if not stored:
            return 0, 0
        existing = get_observations(db_path, save_id, max_turn_id=turn_id)
        from axiom.missions import get_belief_missions, get_universe_mission

        mission = get_universe_mission(db_path) or None
        missions = get_belief_missions(db_path)
        actions = consolidate(
            llm, stored, existing, mission=mission, missions=missions
        )
        if not actions:
            return 0, 0
        # Map each cited fact_id to *its* turn (not the pass turn) so rollback
        # keys stay correct when consolidating a mixed-age fact batch.
        fact_turn_map = {
            int(f.fact_id): int(f.turn_id if f.turn_id is not None else turn_id)
            for f in stored
            if f.fact_id is not None
        }
        counts = apply_consolidation(
            db_path, save_id, turn_id, actions, fact_turn_map
        )
        beliefs_touched = int(
            counts.get("created", 0)
            + counts.get("updated", 0)
            + counts.get("deleted", 0)
        )
        models_refreshed = 0
        if refresh_mental_models:
            models_refreshed = _refresh_models(
                llm, db_path, save_id, turn_id, actions, mission
            )
        return beliefs_touched, models_refreshed
    except Exception:
        if raise_on_error:
            raise
        return 0, 0


def _refresh_models(llm, db_path, save_id, turn_id, actions, mission) -> int:
    """Refresh mental models for affected subjects. Returns how many written."""
    try:
        from axiom.mental_models import stale_subjects, upsert_mental_model
        from axiom.reflect import affected_subjects, reflect

        subjects = affected_subjects(actions)
        seen = {s.strip().lower() for s in subjects}
        for s in stale_subjects(db_path, save_id, max_turn_id=turn_id):
            if s.strip().lower() not in seen:
                subjects.append(s)
                seen.add(s.strip().lower())

        written = 0
        for subj in subjects[:_MAX_MODEL_REFRESH]:
            beliefs = get_observations(
                db_path, save_id, subject=subj, max_turn_id=turn_id
            )
            summary = reflect(llm, subj, beliefs, mission=mission)
            if not summary:
                continue
            src = [o.observation_id for o in beliefs if o.observation_id is not None]
            upsert_mental_model(
                db_path, save_id, subj, summary, turn_id, sources=src
            )
            written += 1
        return written
    except Exception:
        return 0


def recent_narratives_since(
    db_path: str,
    save_id: str,
    *,
    after_turn_id: int,
    up_to_turn_id: int | None = None,
) -> list[tuple[int, str]]:
    """Load narrative_text payloads for turns ``after_turn_id < t <= up_to``.

    Returns list of ``(turn_id, plain_text)`` oldest-first. Used for catch-up
    extraction when the buffer is empty (e.g. after playing on web).
    """
    import json

    from axiom.schema import get_connection

    sql = (
        "SELECT turn_id, payload FROM Event_Log "
        "WHERE save_id = ? AND event_type = 'narrative_text' AND turn_id > ?"
    )
    params: list[object] = [save_id, int(after_turn_id)]
    if up_to_turn_id is not None:
        sql += " AND turn_id <= ?"
        params.append(int(up_to_turn_id))
    sql += " ORDER BY turn_id ASC"

    out: list[tuple[int, str]] = []
    with get_connection(db_path) as conn:
        rows = conn.execute(sql, params).fetchall()
    for row in rows:
        payload = row["payload"]
        text = ""
        try:
            data = json.loads(payload) if isinstance(payload, str) else payload
            if isinstance(data, dict) and "variants" in data:
                variants = data.get("variants") or []
                active = int(data.get("active") or 0)
                if 0 <= active < len(variants):
                    text = str(variants[active])
                elif variants:
                    text = str(variants[0])
            elif isinstance(data, dict):
                text = str(data.get("text") or data.get("content") or "")
            else:
                text = str(data or "")
        except Exception:
            text = str(payload or "")
        text = text.strip()
        if text:
            out.append((int(row["turn_id"]), text))
    return out


def last_fact_turn(db_path: str, save_id: str) -> int:
    """Highest turn_id that already has facts for this save (0 if none)."""
    from axiom.schema import ensure_facts_table, get_connection

    with get_connection(db_path) as conn:
        ensure_facts_table(conn)
        row = conn.execute(
            "SELECT MAX(turn_id) AS m FROM Facts WHERE save_id = ?;",
            (save_id,),
        ).fetchone()
    if row is None or row["m"] is None:
        return 0
    return int(row["m"])
