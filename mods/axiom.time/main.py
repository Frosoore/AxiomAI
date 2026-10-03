"""mods/axiom.time/main.py

Official mod: axiom.time (Diegetic Time System, Calendar & Off-Screen Chronicler)

All of the in-game time of a turn lives here; without this mod no time passes:
1. `axiom.step:gather_context`: time of day and scheduled events due now (injected
   in the narration prompt by the turn).
2. Output field `elapsed_minutes` (sub-schema + instruction contributed to the
   turn's JSON block) and, at `axiom.step:response_parsed`, the fallback when the
   narrator did not say: the Timekeeper (time model), then a default per scene pace.
3. `axiom.step:after_step`: Timeline row and fired scheduled events staged in the
   turn's write batch; the Chronicler (off-screen simulation) after the commit.
4. Service "time" for the UIs (formatting with the universe calendar).
"""

from __future__ import annotations

import json
import re
from typing import Any

from axiom.kernel.context import ModContext
from axiom.logger import logger
from mods.axiom.time.time_prompts import build_timekeeper_prompt
from mods.axiom.time.time_system import CalendarConfig, TimeSystem, get_time_of_day_context

#: Minutes of a turn when neither the narrator nor the Timekeeper said (per scene pace).
PACE_DEFAULT_MINUTES = {
    "combat": 2,
    "dialogue": 5,
    "conversation": 5,
    "exploration": 15,
    "travel": 60,
    "deliberate": 15,
    "montage": 60,
    "tension": 10,
}


class TimeService:
    """Public service exposed by axiom.time to the engine and UIs."""

    @staticmethod
    def get_calendar(db_path: str) -> CalendarConfig:
        from axiom.schema import get_connection
        with get_connection(db_path) as conn:
            row = conn.execute("SELECT value FROM Universe_Meta WHERE key = 'calendar_config';").fetchone()
        return CalendarConfig.from_json(row[0] if row and row[0] else "{}")

    @classmethod
    def time_system(cls, db_path: str) -> TimeSystem:
        return TimeSystem(cls.get_calendar(db_path))

    @staticmethod
    def time_system_from_meta(calendar_json: str | None) -> TimeSystem:
        """TimeSystem of a universe from its stored calendar (Universe_Meta['calendar_config'])."""
        return TimeSystem(CalendarConfig.from_json(calendar_json or "{}"))

    @classmethod
    def format_time(cls, db_path: str, minute: int) -> str:
        try:
            return cls.time_system(db_path).get_time_string(minute)
        except Exception:
            logger.exception("[axiom.time] Could not format minute %s", minute)
            return str(minute)

    @staticmethod
    def get_current_time(db_path: str, save_id: str) -> int:
        from axiom.db_helpers import get_current_time
        return get_current_time(db_path, save_id)

    @staticmethod
    def time_of_day(minute: int) -> str:
        return get_time_of_day_context(minute)


# ---------------------------------------------------------------------------
# Turn
# ---------------------------------------------------------------------------

def on_gather_context(ctx: Any) -> None:
    """Time of day and the scheduled events due now (narrated this turn, fired with it)."""
    ctx.time_ctx = get_time_of_day_context(ctx.total_mins)
    ctx.triggered_events = []
    db_path = getattr(ctx, "db_path", "")
    if not db_path:
        return
    from axiom.schema import get_connection
    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT e.event_id, e.title, e.description
            FROM Scheduled_Events e
            LEFT JOIN Fired_Scheduled_Events f ON e.event_id = f.event_id AND f.save_id = ?
            WHERE e.trigger_minute <= ? AND f.event_id IS NULL;
            """,
            (ctx.save_id, ctx.total_mins),
        ).fetchall()
    ctx.triggered_events = [dict(r) for r in rows]


def on_time_elapsed(val: Any, ctx: Any) -> None:
    """Output field `elapsed_minutes`: the narrator's own estimate."""
    try:
        mins = max(0, int(val))
    except (ValueError, TypeError):
        return
    ctx.elapsed_minutes = mins
    ctx.new_time = ctx.total_mins + mins
    ctx.time_from_narrator = True


