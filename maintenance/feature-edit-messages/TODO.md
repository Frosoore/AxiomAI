# TODO — Dynamic Chat Editing Feature

- [x] Add `edit_message_prompt` to all 10 locale files under `core/locales/`
- [x] Add `update_event_payload` method in `EventSourcer` (`axiom/events.py`)
- [x] Add `update_turn_narrative` method in `VectorMemory` (`axiom/memory.py`)
- [x] Implement event editing task and vector memory update task in background workers
- [x] In `ChatDisplayWidget` (`ui/widgets/chat_display.py`):
  - Add `edit_message_requested = Signal(str, int)` signal
  - Render a small localized `[Edit]` link alongside/below user messages, hero intents, and narrative text
  - Parse link clicks matching `edit:<type>:<turn>` and emit `edit_message_requested`
- [x] In `TabletopView` (`ui/tabletop_view.py`):
  - Connect `edit_message_requested` to the edit handler
  - If editing an AI message (`narrative_text` or `hero_intent`):
    - Update `Event_Log` payload in sqlite
    - Update `VectorMemory` via vector memory task
    - Re-fetch session history and rebuild chat display
  - If editing a user message (`user_input`):
    - Revert/rollback to `turn_id - 1`
    - After rollback complete, append the new user input at `turn_id` and start response generation (simulating message send)
- [x] Run test suite and add/run tests specifically for chat editing
- [x] Fix user message editor by chaining `VectorMemory` rollback after DB rewind in `TabletopView`
- [x] Fix orphaned illustrations cleanup during DB rewind in `RewindTask` (calls `truncate_assets_in`)
- [x] Add integration test in `tests/test_edit_messages_ui.py` to assert VectorMemory rollback chaining in `TabletopView`
- [x] Fix player message turn_id alignment between history memory and SQLite (increments turn_id first in _on_send_message) to prevent destroying previous history during rollback.
- [x] Add unit test in `tests/test_edit_messages_ui.py` verifying turn_id increment alignment.


