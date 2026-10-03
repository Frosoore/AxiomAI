"""Headless living-memory distillation (facts → beliefs → mental models).

Used by the Qt ``FactExtractWorker`` and the web server after turns so both
frontends share one pipeline. Never raises to the caller for LLM/storage
failures: returns how many facts were stored (0 is normal).
"""

from __future__ import annotations

import json
import threading
from typing import Any, Callable

from axiom.backends.base import LLMBackend
try:
    from .consolidate import consolidate
    from .factextract import extract_facts
    from .facts import get_facts, insert_facts
    from .observations import apply_consolidation, get_observations
    from .missions import get_belief_missions, get_universe_mission
    from .mental_models import stale_subjects, upsert_mental_model
    from .reflect import affected_subjects, reflect
except (ImportError, ValueError):
    from mods.axiom.living_memory.consolidate import consolidate
    from mods.axiom.living_memory.factextract import extract_facts
    from mods.axiom.living_memory.facts import get_facts, insert_facts
    from mods.axiom.living_memory.observations import apply_consolidation, get_observations
    from mods.axiom.living_memory.missions import get_belief_missions, get_universe_mission
    from mods.axiom.living_memory.mental_models import stale_subjects, upsert_mental_model
    from mods.axiom.living_memory.reflect import affected_subjects, reflect

# Cap on how many subjects get a (costly LLM) mental-model refresh in one pass.
_MAX_MODEL_REFRESH = 3

_STALE = object()


def _epoch_guarded(
    save_id: str,
    epoch: int | None,
    epoch_checker: Callable[[], int] | None,
    write: Callable[[], Any],
) -> Any:
    """Run ``write`` only if the save's epoch is still ``epoch``, atomically.

    The check and the write happen under the epoch manager's write guard, so a
    rewind/fork/load cannot bump the epoch in between (R2-m-6): either the job
    sees the new epoch and writes nothing, or the rewind waits for the write and
    then removes it. Returns ``_STALE`` when the write was discarded.
    """
    if epoch is None:
        return write()
    from axiom.epoch import get_session_epoch_manager
    from axiom.logger import logger

    mgr = get_session_epoch_manager(save_id)
    with mgr.guarded_write(epoch, epoch_checker) as valid:
        if not valid:
            logger.warning(
                "Époque de session périmée (capturée %d) pour la save %s. Écriture ignorée.",
                epoch,
                save_id,
            )
            return _STALE
        return write()


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
    epoch: int | None = None,
    epoch_checker: Callable[[], int] | None = None,
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

        new_ids = _epoch_guarded(
            save_id, epoch, epoch_checker,
            lambda: insert_facts(db_path, save_id, turn_id, facts),
        )
        if new_ids is _STALE:
            return empty
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
                epoch=epoch,
                epoch_checker=epoch_checker,
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
    epoch: int | None = None,
    epoch_checker: Callable[[], int] | None = None,
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
                epoch=epoch,
                epoch_checker=epoch_checker,
            )
            totals["facts_stored"] += int(result.get("facts_stored", 0) or 0)
            last_turn = int(tid)
        except Exception:
            if raise_on_error:
                raise
            continue

    if consolidate_beliefs and totals["facts_stored"] > 0:
        try:

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
                epoch=epoch,
                epoch_checker=epoch_checker,
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
    epoch: int | None = None,
    epoch_checker: Callable[[], int] | None = None,
) -> dict[str, int]:
    """Run belief consolidation on **already stored** facts (no re-extract).

    Used when Extract now has nothing new in the narrative buffer but Facts
    exist and Beliefs/Profiles are still empty (e.g. prior pass stored facts
    then soft-failed on consolidation).
    """
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
        epoch=epoch,
        epoch_checker=epoch_checker,
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
    epoch: int | None = None,
    epoch_checker: Callable[[], int] | None = None,
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

        counts = _epoch_guarded(
            save_id, epoch, epoch_checker,
            lambda: apply_consolidation(db_path, save_id, turn_id, actions, fact_turn_map),
        )
        if counts is _STALE:
            return 0, 0
        beliefs_touched = int(
            counts.get("created", 0)
            + counts.get("updated", 0)
            + counts.get("deleted", 0)
        )
        models_refreshed = 0
        if refresh_mental_models:
            models_refreshed = _refresh_models(
                llm, db_path, save_id, turn_id, actions, mission,
                epoch=epoch, epoch_checker=epoch_checker,
            )
        return beliefs_touched, models_refreshed
    except Exception:
        if raise_on_error:
            raise
        return 0, 0


def _refresh_models(llm, db_path, save_id, turn_id, actions, mission, *, epoch: int | None = None, epoch_checker: Callable[[], int] | None = None) -> int:
    """Refresh mental models for affected subjects. Returns how many written."""
    try:
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
            res = _epoch_guarded(
                save_id, epoch, epoch_checker,
                lambda: upsert_mental_model(db_path, save_id, subj, summary, turn_id, sources=src),
            )
            if res is _STALE:
                return written
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


