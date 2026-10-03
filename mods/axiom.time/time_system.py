"""mods/axiom.time/time_system.py

Flexible time and calendar system for Axiom AI.
Allows custom minutes per hour, hours per day, and named months.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple

from axiom.kernel.patcher import patchable
from axiom.universe_format import calendar_from_meta, calendar_to_meta

# Libellés anglais par défaut des phases (dev / CLI / lib). Le moteur n'émet pas de
# texte traduit : il expose la CLÉ de phase, et le frontend la localise (TICKET-054).
_PHASE_LABELS_EN = {
    "dawn": "Dawn",
    "morning": "Morning",
    "afternoon": "Afternoon",
    "dusk": "Dusk",
    "night": "Night",
}


class TimeComponents(NamedTuple):
    """Decomposition of an instant into raw data (zero presentation/translation).

    `phase_key` is a stable key among dawn/morning/afternoon/dusk/night;
    `month_name` comes from the universe calendar (data, not a translation).
    """

    year: int
    month_name: str
    day: int
    hour: int
    minute: int
    phase_key: str


@dataclass
class CalendarConfig:
    """Configuration for a custom calendar."""

    minutes_per_hour: int = 60
    hours_per_day: int = 24
    days_per_month: list[int] = field(default_factory=lambda: [30] * 12)
    month_names: list[str] = field(
        default_factory=lambda: [
            "Month 1",
            "Month 2",
            "Month 3",
            "Month 4",
            "Month 5",
            "Month 6",
            "Month 7",
            "Month 8",
            "Month 9",
            "Month 10",
            "Month 11",
            "Month 12",
        ]
    )
    start_day: int = 1
    start_hour: int = 0
    start_minute: int = 0

    @property
    def minutes_per_day(self) -> int:
        return self.minutes_per_hour * self.hours_per_day

    @property
    def minutes_per_year(self) -> int:
        return sum(self.days_per_month) * self.minutes_per_day

    def to_json(self) -> str:
        """The ``Universe_Meta['calendar_config']`` JSON (format owned by the kernel compiler)."""
        return calendar_to_meta({
            "minutes_per_hour": self.minutes_per_hour,
            "hours_per_day": self.hours_per_day,
            "days_per_month": self.days_per_month,
            "month_names": self.month_names,
            "start_day": self.start_day,
            "start_hour": self.start_hour,
            "start_minute": self.start_minute,
        })

    @classmethod
    def from_json(cls, data_str: str) -> CalendarConfig:
        return cls(**calendar_from_meta(data_str))


class TimeSystem:
    """Handles time conversion and formatting based on a CalendarConfig."""

    def __init__(self, config: CalendarConfig | None = None) -> None:
        self.config = config or CalendarConfig()

    def get_time_components(self, total_minutes: int) -> TimeComponents:
        """Decompose cumulative minutes into (year, month, day, h, min, phase key).

        Raw data only: no translation. The frontend localises the display from
        these fields.
        """
        cfg = self.config

        # Adjust by start time
        start_offset = (
            ((cfg.start_day - 1) * cfg.minutes_per_day)
            + (cfg.start_hour * cfg.minutes_per_hour)
            + cfg.start_minute
        )

        abs_mins = total_minutes + start_offset

        # Calculate Year
        year = (abs_mins // cfg.minutes_per_year) + 1
        rem_mins = abs_mins % cfg.minutes_per_year

        # Calculate Month and Day
        month_idx = 0
        mins_in_month = [d * cfg.minutes_per_day for d in cfg.days_per_month]
        for i, m_mins in enumerate(mins_in_month):
            if rem_mins < m_mins:
                month_idx = i
                break
            rem_mins -= m_mins

        day = (rem_mins // cfg.minutes_per_day) + 1
        rem_mins %= cfg.minutes_per_day

        hour = rem_mins // cfg.minutes_per_hour
        minute = rem_mins % cfg.minutes_per_hour

        month_name = (
            cfg.month_names[month_idx] if month_idx < len(cfg.month_names) else "Unknown"
        )

        # Simple phase detection based on fractional day → clé stable (non traduite).
        day_progress = (hour * cfg.minutes_per_hour + minute) / cfg.minutes_per_day
        if 0.2 < day_progress < 0.35:
            phase_key = "dawn"
        elif 0.35 <= day_progress < 0.5:
            phase_key = "morning"
        elif 0.5 <= day_progress < 0.7:
            phase_key = "afternoon"
        elif 0.7 <= day_progress < 0.85:
            phase_key = "dusk"
        else:
            phase_key = "night"

        return TimeComponents(year, month_name, day, hour, minute, phase_key)

    def get_time_string(self, total_minutes: int) -> str:
        """Default English rendering (dev / CLI / library). Zero engine-side localisation.

        The GUI does NOT go through here: it formats through its own localisation
        layer to display in the user's language.
        """
        c = self.get_time_components(total_minutes)
        phase = _PHASE_LABELS_EN.get(c.phase_key, c.phase_key)
        return f"Year {c.year}, {c.month_name} {c.day}, {c.hour:02d}:{c.minute:02d} ({phase})"

    def components_to_minutes(self, day: int, hour: int, minute: int) -> int:
        """Convert a simplified (Day, Hour, Min) UI input back to cumulative session minutes."""
        return (
            ((day - 1) * self.config.minutes_per_day)
            + (hour * self.config.minutes_per_hour)
            + minute
        )

    def minutes_to_components(self, total_minutes: int) -> tuple[int, int, int]:
        """Convert session minutes back to Day, Hour, Min."""
        cfg = self.config
        day = (total_minutes // cfg.minutes_per_day) + 1
        rem = total_minutes % cfg.minutes_per_day
        hour = rem // cfg.minutes_per_hour
        minute = rem % cfg.minutes_per_hour
        return day, hour, minute


@patchable("mods.axiom.time.time_system:get_time_of_day_context")
def get_time_of_day_context(total_minutes: int) -> str:
    """Convert total minutes into a descriptive Day, Time, and Phase string.

    Args:
        total_minutes: Cumulative in-game minutes.

    Returns:
        Formatted string: "Day X, HH:MM (Phase)"
    """
    days = (total_minutes // 1440) + 1
    hours = (total_minutes % 1440) // 60
    mins = total_minutes % 60

    # Determine Phase
    if 5 <= hours < 8:
        phase = "Dawn"
    elif 8 <= hours < 12:
        phase = "Morning"
    elif 12 <= hours < 17:
        phase = "Afternoon"
    elif 17 <= hours < 21:
        phase = "Dusk"
    else:
        phase = "Night"

    return f"Day {days}, {hours:02d}:{mins:02d} ({phase})"
