# CHANGELOG - Saves Sorting Feature

## [Unreleased]
### Added
- Created the feature step files (`TODO.md`, `CHANGELOG.md`, `DOC.md`).
- Extended the `Saves` table schema in `axiom/schema.py` to include a `created_at` timestamp.
- Updated database migrations in `axiom/schema.py` to add the column dynamically and migrate existing records by mapping `created_at` to `last_updated`.
- Recorded initial creation date timestamps when creating saves (`create_new_save` in `axiom/db_helpers.py`), duplicating saves (`duplicate_save` in `axiom/savestore.py`), and forking saves.
- Selected and returned the `created_at` values in the save loading pipeline.
- Implemented a sorting dropdown (`sort_by`, `sort_last_updated`, `sort_creation_date`) at the top of the saves list in the launch view (`ui/setup_view.py`).
- Mapped saves sorting to the in-app help system registry in `ui/help_system.py`.
- Translated all new keys into all 10 supported languages under `core/locales/*.toml`.
- Displayed both formatted date-time values (last updated and creation date/time) directly in the UI list items for each save.
- Handled dynamic re-translation of the list item date labels upon UI language change.
- Added unit tests verifying UI sorting behavior and formatting assertions under `tests/test_saves_sorting.py`.
