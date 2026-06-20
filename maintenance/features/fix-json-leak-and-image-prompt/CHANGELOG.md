# CHANGELOG — Fix JSON Leak and Improve Image Generation

## [Unreleased]
- Created maintenance folder and planning files.
- Extended the `ChatDisplayWidget._flush_token_buffer` streaming filter to detect raw JSON starts (`\n{` and `{` at start) and correctly buffer them, discarding the unclosed contents upon a forced flush.
- Enhanced `LLMBackend.parse_tool_call()` to strip unclosed fences, unclosed raw JSON object openers at the end, and to attempt repairing malformed JSON strings before decoding.
- Added a robust `LLMBackend._repair_json_string()` stateful repair utility to balance quotes, braces, and brackets for truncated LLM responses.
- Rewrote the visual prompt generation system prompt in `axiom/image_generator.py` to instruct the LLM to output a single, direct, natural language description of the main scene, character, and setting (always specifying fully clothed characters in medieval/fantasy attire, and strictly enforcing a medieval fantasy forest/stone path aesthetic while avoiding modern indoor spaces), followed by comma-separated style/lighting keywords.
- Appended standard high-quality negative prompt keywords (including `nsfw, nude, naked, uncensored, bathroom, shower, toilet, modern, indoor, tiles`) to Stable Diffusion txt2img payload and ComfyUI default workflow template to prevent modern indoor/NSFW rendering defects.
- Added a toggleable "Trim Sentences" feature (`AppConfig.trim_sentences`, GUI checkbox in settings) that automatically discards the last sentence of an AI response if it is incomplete due to hitting the token limit (`finish_reason == "length"`).
- Implemented sentence-level truncation in `ArbitratorEngine._call_llm` supporting English, French, Spanish, German, Italian, Portuguese, Russian, Korean, Japanese, and Chinese sentence terminators, scope-limited to narrator output to prevent trimming on auxiliary calls like Companion decisions. Also automatically trims any response that ends with an incomplete sentence regardless of the backend finish reason.
- Added localization keys for "Trim Sentences" in all 10 translation TOML files.
- Updated `TabletopView._on_turn_complete()` to rebuild the chat display from history upon turn completion as a final cleanup step.
- Added unit tests in `tests/test_llm_base.py` and `tests/test_phase6.py` covering malformed/unclosed JSON parsing, repair, streaming, and Trim Sentences behavior.
