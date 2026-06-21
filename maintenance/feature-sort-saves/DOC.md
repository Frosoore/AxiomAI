# Saves Sorting Documentation

## Objective
Provide the user with the ability to sort their saves list either by "Last Updated" or "Creation Date".

## Technical Design
1. **Schema & Migration**:
   - Added a `created_at` column to the `Saves` table definition in `axiom/schema.py`.
   - Updated `migrate_saves_table` to add the column to existing databases and set `created_at = last_updated` for all pre-existing rows.
2. **Saves IO**:
   - `create_new_save` and `duplicate_save` populate the `created_at` column.
   - `load_saves` selects `created_at` and returns it.
3. **UI Layout**:
   - In `ui/setup_view.py`, a horizontal layout with a sorting QLabel and QComboBox is inserted above the saves list.
   - Changing the selection triggers `_on_sort_changed` which sorts the loaded saves in-memory and refreshes the list items.
4. **Help System & Localization**:
   - Registered the sorting control key `setup.sort_saves` in `ui/help_system.py`.
   - Populated the translation keys `sort_by`, `sort_last_updated`, `sort_creation_date`, `doc_setup_sort_saves_t`, and `doc_setup_sort_saves` across all 10 translation files in `core/locales/`.
