import pytest
from PySide6.QtCore import Qt
from ui.widgets.scheduled_events_editor import ScheduledEventsEditorWidget
from axiom.time_system import CalendarConfig

def test_scheduled_events_editor_reads_and_writes_start_time(qtbot):
    widget = ScheduledEventsEditorWidget()
    qtbot.addWidget(widget)

    # Initial defaults
    assert widget._start_day_spin.value() == 1
    assert widget._start_hour_spin.value() == 0
    assert widget._start_minute_spin.value() == 0

    # Custom meta calendar config
    meta = {
        "calendar_config": CalendarConfig(
            minutes_per_hour=60,
            hours_per_day=24,
            start_day=5,
            start_hour=14,
            start_minute=30
        ).to_json()
    }

    # Populate the UI
    widget.set_events_and_calendar([], meta)

    # Check UI fields got populated correctly
    assert widget._start_day_spin.value() == 5
    assert widget._start_hour_spin.value() == 14
    assert widget._start_minute_spin.value() == 30

    # Modify values in UI
    widget._start_day_spin.setValue(10)
    widget._start_hour_spin.setValue(8)
    widget._start_minute_spin.setValue(15)

    # Collect data back
    events, collected_meta = widget.collect_data()
    
    # Assert collected meta matches updated values
    cal_cfg = CalendarConfig.from_json(collected_meta["calendar_config"])
    assert cal_cfg.start_day == 10
    assert cal_cfg.start_hour == 8
    assert cal_cfg.start_minute == 15
