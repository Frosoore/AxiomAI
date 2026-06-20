# CHANGELOG — Dynamic Chat Editing Feature

## Initial Session
- Created TODO.md, CHANGELOG.md, and DOC.md templates for the feature.
- Added localized `edit_message_prompt` to all 10 frontend locale files (`en`, `fr`, `es`, `de`, `it`, `pt`, `ru`, `zh`, `ja`, `ko`).
- Implemented `update_event_payload` in `EventSourcer` to modify event payloads in SQLite.
- Implemented `update_turn_narrative` in `VectorMemory` to clear and replace turn RAG embeddings.
- Created `UpdateEventPayloadTask` in `workers/db_tasks.py` and exposed it in `DbWorker` with signal `event_payload_updated`.
- Created `VectorUpdateWorker` in `workers/vector_worker.py` to process vector updates asynchronously.
- Updated `ChatDisplayWidget` with signal `edit_message_requested` and modified appenders to render standard HTML `[Edit]` links for user, hero, and narrative messages.
- Wired signal in `TabletopView` to `_on_edit_message_requested`, prompting the user for edits.
  - If editing an AI message, updates the database & vector memory and refreshes history in-place.
  - If editing a user message, rolls back state/history to `turn_id - 1` and resubmits the new input, triggering a fresh generation.
- Added comprehensive unit tests in `tests/test_ticket_fixes.py` and UI tests in `tests/test_edit_messages_ui.py`.
- Verified that all 775 tests pass correctly.

## Follow-up Session (Current)
- Fixed player message editor bug where the semantic `VectorMemory` database was not rolled back during message editing (leading to context contamination from alternative futures).
- Chained `VectorMemory` rollback using the background `VectorWorker` thread inside `TabletopView._on_rewind_done`, ensuring SQLite and Vector database consistency.
- Fixed an issue where illustrations from rolled back turns were not cleaned up when doing a rewind from the GUI; `RewindTask.execute` now correctly calls `truncate_assets_in`.
- Added integration test `test_tabletop_view_chains_vector_rollback` in `tests/test_edit_messages_ui.py` to assert correct execution and cleanup flow.
- Fixed player message turn_id alignment bug where interactive messages were appended with the previous turn's ID in memory (`self._history`) but the current turn's ID in SQLite. Under certain editing conditions, this mismatch triggered rollbacks to a negative target (`target_turn_id = -1`), destroying the entire history including the first message.
- Fixed `_on_send_message` in `TabletopView` to increment `self._turn_id` *first* so interactive messages are appended and saved with the correct turn ID matching SQLite.
- Added unit test `test_tabletop_view_on_send_message_increments_turn_id_first` in `tests/test_edit_messages_ui.py` to assert correct turn ID alignment.
- Connected `db_worker.error_occurred` to `_on_worker_error` to ensure background SQLite errors are correctly reported to the user.


