# The `axiom` command line

Installing `axiomai-engine` provides the `axiom` command (also reachable as
`python -m axiom.cli`). Run `axiom --help` or `axiom <command> --help` for the
authoritative usage; this page is the annotated tour.

Wherever a command takes a *universe* argument, it accepts a `.db` file, a
source folder (compiled on the fly when needed) or a `.axiom` archive.

## Playing

### `axiom play`

Play a universe interactively in the terminal:

```console
$ axiom play MyWorld.db --name Alice --difficulty Normal
```

| Option | Effect |
|---|---|
| `--save SAVE_ID` | Resume an existing save. |
| `--new` | Force a new game. |
| `--name NAME` | Player name for a new game (default `Hero`). |
| `--difficulty {Normal,Hardcore,Companion}` | Game mode for a new game. |
| `--temperature F` / `--top-p F` | LLM sampling settings. |
| `--verbosity {short,balanced,talkative}` | Narration length. |

The universe path is also searched in `~/AxiomAI/universes/`.

## Authoring (Universe-as-Code)

### `axiom compile`

Compile a source tree into a `.db` cache
(see [the format](universe-format.md)):

```console
$ axiom compile my-world/ [-o out.db] [--force]
```

### `axiom decompile`

The inverse — turn an existing `.db` universe into an editable text tree:

```console
$ axiom decompile World.db my-world/
```

### `axiom dev`

Authoring loop: watch a source tree and hot-recompile on every change
(`--interval` sets the polling period, default 1 s; `--db` overrides the
target cache path):

```console
$ axiom dev my-world/
```

### `axiom pack` / `axiom import`

Share universes as single-file `.axiom` archives:

```console
$ axiom pack my-world/ MyWorld.axiom    # source folder or .db -> archive
$ axiom import MyWorld.axiom            # archive (v1 or v2) -> playable tree
```

### `axiom populate`

Generate universe content with the configured LLM. Repeat `-t` for several
targets among `meta`, `stats`, `entities`, `rules`, `events`, `lore`, `map`:

```console
$ axiom populate MyWorld.db -t entities -t lore --text "A noir city of clockwork gods"
```

Without `--text`, the generation is inferred from the existing lore. See
[Populating a universe](populate.md).

## Saves

All `save-*` commands operate on a universe and a save identifier. See
[Saves, rewind and sharing](saves.md) for the concepts.

### `axiom save-show`

Inspect a save's state, optionally at a past point (`--turn N` or
`--minute M`):

```console
$ axiom save-show MyWorld.db <save_id> --turn 12
```

### `axiom save-export` / `axiom save-import`

Round-trip a save through an editable `save_state.toml`:

```console
$ axiom save-export MyWorld.db <save_id> state.toml
$ axiom save-import MyWorld.db state.toml [--name Alice]
```

### `axiom save-fork`

Fork a save into a new one, truncating the journal at a point (`--turn` /
`--minute`) — an alternate timeline:

```console
$ axiom save-fork MyWorld.db <save_id> --turn 10 --name "Alice (what if)"
```

### `axiom save-edit`

Fix an existing save in place by applying a correction TOML (stat patches
under `[state.<entity_id>]`, plus `[[inventory]]` and `[[modifiers]]`
entries); `--turn` targets a past point:

```console
$ axiom save-edit MyWorld.db <save_id> patch.toml
```

### `axiom save-pack` / `axiom save-unpack`

Share a single save as a `.axiomsave` archive:

```console
$ axiom save-pack MyWorld.db <save_id> alice.axiomsave
$ axiom save-unpack MyWorld.db alice.axiomsave
```
