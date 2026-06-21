# TODO — Fix JSON Leak and Improve Image Generation

- [x] Update `ui/widgets/chat_display.py` to handle raw/unclosed JSON blocks in streaming.
- [x] Update `axiom/backends/base.py` to strip and repair malformed or unclosed JSON blocks.
- [x] Update `axiom/image_generator.py` with an enhanced system prompt and robust negative prompts.
- [x] Simplify visual prompt generation system prompt to use a natural scene description + style keywords.
- [x] Implement togglable "Trim Sentences" feature to discard the last incomplete sentence when token limit is hit.
- [x] Add localization keys for "Trim Sentences" in all 10 translation TOML files.
- [x] Update `ui/tabletop_view.py` to rebuild chat display on turn completion.
- [x] Add unit tests in `tests/test_phase6.py` and `tests/test_llm_base.py` to verify malformed JSON parsing, streaming, and Trim Sentences behavior.
