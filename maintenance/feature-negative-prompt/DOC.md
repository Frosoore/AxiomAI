# DOC — Negative Prompt Feature

This feature introduces a "Negative Prompt" option in the settings. This allows players to provide custom user-level negative instructions to the LLM (e.g. "Do not break character", "Do not mention future technology", etc.).

## Architecture & Implementation details

1. **Configuration**: A new `negative_prompt` parameter is added to `AppConfig` in `axiom/config.py`.
2. **User Interface**: A multiline `QTextEdit` field is added in the General section of `ui/settings_dialog.py` (just below Basic Prompt) to allow editing this negative prompt easily.
3. **i18n & Help System**: The new setting is registered under the `"settings"` page in `ui/help_system.py`, and appropriate documentation tooltips/titles are added to all 10 language locales.
4. **Narrative Prompt Generation**: `build_narrative_prompt` in `axiom/prompts.py` retrieves the `negative_prompt` from settings and appends it to the system instructions format as negative guidelines.
