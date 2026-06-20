# DOC — Basic Prompt Feature

This feature introduces a "Basic Prompt" option in the settings. This allows players to provide custom user-level instructions to the LLM (e.g. "Parle seulement en anglais" or "Utilise des phrases simples", but also larger custom directives or jailbreaks).

## Architecture & Implementation details

1. **Configuration**: A new `basic_prompt` parameter is added to `AppConfig` in `axiom/config.py` (persisted in JSON `settings.json` under `~/.config/AxiomAI/`).
2. **User Interface**: A multiline `QTextEdit` field is added in the General section of `ui/settings_dialog.py` to allow editing this prompt easily. The text box is limited to a height of 80px to keep the UI clean, and supports plain text.
3. **i18n & Help System**: The new setting is registered under the `"settings"` page in `ui/help_system.py`, and appropriate documentation tooltips/titles are added to all 10 language locales.
4. **Narrative Prompt Generation**: `build_narrative_prompt` in `axiom/prompts.py` retrieves the `basic_prompt` from settings and appends it to the system instructions.
