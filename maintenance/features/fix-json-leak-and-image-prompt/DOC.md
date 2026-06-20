# DOC — Fix JSON Leak and Improve Image Generation

## Objective
1. Prevent any JSON block from leaking into the user chat, even when it is malformed or unclosed by the LLM.
2. Improve visual quality of generated images by providing a structured system prompt to the image prompt generator LLM, adding rich negative prompts to local backends, and rebuilding the chat view upon turn completion as a final cleanup step.

## Design Decisions
- **JSON Leak Prevention**:
  - Extend the streaming filter in `ChatDisplay` to recognize unclosed JSON fence openers (`\n{` and `{` at start) and drop all tokens following them when forced.
  - Implement unclosed fence detection and regex-based unclosed JSON start detection in `parse_tool_call()`.
  - Add a stateful JSON repair utility `_repair_json_string()` that balances quotes, brackets, and braces to retrieve maximum possible data from truncated LLM responses.
- **Image Generation Improvement**:
  - Re-engineer the visual prompt generation system prompt to enforce subject, detail, action, environment, lighting, mood, style, and composition structure.
  - Enrich negative prompts in SD WebUI and default ComfyUI template.
  - Rebuild chat display in `_on_turn_complete()` as a fallback guarantee to synchronize perfectly with the clean text in history.
