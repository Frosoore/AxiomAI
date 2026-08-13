# Axiom Status

> **What this is.** A running, human-readable history of the project: what we **do**, what we
> **fix**, what we **implement**, and what we **break**. It is the narrative companion to the
> machine-formatted [`Changelog.md`](Changelog.md): shorter, plain-language, status-oriented.
>
> **🔴 The rule: update this file on every commit.** Whoever commits (a human, or an AI assistant
> like Claude / Gemini) adds **one entry at the top** of the log below, in the same change. A commit
> that touches code without a matching Axiom Status line is incomplete. Keep entries short and
> honest, including when something regressed or is still broken.
>
> **Stage of the project:** 🟧 **early alpha** (not beta). Expect rough edges and breaking changes.

---

## How to add an entry (for a human or an LLM)

Prepend a new bullet at the very top of the **Log** section, newest first, in this shape:

```
- **YYYY-MM-DD** · `<scope>` · <type>: <one-line, plain-language description>.
```

- `<scope>`: the area touched: `engine`, `ui`, `cli`, `docs`, `site`, `tests`, `ci`, `build`…
- `<type>`: one of: **add** · **fix** · **change** · **remove** · **break** · **chore**.
- Keep it to one line. If it matters to a player or a tester, say so in plain words.
- Once a month, distil the entries since the previous month into a summary on the
  **Dev updates** page (`landing/dev-updates.html`); that page is the public, monthly view of
  this same history.

---

## Log

<!-- Newest first. Add your line directly under this comment on every commit. -->

- **2026-08-13** · `ui` · change: Creator Stats table is a summary again (name, type, lasting/temp badge). Edit opens a full panel; crash/extend only show for buildup meters.
- **2026-08-13** · `engine` · change: Adding a stat classifies it from name + optional note via a fixed form (temporary? kind? fast vs slow). User notes are kept; empty notes may get a short description.
- **2026-08-13** · `engine` · add: Temporary is a per-stat profile (heal / buildup / duration). Creator checkbox + Infer, or classify on first play. The engine ticks healing and peak/crash; the narrator only reports events.
- **2026-08-13** · `engine` · add: Temporary stats (`modifiers`) tick with in-game time — overlays on the base, cleared by event. Play sidebar shows the remaining minutes.
- **2026-08-13** · `ui` · fix: Save editor entity stats were bound to lowercase `stat_id` so Apply worked in-game but re-Edit showed the old numbers. Lookup and write now follow the authored key.
- **2026-08-13** · `ui` · add: Narrator **Continue** (skip a player action). Chat Edit/Regenerate restyled so they stay readable on player and narrator bubbles.
- **2026-08-13** · `ui` · fix: Hub Edit failed to load older saves; resolve now takes the save file path and falls back to `saves/*/save_<id>.db`.
- **2026-08-13** · `engine` · fix: Hub listed zero saves after pull — entity-type migrate issued BEGIN inside an open transaction; `load_saves` then swallowed the error. Listing now survives a failed migrate.
- **2026-08-13** · `engine` · fix: Opening a month-old save after a pull migrates it in place (inventory + session lore + one-time `.pre-migrate.bak`). A failed migrate still opens the file — nothing is deleted.
- **2026-08-13** · `docs` · chore: Status, changelog, Task.md, save/universe guides, and web-continuation docs catch up to the structured save editor, typed stats, session lore, and nested inventory.
- **2026-08-13** · `tests` · change: Web tests that leaked a custom playthrough now use Myria names and lore (`ysolde_brask`, the Usurper).
- **2026-08-13** · `ui` · add: Web save editor is tabbed (entities / nested inventory / session lore / Advanced TOML). Creator types are extendable; stats can be linked to types. Play inventory is a tree; “Lore used this turn” shows why a book fired.
- **2026-08-13** · `engine` · add: Session_Lore (save-only, survives world refresh), Entity_Types + Stat_Type_Links, nested Item_Instances (entity / location / container). Canonize `scope=save` no longer writes the world lore book.
- **2026-08-13** · `engine` · fix: Inventory auto-creates unknown items (no catalog required). Canonize preview is a picker with colored diffs; apply defaults to this save so new games stay clean.
- **2026-08-13** · `engine` · fix: Tabletop stats now overlay Entity_Stats (authored values) with play changes, and map LLM aliases like `player`/`x` onto `x`/`y`. Web header uses the full chat width.
- **2026-08-13** · `ui` · add: Web Slices 2–4 — Setup 3-tab lobby, .axiomsave pack/unpack, Hub export + file pickers, Creator Studio depth, hover doc tooltips, first-launch tour, integrity check.
- **2026-08-13** · `ui` · add: Web Slice 1 — tabletop chrome (verbosity, canonize, rewind list, Hub), SSE token streaming with real cancel, per-provider settings keys, named player entity location.
- **2026-06-23** · `site` · add: Blog post "We asked an AI to tear Axiom apart" (Arbitrator + competitive audit write-up); refreshed the Dev-page roadmap (new Arbitrator-reliability and cost-controls items, NPC item narrowed to the actor model since memory shipped).
- **2026-06-21** · `chore` · change: Renamed the author pseudonym `17h59` to `Pinpanicaille` across the tree (NOTICE, README, docs, landing site, Myria credit).
- **2026-06-21** · `ui` · fix: `retranslate_tooltips` no longer crashes on language change when a documented widget's C++ object was already deleted (CI 3.12 flake); guard + prune via `shiboken6.isValid`.
- **2026-06-21** · `site` · add: Blog post "Under the hood: how saves and universes work"; moved the save/universe QC item to Done on the roadmap and logged it in the June dev update.
- **2026-06-21** · `engine` · fix: `fired_turn_id` is preserved when exporting (`extract_save`/`.axiomsave`) and forking a save, so rewind can still un-fire scheduled events; added a guard test against save copy-list vs schema drift.
- **2026-06-20** · `ui` · fix: Player message editor now correctly rolls back VectorMemory semantic database and cleans up illustration assets.
- **2026-06-20** · `ui` · fix: Aligned memory and database user_input turn IDs to prevent complete history deletion during message rollbacks.
- **2026-06-16** · `site` · add: Created `AXIOM_STATUS.md` and the monthly **Dev updates** page; added an early-alpha tester banner, a feature-request form and Discord links to the landing site.
- **2026-06-16** · `docs` · change: Reframed the project status from “beta” to **early alpha** across the website and README.
