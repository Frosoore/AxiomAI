# TODO — web-ui-continuation

Continuation/consolidation of the Web Application Interface (`main_web.py` + `web/`, Phase 19
of `Task.md`, first drafted by Gemini CLI on 2026-07-02, still uncommitted). Scope: audit the
whole web UI against the Qt app it mirrors, document every `/api/*` endpoint, fix the bugs found,
and grow `tests/test_web_server.py` so the gameplay loop is actually covered.

- [x] Endpoint reference written in `DOC.md` (every route in `main_web.py` cross-checked against
      every `fetch()` call in `web/app.js`)
- [x] Fix: `Session` has no `_time_system` → `/api/session/start`, `/api/session/turn`,
      `/api/session/rewind` raise `AttributeError` on every call (core gameplay loop dead)
- [x] Fix: `/api/saves/create` never writes the turn-0 opening narrative (`first_message` +
      `@tag` substitution from setup answers) → new games start on a blank chat
- [x] Add: `/api/universes/delete` (called by the Hub's Delete button, currently 404)
- [x] Add: `/api/diagnostic` (called by the Diagnostic modal, currently 404)
- [x] Fix: `/api/saves/fork` reimplements forking with raw SQL instead of `axiom.saves.fork_save`,
      dropping Active_Modifiers / Fired_Scheduled_Events (`fired_turn_id`) / Timeline /
      Items_Inventory on fork (regresses TICKET-034/075/086)
- [x] Cleanup: dead `calendar = ACTIVE_SESSION._arbitrator._time_llm` line in `/api/session/start`
- [x] Tests: full session lifecycle (create → start → turn → rewind), universes/delete,
      diagnostic, saves/fork data integrity
- [x] `AXIOM_STATUS.md` entries + this CHANGELOG kept current as work lands
- [x] Full relevant test suite green, no regressions (web server 10/10 + savestore/session/packaging = 76 passed)

Not in scope for this pass (noted, not actioned): `/api/creator/save` and
`workers/db_worker.py::SaveFullUniverseTask` both reimplement universe persistence with raw SQL
instead of a shared `axiom/` helper — pre-existing debt on the Qt side too, not something to fix
as a side effect here.

## Session 4 (2026-07-02) — critical fix: Creator Studio entirely empty

- [x] `Connections` → `Location_Connections` (3 call sites in `main_web.py`: GET
      `/api/creator/data`, POST `/api/creator/save` DELETE+INSERT) — the wrong table name 500'd
      the *whole* `/api/creator/data` response on any universe with map data, blanking every tab,
      not just Map. Verified fixed against the real bundled `universes/Myria`. Also hardened
      `openCreatorStudio()` to check `res.ok` (was silently accepting error bodies as data — the
      reason it looked like "empty tabs" instead of a visible crash). Regression test:
      `test_creator_data_map_connections_round_trip`. See CHANGELOG.
- [ ] Follow-up worth doing next time someone touches the Map tab: audit column names too (only
      table names were cross-checked this pass, via a live query against Myria's real data —
      column names look right by inspection but weren't independently swept the way table names were).

## Session 3 (2026-07-02) — critical fix: app.js was never loaded

- [x] `web/index.html` had no `<script src="app.js">` tag at all — the entire app was inert in a
      real browser (every button, every screen) despite all API-level tests passing, since those
      only exercise `main_web.py` directly, never a real page load. Fixed + regression test
      (`test_static_routes` now asserts `src="app.js"` is present). See CHANGELOG for the full
      writeup and an important caveat: **no browser/node/chromium-cli/Playwright is available in
      this sandbox, so this was not confirmed by actually clicking through the app** — only by
      static analysis + a test that encodes the fix. A real click-through still needs doing.

## Session 2 (2026-07-02) — full Qt↔web feature-parity pass

User ask: "continue la refactorisation de l'UI en html/css/js, tout doit être fonctionnel et
parfaitement similaire à l'ancienne UI [Qt]." Full gap inventory done via a codebase-wide
Qt-vs-web comparison (`ui/*.py`, `ui/widgets/*.py`, `workers/*.py` vs `web/app.js`). Working
this list top to bottom; check items off as they land, with tests, and keep this file the
authoritative backlog across sessions (same convention as `maintenance/project_pilier2_status`).

**Core gameplay (doing this session):**
- [x] Inventory sidebar tab (per-entity items, `Items_Inventory`) — `/api/session/inventory`,
      left-sidebar Stats/Inventory mini-tabs
- [x] Message edit (player + AI) / regenerate / variant navigation in chat — `/api/session/{variant,
      regenerate,edit-message}`; history is now a turn_id-tagged raw event list (was role/content
      pairs) so the client can drive per-bubble controls; `build_session_snapshot()` factored out
      of start/turn/rewind to share this
- [x] Global Personas system (Settings tab CRUD + Setup wizard picker) — `/api/personas` GET/POST,
      new Settings "Personas" tab, Setup wizard picker auto-fills the free-text field (simplified
      vs Qt: no inline `PersonaCreationDialog` in Setup, CRUD lives in Settings only)
- [x] Audio ambiance playback — `/api/audio/track?tag=`, static `/audio/<tag>/<file>` route,
      dual-`<audio>` JS crossfade (mirrors `ui/ambiance_manager.py`'s timing constants exactly),
      triggered from `ArbitratorResult.game_state_tag` (now surfaced by `/api/session/turn`).
      Inert until a user drops files in `assets/audio/<tag>/` — same as Qt, app ships with none.
- [x] Hardcore mode permadeath flow — `/api/session/turn` flags `hardcore_death` (mirrors
      `ui/tabletop_hardcore.py`'s Player_Death rule scan + Hardcore-mode check),
      `POST /api/session/hardcore-delete` performs the irrevocable teardown (backup, WAL flush,
      row+assets+vector deletion, refuses on non-Hardcore sessions). Minor known gap: the
      `edit-message` user_input branch's resubmit doesn't re-check for death (rare edge case,
      noted not fixed).
  Bonus fix found while researching this: `/api/saves/delete` (Session 1) called the wrong,
  wrong-arity function (`CheckpointManager.delete_save`, Hardcore-only + missing `universe_dir`)
  — every call 500'd. Fixed to `axiom.savestore.delete_save` + vector cleanup, matching
  `workers/db_tasks.py::DeleteSaveTask`. New test coverage for both.

**Deferred to a follow-up session (documented, not started):**
- [ ] Memory Browser (Facts/Observations/Mental Models, 3-tab dialog + trends) + Settings "Memory" tab
- [ ] Multiplayer/hotseat (player selector, per-player intent queue, `axiom/multiplayer.py`)
- [ ] Canonize workflow (story → universe lore, diff preview) + "Canon auto" toggle
- [ ] Help system depth (real tooltips, per-page "Explain", searchable directory, real Quick Tour —
      today `btn-menu-explain`/`btn-menu-tour` are placeholder `alert()`s)
- [ ] Settings gaps: wallpaper picker, basic/negative image prompts, `doc_tooltips_enabled`,
      `trim_sentences`, per-provider model browser dialog, `image_gemini_model`, `image_timeout`
- [ ] Polish: checkpoint list dialog UX (vs raw slider), global cancel-generation button, timeline/
      chronicler world-news log tab (distinct from the rewind slider), hero-intent chat bubble
      styling (Companion mode), Ctrl+Z/Ctrl+Y rewind shortcuts, image click-to-zoom lightbox

Full inventory with Qt file/class/engine-call references for every item above: see the
Explore-agent report archived at the bottom of `CHANGELOG.md`'s Session 2 entry.