def _ask_timekeeper(ctx: Any) -> int | None:
    llm = getattr(ctx, "time_llm", None) or getattr(ctx, "llm", None)
    if llm is None:
        return None
    prompt = build_timekeeper_prompt(ctx.combined_intents_text, ctx.narrative_text)
    try:
        resp = llm.complete(prompt, max_tokens=150, temperature=0.1)
    except Exception as err:
        logger.error("[axiom.time] Timekeeper failed: %s", err)
        return None
    data = getattr(resp, "tool_call", None) or {}
    if not data:
        match = re.search(r"\{.*\}", getattr(resp, "narrative_text", str(resp)) or "", re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                data = {}
    try:
        return int(data["elapsed_minutes"]) if isinstance(data, dict) and "elapsed_minutes" in data else None
    except (TypeError, ValueError):
        return None


def on_response_parsed(ctx: Any) -> None:
    """The narrator gave no time: ask the Timekeeper, else use the scene pace default."""
    if getattr(ctx, "time_from_narrator", False):
        return
    legacy = (getattr(ctx, "parsed_tool_call", None) or {}).get("time_elapsed_minutes")
    if legacy is not None:  # key asked by older prompts; read, not requested anymore
        on_time_elapsed(legacy, ctx)
        if getattr(ctx, "time_from_narrator", False):
            return
    from axiom.config import load_config
    elapsed = _ask_timekeeper(ctx) if load_config().timekeeper_enabled else None
    if elapsed is None:
        elapsed = PACE_DEFAULT_MINUTES.get(ctx.scene_pace, 15)
    ctx.elapsed_minutes = max(0, elapsed)
    ctx.new_time = ctx.total_mins + ctx.elapsed_minutes


def on_after_step(ctx: Any) -> None:
    """Timeline row, fired scheduled events (staged with the turn), Chronicler."""
    description = getattr(ctx, "travel_note", None) or f"Turn advanced by {ctx.elapsed_minutes} mins"
    new_time = ctx.new_time
    fired = [str(ev["event_id"]) for ev in getattr(ctx, "triggered_events", []) or []]

    def write(conn: Any, save_id: str, turn_id: int) -> None:
        conn.execute(
            "INSERT INTO Timeline (save_id, turn_id, in_game_time, description) VALUES (?, ?, ?, ?);",
            (save_id, turn_id, new_time, description),
        )
        if fired:
            from axiom.schema import ensure_fired_event_turn_column
            ensure_fired_event_turn_column(conn)
            conn.executemany(
                "INSERT OR IGNORE INTO Fired_Scheduled_Events (save_id, event_id, fired_turn_id) "
                "VALUES (?, ?, ?);",
                [(save_id, eid, turn_id) for eid in fired],
            )

    ctx.write_batch.stage_op(write)

    # Off-screen world simulation, after the commit.
    db_path = getattr(ctx, "db_path", "")
    if not db_path:
        return
    from axiom.config import load_config
    from axiom.events import EventSourcer
    from mods.axiom.time.chronicler import ChroniclerEngine

    chronicler = ChroniclerEngine(
        llm=getattr(ctx, "llm", None),
        event_sourcer=EventSourcer(db_path),
        db_path=db_path,
        trigger_interval=getattr(load_config(), "chronicler_minutes_interval", 60),
    )
    if chronicler.should_trigger(ctx.new_time, ctx.total_mins):
        save_id, turn_id = ctx.save_id, ctx.turn_id
        ctx.write_batch.post_commit_callbacks.append(lambda: chronicler.run(save_id, turn_id))


ELAPSED_FIELD = {
    "name": "elapsed_minutes",
    "schema": 5,
    "instruction": (
        "Give the in-game minutes this turn took (integer: a short exchange 1-5, "
        "an action scene 10-30, a journey 60+)."
    ),
    "handler": on_time_elapsed,
}


def init(ctx: ModContext) -> None:
    """Mod entry point."""
    ctx.register_service("time", TimeService())
    ctx.contribute_slot("axiom.turn:output_fields", ELAPSED_FIELD)
    ctx.register_hook("axiom.step:gather_context", on_gather_context)
    ctx.register_hook("axiom.step:response_parsed", on_response_parsed)
    ctx.register_hook("axiom.step:after_step", on_after_step)

    # Contribute sidebar widget to axiom.ui.qt
    try:
        from mods.axiom.time.ui.timeline_view import TimelineView
        ctx.contribute_slot("axiom.ui.qt:sidebar_widget", TimelineView)
    except ImportError as exc:
        logger.debug("[axiom.time] Qt timeline view unavailable: %s", exc)
