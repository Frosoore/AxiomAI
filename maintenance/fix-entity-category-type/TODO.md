# TODO — Fix Entity Category/Type in Creator Studio

- [x] Modify `EntityEditorWidget._add_entity_row` to use a `QComboBox` for the "type" column instead of a read-only `QTableWidgetItem`.
- [x] Connect the combobox's `currentIndexChanged` signal to `self.changed.emit` to mark the universe as modified.
- [x] Update `EntityEditorWidget.collect_data` to read the entity type from the combobox.
- [x] Update `EntityEditorWidget.retranslate_ui` to retranslate the combobox items for both the input combobox and all table rows.
- [x] Add unit tests in `tests/test_phase6.py` to cover changing the entity type.
