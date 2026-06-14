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
