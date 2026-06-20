# TODO — Basic Prompt Feature

- [x] Add `basic_prompt` string parameter to `AppConfig` in `axiom/config.py`
- [x] Add translation keys for the new setting in `core/locales/` (all 10 languages):
  - `doc_settings_basic_prompt_t` (title)
  - `doc_settings_basic_prompt` (description)
  - `basic_prompt_label` (label)
  - `basic_prompt_placeholder` (placeholder)
- [x] Add `basic_prompt` to the `"settings"` page registry in `ui/help_system.py`
- [x] Implement the `basic_prompt` text area in `ui/settings_dialog.py` (under the General section)
  - Instantiate `QTextEdit` for multiline input
  - Limit its max height (e.g. 80px) and set placeholder text
  - Load the value in `load_from_config` and retrieve it in `collect_config`
  - Translate label/placeholder in `retranslate_ui`
- [x] Inject `basic_prompt` into the system prompt construction in the engine:
  - Update `build_narrative_prompt` in `axiom/prompts.py` to retrieve `basic_prompt` from configuration and append it to the `universe_system_prompt`
- [x] Create unit tests to verify:
  - Config saving/loading with the new `basic_prompt` attribute
  - Correct injection of `basic_prompt` in the built narrative prompt
- [x] Run test suite (`bash test.sh` and `doc_check.py`) and verify all tests pass


