# Adventure Start Date Customization Documentation

## Objective
Allow universe creators to set a custom start hour and minute in addition to the start day for their universe in the Creator Studio's Events tab.

## Technical Design
1. **Model**: The `CalendarConfig` dataclass in `axiom/time_system.py` already supports `start_hour` and `start_minute`.
2. **Editor GUI**:
   - In `ScheduledEventsEditorWidget` (`ui/widgets/scheduled_events_editor.py`), add spinboxes for `start_hour` and `start_minute`.
   - Update form labels to be dynamic `QLabel` widgets instead of hardcoded strings in `addRow`.
   - Implement localized text updates for all labels in `retranslate_ui`.
   - Integrate `start_hour` and `start_minute` in the read (`set_events_and_calendar`), write (`collect_data`), and modification listener (`_on_cal_changed`).
3. **Localization**:
   - Add keys: `calendar_config`, `minutes_per_hour`, `hours_per_day`, `start_day`, `start_hour`, `start_minute`, `month_names_label`, `preview_start` in all 10 `core/locales/*.toml` files.
