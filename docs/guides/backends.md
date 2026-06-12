# LLM backends and configuration

The engine talks to LLMs through a small backend interface
({py:class}`axiom.backends.base.LLMBackend`). Two implementations ship with
it:

- **`universal`** — any **OpenAI-compatible** HTTP API: a local
  [Ollama](https://ollama.com) server, LM Studio, llama.cpp, vLLM, or a
  hosted service.
- **`gemini`** — the **Google Gemini** API, with quota-aware retries, an
  optional fallback model and an optional rate limiter.

## The settings file

Configuration lives in `~/.config/AxiomAI/settings.json` and is loaded by
{py:func}`axiom.config.load_config` into an
{py:class}`axiom.config.AppConfig`. Defaults are sensible; unknown keys are
ignored.

```json
{
  "llm_backend": "gemini",

  "universal_base_url": "http://localhost:11434/v1",
  "universal_api_key": "",
  "universal_model": "llama3.2",

  "gemini_api_key": "YOUR_KEY",
  "gemini_model": "gemini-2.5-flash-lite",
  "gemini_fallback_model": "",
  "llm_requests_per_minute": 0,

  "extraction_model": "llama3.1:8b",
  "time_model": "llama3.2:1b",
  "timekeeper_enabled": true,
  "chronicler_minutes_interval": 720,
  "rag_chunk_count": 5
}
```

### The narration model and the helper models

The main model (`gemini_model` or `universal_model`) narrates the story. Two
auxiliary roles can use cheaper models:

- **`extraction_model`** — structured-output jobs (content generation, the
  Companion hero's decisions).
- **`time_model`** — the *Timekeeper*, a small extra call that deduces how
  many in-game minutes each turn took. Disable it with
  `"timekeeper_enabled": false` to save a call per turn (time is then
  estimated from the scene pace alone).

Both auxiliary names are local-model identifiers; on the Gemini backend they
are ignored and `gemini_model` is used instead.

### Gemini specifics

- `llm_requests_per_minute` — soft rate limit (0 = unlimited). The Gemini
  free tier allows ~10 requests/min per model; set 9 to stay under it.
- `gemini_fallback_model` — tried when the primary model is still
  quota-exhausted (HTTP 429) after retries. Google quotas are per-model, so a
  different model usually still has budget.
- A model with **zero free-tier quota** answers 429 with a misleading "retry
  in N s" — if that happens consistently, the model needs billing, not
  patience; pick another model.

### The Chronicler

`chronicler_minutes_interval` (in-game minutes, default 720 = 12 h) paces the
**Chronicler**, the background pass that simulates the off-screen world each
time the in-game clock crosses the interval — one long time-skip triggers
exactly one simulation.

## Building backends from Python

```python
from axiom.config import load_config, build_llm_from_config

cfg = load_config()
llm = build_llm_from_config(cfg)                          # the main model
aux = build_llm_from_config(cfg, model_override="gemma3") # same backend, other model
```

Or construct one directly — useful to plug the engine into your own stack:

```python
from axiom.backends.universal import UniversalClient

llm = UniversalClient(
    base_url="http://localhost:11434/v1",
    api_key="",
    model_name="llama3.2",
)
session = axiom.Session("MyWorld.db", save_id, llm=llm)
```

{py:class}`axiom.session.Session` also accepts separate `hero_llm` and
`time_llm` backends if you want different models per role.

## Environment overrides

- `AXIOM_CONFIG_DIR` — where `settings.json` lives (default
  `~/.config/AxiomAI/`).
- `AXIOM_DATA_DIR` — the data root for universes, saves, vector memory and
  generated assets (default `~/AxiomAI/`).
