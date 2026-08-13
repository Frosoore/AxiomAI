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
├── types/
│   └── types.toml           # extra entity types (optional; builtins are seeded)
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
entity_type = "npc"              # catalog id: builtin player/npc/faction/world, or a type you added
name = "Marla the Innkeeper"
description = "A weathered woman who hears everything."
is_active = true                 # default: true

[stats]                          # initial stat values (strings)
Health = "100"
Location = "tavern"
Mood = "wary"
```

`entity_type` is a catalog id, not the character's name. The four builtins
(`player`, `npc`, `faction`, `world`) are also **roles** the engine uses
(who is the player, whom the Chronicler tracks). Extra types declare a role
so a `robot` still counts as an `npc`.

## Entity types — `types/types.toml`

Optional. Builtins are always present. Add kinds the world needs:

```toml
[[types]]
type_id = "robot"
name = "Robot"
role = "npc"                     # player | npc | faction | world
description = "A constructed body. Battery, not blood."
```

## Stat definitions — `stats/definitions.toml`

```toml
[[definitions]]
stat_id = "Health"
name = "Health"
description = "Hit points."
value_type = "numeric"           # default: "numeric"
temporary = true                 # engine ticks this; omit or false = lasting
parameters = { min = 0, max = 100 }
# applies_to = ["player", "npc"] # optional; omit = every type

[definitions.dynamics]
kind = "heal"                    # heal | buildup | duration
resting = 100                    # value time pulls toward (healthy max, or 0)
heal_minutes = 20160             # ~2 weeks to close a serious wound
# peak_hold_minutes = 8          # buildup: how long it can sit at max
# crash_on = ["orgasm"]          # buildup: event tags that snap to resting
# extend_on = ["edging"]         # buildup: event tags that refresh the peak
# basis = "Closes over days unless treated."
```

`applies_to` lists type ids that may hold the stat. Empty (or omitted) means
every type — existing worlds keep working. Arousal on a human player and
Battery on a `robot` are the intended split.

**Temporary** is a property of the definition, not a hardcoded list of names.
When you Add a stat, Creator sends **name + optional note** through a fixed
form: is it temporary, what kind, and is the timeline **fast** (scene /
hours) or **slow** (days–weeks)? The note is never overwritten; an empty
note may get a short description back. The stats table is a summary
(lasting vs `kind · pace`); **Edit** opens the full profile. Crash/extend
tags only appear on **buildup** meters. **Infer temporary…** runs the same
form on every row. Play start classifies anything still unmarked on that
save. The engine then:

- **heal** — drifts toward `resting` with in-game time (wounds, vitality).
- **buildup** — the narrator only reports scene-driven change; the engine
  clamps, tracks time at peak, and snaps to resting on a listed `stat_events`
  tag. Rate is allowed to vary by character.
- **duration** — short overlay that also eases toward resting (intoxication).

Lasting stats (cash, reputation, location) stay put until the story changes
them. The narrator is told not to fake the decay.

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

Keyword lists matter: the arbitrator matches a turn against `keywords` + name
(and a short content excerpt) when semantic retrieval is off. Empty keywords
weaken that fallback. Lore that belongs only to one playthrough lives in the
save (`Session_Lore`), not under `lore/` — see [Saves](saves.md).

## Scheduled events — `events/*.toml`

Events fire when the in-game clock reaches `trigger_minute`:

```toml
event_id = "eclipse"
trigger_minute = 4320            # in-game minutes from the start
title = "The Brass Eclipse"
description = "The clockwork sun grinds to a halt."
```

## Items — `items/*.toml`

Optional **definitions** only (name, category, whether it is a container).
There is no world-template inventory: what a character carries or stashes
appears during play (or in the save editor). Worlds like Myria may still
ship a few named relics here.

```toml
item_id = "rusty_sword"
name = "Rusty Sword"
description = "It has seen better centuries."
category = "weapon"              # default: "misc"
weight = 3.5
rarity = "common"
is_container = false             # optional; bags, purses, drawers
# capacity = 8                   # optional; omit = unlimited
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
