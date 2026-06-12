# Populating a universe with an LLM

Writing a whole world by hand is work. The engine can draft one for you: the
**populate** module sends your idea (or your existing lore) to the configured
LLM and writes the results into the universe — entities, lore entries, rules,
a map, scheduled events, stat definitions, metadata.

## From the command line

```console
$ axiom populate MyWorld.db -t meta -t entities -t lore \
      --text "A noir city ruled by clockwork gods"
```

- `-t/--target` is repeatable, one per content kind:
  `meta`, `stats`, `entities`, `rules`, `events`, `lore`, `map`.
- `--text` gives a free-form instruction. Without it, the generation is
  inferred from the lore already present in the universe.

The universe argument accepts a `.db`, a source folder or a `.axiom` archive.
If the universe is folder-backed (Universe-as-Code), the generated content is
**decompiled back into the source tree** afterwards, so the text files stay
the source of truth.

## What each target generates

| Target | Writes |
|---|---|
| `meta` | Universe name, system prompt, global lore, first message. |
| `stats` | Stat definitions appropriate for the setting. |
| `entities` | Characters and creatures, with initial stats. |
| `rules` | Mechanical rules (conditions/actions) matching the world. |
| `events` | Scheduled in-game events on the timeline. |
| `lore` | Lore-book entries (history, factions, places…). |
| `map` | Locations and their connections. |

Generation is **idempotent in spirit**: entity identifiers are derived from
names, so regenerating tends to update rather than duplicate.

## From Python

Each target is a function in {py:mod}`axiom.populate`, all sharing the same
shape — a database path, an optional instruction, an injectable LLM backend
and an optional status callback:

```python
from axiom.populate import populate_entities
from axiom.config import load_config, build_llm_from_config

llm = build_llm_from_config(load_config())
populate_entities("MyWorld.db", text="A noir city of clockwork gods", llm=llm)
```

`POPULATE_TARGETS` maps the CLI target names to these functions.

## Practical notes

- **Model choice matters.** Generation asks for structured output; small
  local models sometimes return malformed JSON. If a run fails, retry or use
  a stronger model.
- **Quota resilience.** On Gemini, rate limits (HTTP 429) are retried with
  the configured backoff and the optional fallback model — see
  [LLM backends](backends.md).
- **Review the output.** Generated content is a draft. With a folder-backed
  universe, review the diff with `git diff` like any other code.
