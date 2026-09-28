"""mods/axiom.time/main.py

Official mod: axiom.time (Diegetic Time System, Calendar & Off-Screen Chronicler)
Provides:
1. Calendar formatting and in-game time calculation.
2. Slot contribution to axiom.turn:output_fields ("time_elapsed_minutes").
3. Slot contribution to axiom.turn:prompt_sections (dynamic in-game date & time).
4. Hook axiom.step:after_step:
   - Stages Timeline row in TurnWriteBatch
   - Detects and triggers Scheduled_Events
   - Triggers Chronicler off-screen world simulation if interval reached
5. Service "time" registration for UI and engine queries.
"""

from __future__ import annotations

from typing import Any

from axiom.kernel.context import ModContext
from axiom.logger import logger


class TimeService:
    """Public service exposed by axiom.time to the engine and UIs."""

    @staticmethod
    def format_time(db_path: str, minute: int) -> str:
        from axiom.schema import get_connection
        from axiom.time_system import CalendarConfig, TimeSystem
        try:
            with get_connection(db_path) as conn:
                row = conn.execute("SELECT value FROM Universe_Meta WHERE key = 'calendar';").fetchone()
                cal_str = row[0] if row and row[0] else "{}"
            return TimeSystem(CalendarConfig.from_json(cal_str)).get_time_string(minute)
        except Exception:
            return str(minute)

    @staticmethod
    def get_current_time(db_path: str, save_id: str) -> int:
        from axiom.db_helpers import get_current_time
        return get_current_time(db_path, save_id)

    @staticmethod
    def get_calendar(db_path: str) -> Any:
        from axiom.schema import get_connection
        from axiom.time_system import CalendarConfig
        with get_connection(db_path) as conn:
            row = conn.execute("SELECT value FROM Universe_Meta WHERE key = 'calendar';").fetchone()
            cal_str = row[0] if row and row[0] else "{}"
        return CalendarConfig.from_json(cal_str)


def on_time_elapsed(val: Any, ctx: Any) -> None:
    """Handler for output_fields 'time_elapsed_minutes' / 'elapsed_minutes'."""
    try:
        mins = int(val)
        if mins < 0:
            mins = 0
        ctx.elapsed_minutes = mins
        ctx.new_time = ctx.total_mins + mins
    except (ValueError, TypeError):
        pass


def build_time_prompt_section(ctx: Any) -> dict[str, str]:
    """Generates prompt section with current in-game time and instructions."""
    db_path = getattr(ctx, "db_path", "")
    current_time = getattr(ctx, "total_mins", 0)
    formatted = TimeService.format_time(db_path, current_time) if db_path else str(current_time)
    text = (
        f"IN-GAME TIME: Current date/time is {formatted} (minute {current_time}).\n"
        f"In your tool_call JSON, include \"time_elapsed_minutes\": <int> to specify how "
        f"many minutes of in-game time elapsed during the actions in this turn."
    )
    return {
        "position": "system",
        "text": text,
        "depth": 5,
    }


def on_after_step(ctx: Any) -> None:
    """Hook: axiom.step:after_step.
    
    1. Stages Timeline entry.
    2. Checks Scheduled_Events.
    3. Triggers off-screen Chronicler simulation if scheduled.
    """
    # 1. Timeline row
    timeline_desc = getattr(ctx, "travel_note", None) or f"Turn advanced by {ctx.elapsed_minutes} mins"
    ctx.write_batch.timeline_entries.append((ctx.save_id, ctx.turn_id, ctx.new_time, timeline_desc))

    # 2. Check and stage Scheduled_Events
    db_path = getattr(ctx, "db_path", "")
    if db_path:
        try:
            from axiom.schema import get_connection
            with get_connection(db_path) as conn:
                rows = conn.execute(
                    """
                    SELECT e.event_id
                    FROM Scheduled_Events e
                    LEFT JOIN Fired_Scheduled_Events f ON e.event_id = f.event_id AND f.save_id = ?
                    WHERE e.trigger_minute <= ? AND f.event_id IS NULL;
                    """,
                    (ctx.save_id, ctx.new_time),
                ).fetchall()
                for r in rows:
                    eid = str(r[0])
                    if eid not in ctx.write_batch.fired_scheduled_events:
                        ctx.write_batch.fired_scheduled_events.append(eid)
        except Exception as err:
            logger.debug("axiom.time: Scheduled_Events query skipped: %s", err)

    # 3. Off-screen world simulation (Chronicler)
    if db_path:
        try:
            from axiom.config import load_config
            cfg = load_config()
            interval = getattr(cfg, "chronicler_minutes_interval", 60)
            from axiom.chronicler import ChroniclerEngine
            from axiom.events import EventSourcer

            chronicler = ChroniclerEngine(
                llm=getattr(ctx, "_llm", None),
                event_sourcer=EventSourcer(db_path),
                db_path=db_path,
                trigger_interval=interval,
            )
            if chronicler.should_trigger(ctx.new_time, ctx.total_mins):
                ctx.write_batch.post_commit_callbacks.append(
                    lambda: chronicler.run(ctx.save_id, ctx.turn_id)
                )
        except Exception as err:
            logger.debug("axiom.time: Chronicler check skipped: %s", err)


def init(ctx: ModContext) -> None:
    """Mod entry point."""
    # Expose public service
    ctx.register_service("time", TimeService())

    # Output fields routing
    ctx.contribute_slot("axiom.turn:output_fields", ("time_elapsed_minutes", on_time_elapsed))
    ctx.contribute_slot("axiom.turn:output_fields", ("elapsed_minutes", on_time_elapsed))

    # Dynamic prompt sections
    ctx.contribute_slot("axiom.turn:prompt_sections", build_time_prompt_section)

    # Lifecycle hook
    ctx.register_hook("axiom.step:after_step", on_after_step)

    # Contribute sidebar widget to axiom.ui.qt
    try:
        from mods.axiom.time.ui.timeline_view import TimelineView
        ctx.contribute_slot("axiom.ui.qt:sidebar_widget", TimelineView)
    except Exception as exc:
        logger.debug("[axiom.time] Could not load TimelineView: %s", exc)

