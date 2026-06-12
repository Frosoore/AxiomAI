# Scene illustration

Optionally, the engine can generate **one illustration per turn**: it asks the
LLM to distil the narrative, the location and the characters present into a
visual prompt, then sends that prompt to an image backend. Images are saved
under the data root (`assets/<save_id>/turn_<n>.png`) and follow the save
through rewind, fork, export and import.

Image generation never blocks the game: any failure logs a warning and the
turn completes without an image.

## Configuration

In `~/.config/AxiomAI/settings.json`:

```json
{
  "image_generation_enabled": true,
  "image_backend": "gemini",

  "image_api_url": "http://127.0.0.1:7860",
  "image_width": 512,
  "image_height": 512,
  "image_steps": 20,
  "image_cfg_scale": 7.0,
  "image_timeout": 180,
  "image_comfyui_workflow": "",
  "image_gemini_model": "gemini-2.5-flash-image"
}
```

## Backends

### `gemini` — Google Gemini (cloud)

Uses the same API key as the text backend; no local install needed. The model
is set by `image_gemini_model`, and the aspect ratio is derived from
`image_width`/`image_height`. Note that image models are typically **not** in
the Gemini free tier.

### `stable_diffusion` — Stable Diffusion WebUI (local)

Any AUTOMATIC1111-compatible server (A1111, reForge, Forge…) reachable at
`image_api_url`. The server **must be launched with the `--api` flag** —
without it the engine gets a 404 and tells you so. `image_width`,
`image_height`, `image_steps` and `image_cfg_scale` map straight to the
generation request; `image_timeout` caps the wait per image (default 180 s —
raise it on slow machines).

### `comfyui` — ComfyUI (local)

Point `image_api_url` at the ComfyUI server. By default the engine submits a
minimal text-to-image workflow using the first installed checkpoint; for full
control, set `image_comfyui_workflow` to a workflow JSON file path (or the
JSON itself) exported from ComfyUI. Polling is bounded by `image_timeout`.

## From Python

{py:class}`axiom.image_generator.ImageGenerator` exposes the two steps —
`generate_prompt(...)` (LLM → visual prompt) and
`generate_image(prompt, assets_dir, filename)` (backend → PNG file, or `None`
on failure). {py:class}`axiom.session.Session` calls it automatically at the
end of each turn when `image_generation_enabled` is true.
