# The Universe-as-Code format

An Axiom universe can be defined entirely as a **tree of plain-text files**
(TOML and Markdown). The text is the source of truth; the SQLite `.db` the
engine actually runs on is a **compiled cache**, regenerated whenever the
source changes. This makes universes diff-able, reviewable and shareable on
Git, like code.

```console
$ axiom compile my-world/        # source tree -> .db cache
$ axiom decompile World.db out/  # existing .db -> source tree
$ axiom dev my-world/            # watch & hot-recompile while you edit
```

Only the **definition** of the universe lives in the source tree (entities,
rules, lore, map…). Player saves are runtime data, stored separately — see
[Saves, rewind and sharing](saves.md).

## Layout

```text
my-world/
├── universe.toml            # required: metadata, narration, calendar
├── stats/
│   └── definitions.toml     # stat definitions (optional)
├── entities/
│   ├── hero.toml            # one file per entity
│   └── innkeeper.toml
├── rules/
│   └── poison.toml          # one file per rule
├── locations/
│   └── map.toml             # locations + connections
├── lore/
│   ├── _global_lore.md      # referenced from universe.toml
│   └── history/origins.md   # every other .md becomes a lore-book entry
├── events/
│   └── eclipse.toml         # scheduled events
├── items/
│   └── rusty_sword.toml     # item definitions
├── setup/
│   └── questions.toml       # story-setup questionnaire
└── .axiom-cache/            # compiled cache (generated; don't commit)
    └── universe.db
```

Every folder except `universe.toml` is optional. Files named `_index.toml`
are ignored, and so is anything under `.axiom-cache/` and `.git/`.

## `universe.toml`

```toml
[meta]
name = "The Clockwork City"

[narrative]
system_prompt = "You are the narrator of a noir city of clockwork gods."
# Long texts can live in their own file instead of inline:
global_lore_file = "lore/_global_lore.md"     # or: global_lore = "…"
first_message_file = "lore/_first_message.md" # or: first_message = "…"
world_tension_level = "simmering unrest"

[calendar]               # optional custom calendar
minutes_per_hour = 60
hours_per_day = 24
days_per_month = [30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30, 30]
month_names = ["Frostfall", "Embertide"]  # … one name per month
start_day = 1
start_hour = 8
start_minute = 0

[companion]              # optional Companion mode defaults
enabled = true
hero_id = "hero"

[extra]                  # free-form keys, preserved verbatim
my_custom_key = "value"
```

`global_lore` / `first_message` may be given inline or via a `*_file` path;
referenced files are excluded from the lore book.

## Entities — `entities/*.toml`

One file per entity:

```toml
entity_id = "innkeeper"          # required, stable identifier
entity_type = "npc"              # default: "npc"
name = "Marla the Innkeeper"
description = "A weathered woman who hears everything."
is_active = true                 # default: true

[stats]                          # initial stat values (strings)
Health = "100"
Location = "tavern"
Mood = "wary"
```

## Stat definitions — `stats/definitions.toml`

```toml
[[definitions]]
stat_id = "Health"
name = "Health"
description = "Hit points."
value_type = "numeric"           # default: "numeric"
parameters = { min = 0, max = 100 }
```

## Rules — `rules/*.toml`

One file per rule. Conditions and actions are stored as JSON-compatible
structures and evaluated by the engine each turn:

```toml
rule_id = "poison_tick"
priority = 10                    # default: 0
target_entity = "*"              # default: "*" (any entity)

[conditions]
stat = "Poisoned"
equals = "true"

[[actions]]
type = "modify_stat"
stat = "Health"
delta = -5
```

## Locations — `locations/map.toml`

```toml
[[locations]]
location_id = "tavern"
name = "The Rusty Cog"
scale = "poi"                    # e.g. "poi", "district", "city", "region"
parent_id = "old_town"           # optional hierarchy
description = "Smoke, gears and cheap gin."
x = 12.5
y = 4.0

[[connections]]
source_id = "tavern"
target_id = "market"
distance_km = 1
```

## Lore book — `lore/**/*.md`

Every Markdown file under `lore/` (recursively) becomes a lore-book entry,
except files referenced from `universe.toml`. An optional **TOML frontmatter**
between `+++` delimiters carries the metadata:

```markdown
+++
entry_id = "origins"
category = "history"
name = "The Origins of the City"
keywords = "clockwork, gods, founding"
+++
Long ago, the first gear was set in motion…
```

Without frontmatter, the `entry_id` is derived from the relative path and the
name from the file name. The body is preserved byte-for-byte (compile →
decompile round-trips are lossless).

## Scheduled events — `events/*.toml`

Events fire when the in-game clock reaches `trigger_minute`:

```toml
event_id = "eclipse"
trigger_minute = 4320            # in-game minutes from the start
title = "The Brass Eclipse"
description = "The clockwork sun grinds to a halt."
```

## Items — `items/*.toml`

```toml
item_id = "rusty_sword"
name = "Rusty Sword"
description = "It has seen better centuries."
category = "weapon"              # default: "misc"
weight = 3.5
rarity = "common"
```

## Story setup — `setup/questions.toml`

Questions asked when a new game starts:

```toml
[[questions]]
setup_id = "origin"
question = "Where do you come from?"
type = "choice"                  # default: "text"
options = ["The Foundry", "The Undercity", "Outside the walls"]
max_selections = 1
priority = 0
```

## Compilation and the cache

`axiom compile my-world/` hashes the whole source tree and writes the compiled
database to `my-world/.axiom-cache/universe.db`, plus the hash, so unchanged
sources are not recompiled (`--force` overrides this; `-o` chooses another
output path). During authoring, `axiom dev my-world/` watches the tree and
recompiles on every change.

To **share** a universe, pack it into a single `.axiom` archive:

```console
$ axiom pack my-world/ MyWorld.axiom
$ axiom import MyWorld.axiom     # on the other side (v1 archives work too)
```

From Python, the same operations are available in
{py:mod}`axiom.compile`, {py:mod}`axiom.decompile`, {py:mod}`axiom.package`
and {py:mod}`axiom.dev`.
