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

- **2026-07-02** · `ui` · fix: Every Creator Studio tab rendered empty — `main_web.py` queried a table called `Connections` that has never existed (schema name is `Location_Connections`), 500ing the *entire* `/api/creator/data` response on any universe with map data (not just the Map tab); `openCreatorStudio()` also never checked `res.ok`, so the error body was silently treated as data. Fixed both (3 SQL call sites + a client-side error check); verified against the real bundled `universes/Myria` (11 entities, 18 locations, 7 connections — all now returned correctly, previously a 500). Audited every other table name in `main_web.py` against the schema; no other mismatches found.
- **2026-07-02** · `ui` · break/fix: The entire web client was non-interactive — `web/index.html` never had a `<script src="app.js">` tag, so the JS was servable but never loaded by the browser; every button on every screen (not just the Hub) silently did nothing since the very first draft. Fixed + regression test (`test_static_routes` now checks for `src="app.js"`). Caveat: this sandbox has no browser/node/chromium-cli to actually click through the fix — verified statically + by test only.
- **2026-07-02** · `ui` · add: Web client feature-parity pass toward the Qt app — inventory sidebar tab (`/api/session/inventory`); in-chat message edit/regenerate/variant-navigation (`/api/session/{variant,regenerate,edit-message}`, chat history now turn_id-tagged instead of role/content pairs); global Personas system (`/api/personas`, Settings tab + Setup picker); ambiance audio actually plays now (`/api/audio/track`, dual-`<audio>` crossfade driven by `ArbitratorResult.game_state_tag`, was a dead volume slider before); Hardcore mode permadeath flow (`/api/session/hardcore-delete`, Player_Death rule detection). Found & fixed along the way: `/api/saves/delete` called the wrong, wrong-arity engine function and 500'd on every call (now `axiom.savestore.delete_save` + vector cleanup, matching the Qt Hub's Delete button). `tests/test_web_server.py` grown from 11 to 22 tests. Remaining gaps (Memory Browser, Multiplayer, Canonize workflow, real tooltip/quick-tour help content) tracked in `maintenance/features/web-ui-continuation/TODO.md`.
- **2026-07-02** · `ui` · fix: Web client gameplay loop was completely broken (`/api/session/start|turn|rewind` crashed on a nonexistent `Session._time_system`); new saves started on a blank chat (opening `first_message` + `@tag` substitution was never written); `Hub → Delete` and the Diagnostic modal 404'd (missing `/api/universes/delete`, `/api/diagnostic` routes); `saves/fork` reimplemented forking with raw SQL and dropped Active_Modifiers/Fired_Scheduled_Events (regressing TICKET-034/075/086) — now delegates to `axiom.saves.fork_save`. Endpoint reference documented in `maintenance/features/web-ui-continuation/DOC.md`; `tests/test_web_server.py` grown from 6 to 10 tests covering the full session lifecycle, universe deletion, diagnostics and fork data integrity.
- **2026-07-02** · `ui` · fix: Fixed presets ID generation and wired up events-add-btn, status-cancel-btn, and btn-menu-hub click listeners in the web client.
- **2026-07-02** · `ui` · change: Refactored `run.sh` / `run.bat` launch scripts to support `--web` mode; implemented backend endpoints and front-end modal dialog for exporting, editing and diffing save state TOML files.
- **2026-07-02** · `ui` · add: Web interface main_web.py with HTML/CSS/JS frontend mirroring the Qt tabletop and creator studio screens, and corresponding test suite.
- **2026-06-23** · `site` · add: Blog post "We asked an AI to tear Axiom apart" (Arbitrator + competitive audit write-up); refreshed the Dev-page roadmap (new Arbitrator-reliability and cost-controls items, NPC item narrowed to the actor model since memory shipped).
- **2026-06-21** · `chore` · change: Renamed the author pseudonym `17h59` to `Pinpanicaille` across the tree (NOTICE, README, docs, landing site, Myria credit).
- **2026-06-21** · `ui` · fix: `retranslate_tooltips` no longer crashes on language change when a documented widget's C++ object was already deleted (CI 3.12 flake); guard + prune via `shiboken6.isValid`.
- **2026-06-21** · `site` · add: Blog post "Under the hood: how saves and universes work"; moved the save/universe QC item to Done on the roadmap and logged it in the June dev update.
- **2026-06-21** · `engine` · fix: `fired_turn_id` is preserved when exporting (`extract_save`/`.axiomsave`) and forking a save, so rewind can still un-fire scheduled events; added a guard test against save copy-list vs schema drift.
- **2026-06-20** · `ui` · fix: Player message editor now correctly rolls back VectorMemory semantic database and cleans up illustration assets.
- **2026-06-20** · `ui` · fix: Aligned memory and database user_input turn IDs to prevent complete history deletion during message rollbacks.
- **2026-06-16** · `site` · add: Created `AXIOM_STATUS.md` and the monthly **Dev updates** page; added an early-alpha tester banner, a feature-request form and Discord links to the landing site.
- **2026-06-16** · `docs` · change: Reframed the project status from “beta” to **early alpha** across the website and README.
