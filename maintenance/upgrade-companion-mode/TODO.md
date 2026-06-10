# TODO - Upgrade Companion Mode

- [x] Declare module modifications in `maintenance/collab/gemini/EN_COURS.md`.
- [x] Retrieve Player name & persona from `Saves` in `ArbitratorEngine.process_turn` and pass them to `build_narrative_prompt`.
- [x] Reconstruct a multi-entity relevant stats block in `Session._get_hero_decision` and pass it to `build_hero_decision_prompt` so the companion sees both player and enemy stats.
- [x] Load `hero_intent` events in `Session._load_history` and group them under simultaneous user intents in history to preserve turn coherence and let the companion remember its past intents.
- [x] Add `player_name` and `player_persona` context to `build_hero_decision_prompt` in `axiom/prompts.py`.
- [x] Add Group Awareness rules dynamically to NARRATOR RULES and critical reminders when 3 or more local characters are present to prevent binary bias (e.g. referring to 3 characters as "you two").
- [x] Fix player ID mismatch bugs in spatial context and `_identify_relevant_entities` by dynamically using the resolved player ID (`self._player_entity_id`) instead of hardcoded `"player"`.
- [x] Add unit tests verifying the improvements to Companion Mode in `tests/test_session.py` and `tests/test_arbitrator.py`.
- [x] Run the test suite to ensure no regressions.
