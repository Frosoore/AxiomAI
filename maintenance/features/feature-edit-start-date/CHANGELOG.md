# CHANGELOG - Adventure Start Date Customization

## [Unreleased]
### Added
- Created the feature step files (`TODO.md`, `CHANGELOG.md`, `DOC.md`).
- Added `_start_hour_spin` and `_start_minute_spin` controls in `ScheduledEventsEditorWidget`.
- Localized the calendar group title and form labels (`calendar_config`, `minutes_per_hour`, `hours_per_day`, `start_day`, `start_hour`, `start_minute`, `month_names_label`, `preview_start`) dynamically using `retranslate_ui`.
- Appended the new translation keys for all 10 languages in `core/locales/*.toml`.
- Linked the start hour and minute values in the load (`set_events_and_calendar`), save (`collect_data`), and change (`_on_cal_changed`) pipelines.
