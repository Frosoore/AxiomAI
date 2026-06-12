# Axiom Engine

**Axiom Engine** (`axiomai-engine` on PyPI) is a headless, LLM-driven narrative
game engine. It powers the Axiom AI desktop application, but it has zero GUI
dependencies: you can drive it from a Python script, a terminal, a server — or
build your own front-end on top of it.

```python
import axiom
from axiom.config import load_config, build_llm_from_config
from axiom.db_helpers import create_new_save

llm = build_llm_from_config(load_config())
save_id = create_new_save("MyWorld.db", "Alice", "Normal")

session = axiom.Session("MyWorld.db", save_id, llm=llm)
result = session.take_turn("I open the tavern door.")
print(result.narrative_text)
```

## What it does

- **Persistent universes** — each world is a self-contained SQLite database
  holding entities, stats, rules, lore, locations and scheduled events.
- **Universe-as-Code** — a universe can be defined as a versionable tree of
  plain-text files (TOML + Markdown); the `.db` is just a compiled cache.
  Compile, decompile, hot-reload, share on Git.
- **LLM-arbitrated narration** — a configurable LLM backend (Google Gemini, or
  any OpenAI-compatible API such as Ollama) narrates each turn, applies your
  universe's rules, and tracks entity stats.
- **Event sourcing & time travel** — every turn is an event in a journal.
  Rewind to any past turn, fork a save into an alternate timeline, or edit a
  save state by hand.
- **Causal time** — an in-game clock advances with the story; an off-screen
  "Chronicler" simulates the rest of the world while the player is away.
- **Vector memory (RAG)** — long-term memory and lore retrieval backed by a
  local vector store.
- **Content generation** — populate a universe (entities, lore, map, rules…)
  with an LLM, from the command line or from Python.
- **Optional scene illustration** — generate an image per turn via Stable
  Diffusion WebUI, ComfyUI or the Gemini image API.

## Where to start

- **New here?** Follow the [Quickstart](quickstart.md): install the engine,
  configure an LLM backend and play your first turn — in Python or straight
  from the terminal.
- **Building a universe?** Read the
  [Universe-as-Code format](guides/universe-format.md) and the
  [CLI guide](guides/cli.md).
- **Integrating the engine?** Head to the [API reference](api/index.md),
  generated from the source docstrings.

```{toctree}
:maxdepth: 2
:caption: Getting started

quickstart
```

```{toctree}
:maxdepth: 2
:caption: Guides

guides/universe-format
guides/cli
guides/saves
guides/populate
guides/backends
guides/images
```

```{toctree}
:maxdepth: 2
:caption: Reference

api/index
```

## Project links

- [Source repository](https://github.com/Frosoore/AxiomAI) (the engine lives
  in the `axiom/` package of the Axiom AI mono-repo)
- [PyPI: axiomai-engine](https://pypi.org/project/axiomai-engine/)
- [Issue tracker](https://github.com/Frosoore/AxiomAI/issues)

Axiom Engine is free software, licensed under the
[GNU AGPL v3 or later](https://www.gnu.org/licenses/agpl-3.0.html); see the
`NOTICE` file for the attribution requirement ("Based on Axiom AI by 17h59 and
Frosoore").
