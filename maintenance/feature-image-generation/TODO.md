# TODO - Image Generation Feature

- [x] Declare module modifications in `maintenance/collab/gemini/EN_COURS.md`.
- [x] Add image generation settings (backend type, API URL, prompt template, dimensions) to `settings.json` and `axiom/config.py`.
- [x] Create `axiom/image_generator.py` containing:
  - `ImageGenerator` class.
  - LLM-based prompt generation from narrative context.
  - HTTP requests to Stable Diffusion WebUI API (`/sdapi/v1/txt2img`).
  - HTTP requests to ComfyUI API (`/prompt`).
  - Robust error handling and fallback/mocking.
- [x] Integrate image generation into `Session` (e.g. after a turn resolves, optionally generate an image of the scene).
- [x] Add unit tests verifying prompt generation and API client requests with mock servers.
- [x] Run test suite to verify everything is working.
