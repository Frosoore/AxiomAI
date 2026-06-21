# TODO - Saves Sorting Feature

- [x] Update database schema in `axiom/schema.py` to add `created_at` column in `_DDL_SAVES`.
- [x] Update `migrate_saves_table` in `axiom/schema.py` to add the column dynamically and default it to `last_updated`.
- [x] Update `create_new_save` in `axiom/db_helpers.py` to write `created_at`.
- [x] Update `load_saves` in `axiom/db_helpers.py` to query and return `created_at`.
- [x] Update `duplicate_save` in `axiom/savestore.py` to set `created_at` on duplicate.
- [x] Add combobox and label UI controls for sorting in the Saves tab in `ui/setup_view.py`.
- [x] Register the new undocumented widget `"sort_saves"` under `"setup"` in `ui/help_system.py`.
- [x] Implement saves sorting logic (`_display_saves` and `_on_sort_changed`) in `ui/setup_view.py`.
- [x] Add translation keys (`sort_by`, `sort_last_updated`, `sort_creation_date`, `doc_setup_sort_saves_t`, `doc_setup_sort_saves`) in all 10 `core/locales/*.toml` files.
- [x] Retranslate sorting labels and combobox items in `retranslate_ui` in `ui/setup_view.py`.
- [x] Run i18n checks, documentation check, and full test suite to guarantee everything is green.
