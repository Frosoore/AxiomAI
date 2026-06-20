# CHANGELOG — Negative Prompt Feature

## Initial Session
- Created TODO.md, CHANGELOG.md, and DOC.md templates for the feature.

## Implementation Session
- Added `negative_prompt` configuration parameter in `axiom/config.py` (AppConfig).
- Updated `build_narrative_prompt` in `axiom/prompts.py` to append the negative prompt instructions structure dynamically.
- Provided translations for the new field labels, placeholders, and tooltips in all 10 locale files (`en.toml`, `fr.toml`, `es.toml`, `de.toml`, `it.toml`, `pt.toml`, `ru.toml`, `zh.toml`, `ja.toml`, `ko.toml`).
- Added Negative Prompt multiline edit field directly under the Basic Prompt text edit in `ui/settings_dialog.py`.
- Integrated Negative Prompt field in `ui/help_system.py` settings elements and general settings page definition.
- Wrote unit/integration tests in `tests/test_config.py`, `tests/test_prompt_builder.py`, and `tests/test_settings_dialog.py`.
