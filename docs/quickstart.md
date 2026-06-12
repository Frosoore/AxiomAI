# Quickstart

This page takes you from `pip install` to your first narrated game turn.

## Requirements

- **Python 3.11 or newer.**
- An LLM you can call: either a **Google Gemini API key** (free tier works) or
  any **OpenAI-compatible endpoint** — a local [Ollama](https://ollama.com)
  server, LM Studio, llama.cpp, vLLM…

## Install

```console
$ pip install axiomai-engine
```

This installs the `axiom` Python package and the `axiom` command-line tool.
Check it works:

```console
$ axiom --help
$ python -c "import axiom; axiom.help()"
```

`axiom.help()` prints a short usage guide right in the REPL.

## Configure an LLM backend

The engine reads its configuration from `~/.config/AxiomAI/settings.json`
(created on first use). The two essential keys:

```json
{
  "llm_backend": "gemini",
  "gemini_api_key": "YOUR_API_KEY",
  "gemini_model": "gemini-2.5-flash-lite"
}
```

or, for a local OpenAI-compatible server such as Ollama:

```json
{
  "llm_backend": "universal",
  "universal_base_url": "http://localhost:11434/v1",
  "universal_model": "llama3.2"
}
```

See the [LLM backends guide](guides/backends.md) for every option, including
rate limiting and fallback models. From Python you can also bypass the file
entirely and construct a backend yourself.

## Get a universe

A universe is a single file (`.db` or `.axiom`) or a source folder. Three ways
to get one:

1. **Import a shared `.axiom` archive** someone published:

   ```console
   $ axiom import MyWorld.axiom
   ```

2. **Write one as text** — a folder with a `universe.toml` and friends, then
   compile it (see [Universe-as-Code](guides/universe-format.md)):

   ```console
   $ axiom compile path/to/my-world/
   ```

3. **Generate one with an LLM** from a one-line idea (see
   [Populating a universe](guides/populate.md)):

   ```console
   $ axiom populate MyWorld.db -t meta -t entities -t lore --text "A noir city of clockwork gods"
   ```

## Play in the terminal

```console
$ axiom play MyWorld.db --name Alice
```

The `play` command looks for the universe file where you point it, and also in
`~/AxiomAI/universes/`. Use `--save SAVE_ID` to resume, `--new` to force a new
game, and `--difficulty Normal|Hardcore|Companion` to pick a mode.

## Play from Python

```python
import axiom
from axiom.config import load_config, build_llm_from_config
from axiom.db_helpers import create_new_save

# Build the LLM backend from ~/.config/AxiomAI/settings.json
llm = build_llm_from_config(load_config())

# Create a save and open a session
save_id = create_new_save("MyWorld.db", "Alice", "Normal")
session = axiom.Session("MyWorld.db", save_id, llm=llm)

# Play a turn (synchronous; stream tokens with on_token)
result = session.take_turn("I open the tavern door.", on_token=print)
print(result.narrative_text)

# Inspect and time-travel
print(session.current_stats())       # entity stats, materialised
session.rewind(session.turn_id - 1)  # undo the last turn
```

Key objects:

- {py:class}`axiom.session.Session` — the high-level game loop: submit
  intents, resolve turns, rewind, regenerate variants.
- {py:class}`axiom.universe.Universe` — read-only metadata and save listing
  for a universe file.

## Where files live

By default the engine keeps its data under `~/AxiomAI/` (universes, saves,
vector memory, generated assets) and its settings under `~/.config/AxiomAI/`.
Both roots can be redirected with the `AXIOM_DATA_DIR` and `AXIOM_CONFIG_DIR`
environment variables — handy for tests and sandboxes.

## Next steps

- [The Universe-as-Code format](guides/universe-format.md) — define worlds as
  versionable text.
- [The `axiom` command line](guides/cli.md) — every subcommand.
- [Saves, rewind and sharing](guides/saves.md) — event sourcing in practice.
- [API reference](api/index.md).
