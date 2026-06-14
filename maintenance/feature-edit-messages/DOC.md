# DOC — Dynamic Chat Editing Feature

This feature allows the player to dynamically correct or change messages directly in the tabletop view chat history.

## Technical Details

### 1. AI Message Editing (narrative_text / hero_intent)
- When edited, only the underlying data stores (sqlite Event_Log and ChromaDB VectorMemory) are updated.
- A background task is used to perform the sqlite payload update, and another task modifies vector memory.
- The chat is rebuilt from history.

### 2. User Message Editing (user_input)
- When a user's own message is edited, a rollback to `turn_id - 1` is performed.
- All subsequent events, snapshots, and timeline entries are deleted.
- Once the database is rolled back, the new input is appended, and response generation is triggered (exactly as if the user sent it for the first time).
