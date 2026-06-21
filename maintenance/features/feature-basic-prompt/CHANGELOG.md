# CHANGELOG — Basic Prompt Feature

## Initial Session
- Created TODO.md, CHANGELOG.md, and DOC.md templates for the feature.
- Added `basic_prompt: str` attribute to `AppConfig` in `axiom/config.py`.
- Added a `QTextEdit` multiline widget with an 80px max height to the General settings section in `ui/settings_dialog.py`.
- Mapped settings loading (`load_from_config`) and saving (`collect_config`) to the `basic_prompt` attribute.
- Created and translated label, placeholder, and documentation keys for the `basic_prompt` in all 10 locales (`en`, `fr`, `de`, `es`, `it`, `pt`, `ru`, `zh`, `ja`, `ko`).
- Registered `basic_prompt` under the settings page in the help system registry (`ui/help_system.py`).
- Updated `build_narrative_prompt` in `axiom/prompts.py` to optionally accept `basic_prompt` and append it to the `universe_system_prompt` for narrative game turns.
- Created unit and UI tests in `tests/test_config.py`, `tests/test_prompt_builder.py`, and `tests/test_settings_dialog.py` verifying full saving/loading, prompt injection, and UI collection.