class LivingMemoryAccumulator:
    """Headless accumulator and background distillation scheduler for living memory.

    Encapsulates the in-memory turn prose buffer, turn counter, and background
    distillation thread so all frontends (Web, GUI, CLI) share a single headless
    component without ad-hoc global buffers.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, list[str]] = {}
        self._counters: dict[str, int] = {}
        self._busy: set[str] = set()
        self._mod_ctx: Any | None = None

    def set_context(self, ctx: Any) -> None:
        self._mod_ctx = ctx

    def reset(self, save_id: str | None = None) -> None:
        """Clear pending buffer and turn counter (for a save or all saves)."""
        with self._lock:
            if save_id is not None:
                self._pending.pop(save_id, None)
                self._counters.pop(save_id, None)
            else:
                self._pending.clear()
                self._counters.clear()

    def record_turn(
        self,
        db_path: str,
        save_id: str,
        turn_id: int,
        narrative_text: str,
        *,
        cfg: Any = None,
        llm: LLMBackend | None = None,
        force_async: bool = True,
        epoch: int | None = None,
        epoch_checker: Callable[[], int] | None = None,
    ) -> bool:
        """Buffer turn prose; schedule distillation every N turns (living mode)."""
        text = (narrative_text or "").strip()
        if not text:
            return False

        if cfg is None:
            from axiom.config import load_config
            cfg = load_config()

        from axiom.config import memory_mode_is_living
        if not memory_mode_is_living(cfg):
            return False

        interval = int(getattr(cfg, "memory_fact_interval", 0) or 0)
        with self._lock:
            self._pending.setdefault(save_id, []).append(text)
            self._counters[save_id] = self._counters.get(save_id, 0) + 1
            counter_hit = interval > 0 and self._counters[save_id] >= interval

        if counter_hit:
            self.spawn_distillation(
                db_path,
                save_id,
                turn_id,
                cfg=cfg,
                llm=llm,
                force_catchup=True,
                run_async=force_async,
                epoch=epoch,
                epoch_checker=epoch_checker,
            )
            return True
        return False

    def spawn_distillation(
        self,
        db_path: str,
        save_id: str,
        turn_id: int,
        *,
        cfg: Any = None,
        llm: LLMBackend | None = None,
        force_catchup: bool = True,
        run_async: bool = True,
        epoch: int | None = None,
        epoch_checker: Callable[[], int] | None = None,
    ) -> Any:
        """Fire background distillation job (does not block the turn)."""
        from axiom.epoch import get_session_epoch_manager
        mgr = get_session_epoch_manager(save_id)
        captured_epoch = epoch if epoch is not None else mgr.current
        if epoch_checker is None:
            epoch_checker = lambda: mgr.current

        with self._lock:
            if save_id in self._busy:
                return None
            pending = list(self._pending.get(save_id, []))
            self._pending[save_id] = []
            self._counters[save_id] = 0
            self._busy.add(save_id)

        def _job() -> dict:
            try:
                from axiom.logger import logger
                if captured_epoch is not None and epoch_checker is not None:
                    curr_epoch = epoch_checker()
                    if captured_epoch != curr_epoch:
                        logger.warning(
                            "Époque de session périmée (%d vs %d). Écriture ignorée.",
                            captured_epoch,
                            curr_epoch,
                        )
                        return {"status": "stale_epoch", "facts_stored": 0}

                nonlocal cfg, llm
                if cfg is None:
                    from axiom.config import load_config
                    cfg = load_config()
                if llm is None:
                    from axiom.config import resolve_memory_fact_model
                    from axiom.session import resolve_llm_backend  # axiom.providers only (M8)
                    llm = resolve_llm_backend(cfg, model_override=resolve_memory_fact_model(cfg))

                from axiom.config import memory_beliefs_active, memory_mental_models_active
                turn_pairs: list[tuple[int, str]] = []
                if force_catchup:
                    try:
                        after = last_fact_turn(db_path, save_id)
                        pairs = recent_narratives_since(
                            db_path, save_id, after_turn_id=after, up_to_turn_id=turn_id
                        )
                        turn_pairs = pairs[-6:]
                    except Exception:
                        from axiom.logger import logger
                        logger.exception("Living-memory Event_Log catch-up failed")

                if not turn_pairs and pending:
                    turn_pairs = [(turn_id, "\n\n".join(pending))]

                if not turn_pairs:
                    return {"status": "ok", "facts_stored": 0}

                result = distil_turns_to_memory(
                    llm,
                    db_path,
                    save_id,
                    turn_pairs,
                    consolidate_beliefs=memory_beliefs_active(cfg),
                    refresh_mental_models=memory_mental_models_active(cfg),
                    max_turns=6,
                    epoch=captured_epoch,
                    epoch_checker=epoch_checker,
                )
                from axiom.logger import logger
                logger.info(
                    "Living-memory job done for save %s: facts=%s beliefs=%s models=%s",
                    save_id,
                    result.get("facts_stored"),
                    result.get("beliefs_touched"),
                    result.get("models_refreshed"),
                )
                return result
            except Exception:
                from axiom.logger import logger
                logger.exception("Background living-memory job failed for save %s", save_id)
                return {"status": "error", "facts_stored": 0}
            finally:
                with self._lock:
                    self._busy.discard(save_id)

        if run_async:
            if getattr(self, "_mod_ctx", None) is not None:
                return self._mod_ctx.spawn_job(_job, name=f"axiom.living_memory:{save_id}:{turn_id}")
            thread = threading.Thread(target=_job, daemon=True)
            thread.start()
            return thread
        return _job()

    def run_extract_now(
        self,
        db_path: str,
        save_id: str,
        turn_id: int,
        *,
        cfg: Any = None,
        llm: LLMBackend | None = None,
        force_catchup: bool = False,
    ) -> dict:
        """Run synchronous extract now for UI / API endpoints.

        Epoch-guarded like the background job: a rewind/fork/load of the save
        while the (slow) LLM extraction runs makes its writes be discarded.
        """
        from axiom.epoch import get_session_epoch_manager
        captured_epoch = get_session_epoch_manager(save_id).current

        with self._lock:
            pending = list(self._pending.get(save_id, []))
            self._pending[save_id] = []
            self._counters[save_id] = 0

        if cfg is None:
            from axiom.config import load_config
            cfg = load_config()

        from axiom.config import (
            memory_beliefs_active,
            memory_mental_models_active,
            memory_mode_is_living,
            resolve_memory_fact_model,
        )
        from axiom.session import resolve_llm_backend  # axiom.providers only (M8)
        if not memory_mode_is_living(cfg):
            return {
                "status": "skipped",
                "error": "Living memory is off (Settings → Memory mode).",
                "facts_stored": 0,
            }

        turn_pairs: list[tuple[int, str]] = []
        if force_catchup:
            after = last_fact_turn(db_path, save_id)
            turn_pairs = recent_narratives_since(
                db_path, save_id, after_turn_id=after, up_to_turn_id=turn_id
            )
            turn_pairs = turn_pairs[-8:]
        if not turn_pairs and pending:
            turn_pairs = [(turn_id, "\n\n".join(pending))]

        override = resolve_memory_fact_model(cfg)
        if llm is None:
            try:
                llm = resolve_llm_backend(cfg, model_override=override)
            except Exception as exc:
                return {
                    "status": "error",
                    "error": f"Could not build memory LLM: {exc}",
                    "facts_stored": 0,
                }

        if turn_pairs:
            result = distil_turns_to_memory(
                llm,
                db_path,
                save_id,
                turn_pairs,
                consolidate_beliefs=memory_beliefs_active(cfg),
                refresh_mental_models=memory_mental_models_active(cfg),
                raise_on_error=True,
                max_turns=8,
                epoch=captured_epoch,
            )
        elif force_catchup and memory_beliefs_active(cfg):
            existing_beliefs = get_observations(db_path, save_id, max_turn_id=turn_id)
            if existing_beliefs:
                return {
                    "status": "ok",
                    "facts_stored": 0,
                    "beliefs_touched": 0,
                    "models_refreshed": 0,
                    "message": "Nothing new to distil (facts and beliefs already up to date).",
                }
            result = consolidate_facts_to_beliefs(
                llm,
                db_path,
                save_id,
                turn_id,
                refresh_mental_models=memory_mental_models_active(cfg),
                raise_on_error=True,
                epoch=captured_epoch,
            )
        else:
            return {
                "status": "ok",
                "facts_stored": 0,
                "message": "Nothing new to distil.",
            }

        if isinstance(result, dict):
            n_facts = int(result.get("facts_stored", 0) or 0)
            n_beliefs = int(result.get("beliefs_touched", 0) or 0)
            n_models = int(result.get("models_refreshed", 0) or 0)
        else:
            n_facts, n_beliefs, n_models = int(result or 0), 0, 0

        parts = []
        if n_facts:
            parts.append(f"{n_facts} fact(s)")
        if n_beliefs:
            parts.append(f"{n_beliefs} belief update(s)")
        if n_models:
            parts.append(f"{n_models} profile(s)")
        message = (
            ("Stored " + ", ".join(parts) + ".")
            if parts
            else "Model returned no new facts/beliefs for this slice (try more turns, or check extraction model)."
        )
        return {
            "status": "ok",
            "facts_stored": n_facts,
            "beliefs_touched": n_beliefs,
            "models_refreshed": n_models,
            "message": message,
        }


_DEFAULT_ACCUMULATOR: LivingMemoryAccumulator | None = None


def get_living_memory_accumulator() -> LivingMemoryAccumulator:
    """Return the process-wide default LivingMemoryAccumulator instance."""
    global _DEFAULT_ACCUMULATOR
    if _DEFAULT_ACCUMULATOR is None:
        _DEFAULT_ACCUMULATOR = LivingMemoryAccumulator()
    return _DEFAULT_ACCUMULATOR
