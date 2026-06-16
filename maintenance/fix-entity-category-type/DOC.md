# DOC — Fix Entity Category/Type in Creator Studio

## Objective
Fix a bug in the Universe Creator (Creator Studio) that prevents changing the category/type of an existing entity.

## Design Decisions
- Replace the static read-only `QTableWidgetItem` in column 1 ("type") of the entity table with a `QComboBox`.
- Retrieve the value from this `QComboBox` during `collect_data()` to ensure edits to the type are preserved.
- Ensure i18n support by updating the combo boxes when `retranslate_ui()` is called.
