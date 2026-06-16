# CHANGELOG — Fix Entity Category/Type in Creator Studio

## [Unreleased]
- Created maintenance folder and planning files.
- Replaced the static, read-only entity type cell in the Creator Studio spreadsheet with a dynamic `QComboBox` populated with valid entity types (player, npc, faction, world).
- Connected the combobox's `currentIndexChanged` signal to update the entity data in memory and emit the `changed` signal immediately.
- Updated `collect_data()` to correctly extract the entity type from the combobox in the table.
- Added translation support in `retranslate_ui()` for both the new entity input type combobox and all comboboxes in the table rows.
- Added the `test_change_entity_type` unit test in `tests/test_phase6.py` to assert the correct behavior of type selection, memory synchronization, and signal emission.
