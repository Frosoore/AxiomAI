# Saves, rewind and sharing

Axiom is **event-sourced**: every turn appends events (player input, narrative
text, stat changes, time…) to a journal, the `Event_Log`. The visible game
state is *derived* from that journal. This one design decision buys most of
the engine's tricks:

- **Rewind** — drop the events after turn *N* and rebuild the state: you are
  back at turn *N*.
- **Fork** — copy a save with its journal truncated at a point: an alternate
  timeline.
- **Inspect anywhere** — materialise the state at any past turn or in-game
  minute without touching the save.
- **Edit safely** — corrections are applied on top of the journal, never by
  mutating derived state.

## Where saves live

The universe definition and the play-throughs are separate things:

```text
~/AxiomAI/
├── universes/<name>/…                    # definition (source tree + cache)
└── saves/<universe key>/save_<uuid>.db   # one file per save (runtime state)
```

Each save database is **self-contained**: it carries a copy of the universe
definition taken at creation time. Patching the universe never breaks an
existing save — the definition copy is resynchronised when the save is
opened, while the runtime state survives. A save is therefore a single
portable file.

(Saves created by very old versions live *inside* the universe `.db`; they
remain listed and playable as-is.)

## Rewind and checkpoints

From Python, rewind is one call on the session:

```python
session.rewind(target_turn_id)     # back to that turn
session.list_checkpoints()         # turns with a snapshot
```

In **Hardcore** mode, death deletes the save — that is the point of Hardcore.

## Inspecting and editing a save

The `axiom save-*` commands (see [the CLI guide](cli.md)) expose the editing
toolbox. Points in time are selected by turn (`--turn N`) or by in-game
minutes (`--minute M`).

```console
$ axiom save-show MyWorld.db <save_id> --turn 12     # materialised state
$ axiom save-export MyWorld.db <save_id> state.toml  # state -> editable TOML
$ axiom save-import MyWorld.db state.toml            # TOML -> new save
$ axiom save-fork MyWorld.db <save_id> --turn 10     # alternate timeline
$ axiom save-edit MyWorld.db <save_id> patch.toml    # in-place correction
```

The editable `save_state.toml` format:

```toml
[save]
player_name = "Alice"
difficulty = "Normal"
player_persona = "A reformed clockwork thief."

[point]                  # informative at export time
turn_id = 12
in_game_minutes = 540

[state.innkeeper]        # effective entity stats
Health = "100"
Mood = "friendly"

[[inventory]]
entity_id = "player_alice"
item_id = "rusty_sword"
quantity = 1

[[modifiers]]
entity_id = "player_alice"
stat_key = "Strength"
delta = 2
minutes_remaining = 120
```

Two rules keep editing safe:

1. The journal stays the source of truth. Imports create a *new* save whose
   journal starts with "genesis" events at turn 0; exports materialise the
   state by replaying the journal.
2. An imported save starts with an empty vector memory — it fills up again as
   you play.

## Sharing a save

Pack a save (journal, state, illustrations metadata) into a single
`.axiomsave` archive and import it next to any copy of the same universe:

```console
$ axiom save-pack MyWorld.db <save_id> alice.axiomsave
$ axiom save-unpack MyWorld.db alice.axiomsave
```

## From Python

The same operations are exposed by {py:mod}`axiom.savestore` (separate save
files, archives) and {py:mod}`axiom.saves` (materialise / fork / import /
edit), with {py:class}`axiom.checkpoint.CheckpointManager` underneath.
