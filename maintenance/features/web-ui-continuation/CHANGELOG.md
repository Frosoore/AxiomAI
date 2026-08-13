# CHANGELOG — web-ui-continuation

## Session 2026-08-13 — classify on add (name + note)

- Add-stat sends STAT_NAME + AUTHOR_NOTE through a fixed form: temporary?,
  kind, pace (fast / medium / slow). Engine maps pace to minutes.
- User note is never overwritten; blank note may receive a short description.

## Session 2026-08-13 — stat dynamics (not hardcoded names)

- Creator Stats: Temporary checkbox, kind, timescale, crash/extend tags, **Infer temporary…**.
- Profiles live in `Stat_Definitions.parameters`. Engine ticks heal / peak / crash.
- Play start classifies any stat that still has no profile (save-local).
- Narrator prompt lists TEMPORARY STATS generically; `stat_events` replace named special cases.

## Session 2026-08-13 — editor stats + temporary modifiers

- Save editor entity fields resolve `stat_id` vs authored key case-insensitively,
  so Apply then re-Edit shows the same numbers play already had.
- New **Temporary** tab lists `Active_Modifiers`. Apply replaces that list.
- Narrator JSON accepts `modifiers` (`delta` + `minutes`, or `clear`). They overlay
  the tabletop sidebar and tick down with in-game minutes.

## Session 2026-08-13 — living game state

- Save Edit is no longer a single TOML textarea. Tabs: Entities (type-filtered stats),
  Inventory (tree, add container/item), Session lore (save-only, empty-keyword warning),
  Advanced TOML.
- `GET/POST /api/saves/state` wrap `materialize_state` / `apply_structured_state`.
- Creator: extendable `Entity_Types`, stat `applies_to` multi-select, initial-stats panel
  filtered by type. Still no inventory tab (items are play-emergent).
- Play inventory is a nestable tree (`Item_Instances`); `POST /api/session/inventory/move`.
- Session lore + turn `lore_hits` on the right rail. Canonize `scope=save` → `Session_Lore`.
- Web tests that named a private custom world now use Myria (`ysolde_brask`, Usurper lore).

## Session 1 (2026-07-02)

- Read the full web stack (`main_web.py` 1207 lines, `web/app.js` 2048 lines, `web/index.html`,
  `tests/test_web_server.py`) and cross-referenced every `fetch()` call against the backend route
  table.
- Audit findings (see `TODO.md` for the fix list):
  - `/api/session/start|turn|rewind` crash: `ACTIVE_SESSION._time_system` does not exist on
    `Session` (it is a Qt-app-only construct built in `ui/tabletop_view.py` from
    `Universe_Meta.calendar_config`). Every response returns `{"error": ...}` today.
  - New saves never get their opening narrative: `ui/tabletop_view.py::_show_first_message`
    (variant pick + `@tag` substitution from setup answers) has no equivalent in
    `/api/saves/create`.
  - `web/app.js` calls two routes the backend never defines: `POST /api/universes/delete` and
    `GET /api/diagnostic`.
  - `/api/saves/fork` hand-rolls a subset of `axiom.saves.fork_save`'s SQL, silently dropping
    fixes from TICKET-034/075/086.
- Fixes landed (all in `main_web.py` unless noted):
  - Added `get_time_system(db_path)` (reads `Universe_Meta.calendar_config`, mirrors
    `ui/tabletop_view.py`'s `TimeSystem(CalendarConfig.from_json(...))`) and switched
    `/api/session/start|turn|rewind` to call it instead of the nonexistent
    `ACTIVE_SESSION._time_system`. Removed the dead `calendar = ACTIVE_SESSION._arbitrator._time_llm`
    line in `/api/session/start` while there.
  - `/api/saves/create` now writes the turn-0 `narrative_text` event from the universe's
    `first_message` (variant split on `---VARIANT---`, `@tag` substitution from `setup_answers`,
    case-insensitive) — same behaviour as `ui/tabletop_view.py::_show_first_message`.
  - Added `POST /api/universes/delete` (mirrors `ui/hub_view.py::_on_card_delete_requested`:
    deletes saves + their vector stores first, then the universe folder/flat-db + WAL/SHM sidecars).
  - Added `GET /api/diagnostic` (`tools.diagnostic.run_diagnostics()` + `format_report()`).
  - `/api/saves/fork` now calls `axiom.saves.fork_save(db_path, save_id, at_turn=..., player_name=...)`
    directly instead of reimplementing a Saves+Event_Log-only copy.
- `tests/test_web_server.py` grown from 6 to 10 tests: `test_universes_delete_removes_flat_db`,
  `test_diagnostic_endpoint_returns_report`, `test_session_lifecycle_start_turn_rewind` (full
  create → start → turn → rewind through real HTTP, LLM/Timekeeper mocked via
  `patch("axiom.config.build_llm_from_config", ...)` + `patch("axiom.session.Session._resolve_time_llm", ...)`),
  `test_saves_fork_preserves_modifiers_and_fired_events`. All would have failed before the fixes
  above. Verified green together with `test_savestore.py`, `test_session.py`, `test_packaging.py`
  (76 passed).

## Session 2 (2026-07-02) — feature-parity pass

Full Qt-vs-web gap inventory (Explore agent, codebase-wide read of `ui/*.py`, `ui/widgets/*.py`,
`workers/*.py` cross-checked against `web/app.js`/`web/index.html`). Archived verbatim below;
the prioritized backlog derived from it lives in `TODO.md` and is the thing to keep updated as
items land.

<details>
<summary>Raw gap inventory (Explore agent report)</summary>

Qt tabletop_view.py: message edit/regenerate/variant nav, multiplayer hotseat, companion hero-intent
bubble, inventory sidebar, timeline/chronicler log tab, checkpoint dialog (vs web's slider), canonize
workflow + diff preview, living-memory auto-extraction + "extract now", verbosity slider, audio
ambiance auto-switching, image lightbox, rejected-changes toast, Ctrl+Z/Y shortcuts, integrity warning
dialog -- all MISSING or PARTIAL in web (0 grep hits in app.js for regenerate/inventory/multiplayer/
canoniz/memory-browser keywords).

ui/memory_browser.py: 3-tab Mental Models / Beliefs+trend / Facts dialog -- MISSING wholesale.

ui/checkpoint_dialog.py: discrete checkpoint list dialog -- PARTIAL (web uses a raw turn slider).

Personas: ui/widgets/persona_editor.py (global CRUD, Settings tab) + Setup wizard persona picker --
MISSING (web Setup has a single free-text persona textarea only).

ui/ambiance_manager.py: dual-QMediaPlayer crossfade by game_state_tag, random file pick, volume --
MISSING (web's volume slider/audio checkbox drive nothing; /api/audio/volume is a no-op).

ui/help_system.py + help_dialogs.py: ~120-entry tooltip registry, per-page F1 explain, searchable
directory, 7-step Quick Tour -- web's Explain/Tour buttons are placeholder alert() one-liners.

ui/widgets/lore_book_editor.py / stat_definition_editor.py: multi-cell select/fill, stat presets --
PARTIAL vs web's simpler single-row tables (presets combo already exists in web Stats tab).

ui/settings_dialog.py fields missing from web: Memory tab (memory_mode, fact_interval, fact_model,
reranker/beliefs/mental_models/prompt_cache toggles, extract-now/browse-memory buttons), Personas tab,
per-provider model browser dialog, image_gemini_model, image_timeout, doc_tooltips_enabled,
trim_sentences, custom_wallpaper picker, basic_prompt/negative_prompt, per-universe temperature/top_p.

ui/main_window.py: F1/global shortcuts, global cancel-generation button (polls active_generation_count
every 500ms), wallpaper theming, first-launch Quick Tour auto-trigger -- MISSING.

ui/tabletop_hardcore.py: Player_Death rule detection + confirm dialog + full teardown (kill workers,
HardcoreWorker deletes DB/vector-store/universe files) -- MISSING (web's "Hardcore" is just a select
option string with no death handling).

Inventory: single source ConstantsSidebar.refresh_inventory / DbWorker.inventory_loaded -- MISSING
wholesale from web (no tab, no endpoint).

Multiplayer: axiom/multiplayer.py (PlayerAction/ActionQueue) + TabletopView hotseat intent
accumulation, player selector -- MISSING wholesale from web.

</details>

### Landed: Inventory tab + message edit/regenerate/variant-nav (2026-07-02)

- `GET /api/session/inventory`: mirrors `workers/db_tasks.py::LoadInventoryTask` via the engine's
  own `axiom.db_helpers.get_inventory`. New left-sidebar mini-tabs (Stats/Inventory) in
  `web/index.html`/`app.js`/`style.css`.
- `build_session_snapshot()` helper factored out of `/api/session/start|turn|rewind` (was ~25
  lines duplicated 3x) and reused by 3 new endpoints:
  - `POST /api/session/variant` (`{turn_id, variant_index}`) — flips the active variant of a
    `narrative_text` event.
  - `POST /api/session/regenerate` (`{turn_id}`) — calls `Session.regenerate_variant` (already a
    clean engine API from B4), reading temperature/top_p from `Universe_Meta` (+0.1 temp, mirrors
    `ui/tabletop_view.py::_on_regenerate_requested`).
  - `POST /api/session/edit-message` (`{event_type, turn_id, new_text}`) — `user_input` branch
    rewinds to `turn_id-1` then resubmits as a new turn (mirrors the Qt rollback+resubmit flow);
    `narrative_text` branch patches the active variant in place via `EventSourcer.update_event_payload`
    + `VectorMemory.update_turn_narrative` (best-effort), no rewind.
  - `history` in `build_session_snapshot()` changed shape: turn_id-tagged raw events
    (`{turn_id, event_type, payload}`, mirrors `LoadSessionHistoryTask`) instead of
    `Session._load_history()`'s role/content pairs, since the client needs turn_id + variant
    metadata per message to render edit/regenerate/variant-nav controls.
- Frontend: `appendMessage` replaced by `appendBubble`/`renderHistoryEvent`/`rebuildChatFromHistory`;
  every persisted message bubble gets an Edit button (+ Regenerate/variant nav on AI messages);
  `hero_intent` events render with the existing (previously unused) `.chat-bubble.hero` amber style;
  images are now re-resolved from `turn_<n>.png` on every rebuild (`onerror` hides the `<img>`)
  instead of only appearing transiently right after generation.
- Tests: 4 new (`test_session_edit_message_ai_patches_active_variant`,
  `test_session_edit_message_user_input_rewinds_and_resubmits`,
  `test_session_regenerate_appends_variant_and_switches_active`, `test_session_variant_switch`) +
  `test_session_inventory_endpoint`; `test_session_lifecycle_start_turn_rewind` updated for the new
  history shape. 15/15 green.

### Landed: Global Personas system (2026-07-02)

- `GET/POST /api/personas`: mirrors `workers/db_tasks.py::{Load,Save}GlobalPersonasTask` against
  `Global_Personas` in the machine-global `global.db`. Uses `axiom.config._resolve_global_db_file()`
  (override-aware) rather than the frozen `GLOBAL_DB_FILE` constant so tests can isolate it via
  `AXIOM_CONFIG_DIR` — real-app behavior is unchanged (same resolved path when no override is set).
- Settings modal: new "Personas" tab (name/description table, add/delete), saved together with the
  rest of Settings on the Save button (matches `ui/settings_dialog.py::_save_personas_async`).
- Setup wizard: new "Saved Persona" picker above the free-text persona textarea; selecting one
  auto-fills the textarea (still freely editable). Simplified vs Qt: no inline persona-creation
  dialog in Setup (CRUD lives in Settings only) — noted as a deliberate scope cut, not a bug.
- Test: `test_personas_crud` (round-trip + replace-shrinks-list semantics), isolated via
  `monkeypatch.setenv("AXIOM_CONFIG_DIR", ...)`. 16/16 green.

### Landed: Audio ambiance playback (2026-07-02)

- `GET /api/audio/track?tag=<tag>`: mirrors `ui/ambiance_manager.py::_pick_random_file` (random
  `.mp3`/`.ogg`/`.wav` from `assets/audio/<tag>/`, repo-bundled/opt-in, app ships with none).
  `pick_ambiance_track()`/`AUDIO_ASSETS_DIR` are module-level so tests can monkeypatch the assets
  root without writing into the real repo tree.
- Static `GET /audio/<tag>/<file>` route (same traversal-guard pattern as the existing `/assets/`
  handler) serves the picked track.
- `/api/session/turn` (and the `edit-message` user_input branch) now also returns `game_state_tag`
  from `ArbitratorResult` (already an engine-level field, `axiom/arbitrator.py`).
- Frontend: dual-`<audio>` crossfade in `app.js` (`updateAmbiance`/`stopAmbiance`/
  `setAmbianceVolume`), same `FADE_DURATION_MS=3000`/`FADE_STEP_MS=50` constants as
  `AmbianceManager`. Triggered on session start (`exploration` default, mirrors
  `tabletop_view.py:447`) and after every turn. Volume slider and "Enable Background Audio"
  checkbox now actually drive playback (previously dead controls); `#status-audio-label` reflects
  the active tag.
- Tests: `test_audio_track_no_bundled_assets_returns_null`,
  `test_audio_track_picks_and_serves_bundled_file` (isolated via `monkeypatch.setattr(main_web,
  "AUDIO_ASSETS_DIR", tmp_path)`), `test_session_turn_includes_game_state_tag`. 19/19 green.

### Bug found + fixed while researching Hardcore mode: /api/saves/delete (2026-07-02)

`/api/saves/delete` (written in Session 1, never covered by a test) called
`axiom.checkpoint.CheckpointManager.delete_save(save_id)`: wrong function (that one is
Hardcore-only and recursively deletes an entire `universe_dir`) AND wrong arity (missing the
required `universe_dir` arg -- every call raised `TypeError`, surfaced to the client as a 500).
Fixed to `axiom.savestore.delete_save(db_path, save_id)` (the general single-save deletion the Qt
Hub's Delete button also uses via `workers/db_tasks.py::DeleteSaveTask`), plus the VectorMemory
directory cleanup `DeleteSaveTask` does alongside it that `savestore.delete_save` doesn't cover on
its own. New test: `test_saves_delete_removes_only_the_targeted_save`. 20/20 green.

Also clarified for the record: `axiom.checkpoint.CheckpointManager.delete_save` turns out to be
dead code in the engine today -- nothing in the Qt app calls it either (`ui/tabletop_hardcore.py`'s
actual Hardcore deletion goes through `workers/hardcore_worker.py::HardcoreWorker`, a separate
from-scratch sqlite3 implementation). Left as-is (out of scope to clean up unused engine code here).

### Landed: Hardcore mode permadeath flow (2026-07-02)

- `is_player_death_triggered(result)`: mirrors `ui/tabletop_hardcore.py::_check_for_player_death`'s
  rule scan (a `trigger_event` action whose `event` field contains "player_death", case-insensitive).
- `perform_hardcore_deletion(db_path, save_id)`: mirrors `workers/hardcore_worker.py::HardcoreWorker
  ._execute()` (fail-safe `create_auto_backup(..., "hardcore_death")`, WAL checkpoint/flush, then
  the same `axiom.savestore.delete_save` + vector-store cleanup `/api/saves/delete` uses) minus the
  Qt-thread lock-release choreography -- the web server holds no handles across requests, so
  there's nothing analogous to release first.
- `/api/session/turn` now reports `hardcore_death: bool` (Hardcore-mode session + death rule fired)
  without acting on it; `POST /api/session/hardcore-delete` performs the actual irrevocable
  teardown and clears `ACTIVE_SESSION`, refusing (400) on a non-Hardcore session.
- Frontend: `submitTurn()` checks `result.hardcore_death` and, if set, runs `handleHardcoreDeath()`
  (reuses the existing `death_text`/`save_deleted_text`/`deletion_failed_title` i18n keys, stripped
  of their Qt-rich-text HTML for `alert()`), then returns to the Hub.
- Tests: `test_is_player_death_triggered` (unit, 5 cases) + `test_hardcore_delete_removes_save_and_
  blocks_non_hardcore` (Normal session refused, Hardcore session wiped, dangling ACTIVE_SESSION
  correctly cleared). 22/22 green.

### Critical fix: index.html never loaded app.js at all (2026-07-02)

User report: "Hub buttons don't work." Root cause was much bigger than the Hub: `web/index.html`
had `<link rel="stylesheet" href="style.css">` in `<head>` but **no `<script src="app.js">` tag
anywhere in the document** -- the entire JS file was servable (`GET /app.js` worked, per
`test_static_routes`) but the browser never loaded/executed it. Every button in the whole app was
inert (Hub, Setup, Tabletop, Creator Studio, Settings, everything) -- the page rendered fine
visually (CSS was linked correctly) which is why it looked like a working page with dead buttons
rather than an obviously broken one.

This had been true since the very first draft (Session 1) and every session since -- all backend
work was verified via synthetic HTTP tests against `main_web.py` directly, which correctly proved
the API layer, but nothing ever asserted the frontend actually wired itself up in a real browser
loading the real page. `test_static_routes` checked `href="style.css"` was present but never
checked for `src="app.js"`.

**Fix:** added `<script src="app.js"></script>` before `</body>`. **Regression test:**
`test_static_routes` now also asserts `'src="app.js"' in html`.

**Verification caveat (read before trusting this "fixed"):** this sandboxed environment has no
browser, no `node`/`npm`, no `chromium-cli`, and no Playwright installed -- there is no way here to
actually load the page in a browser and watch it work. What was done instead: (1) root-caused via
static analysis (grep for `<script`, confirmed absent), (2) fixed it, (3) added a test that fails
without the fix and passes with it, (4) re-read the rest of `index.html`'s `<head>` to confirm no
sibling asset tag is *also* missing (CSS was fine). This is NOT the same as confirming the buttons
now work in a real browser -- that still needs a human (or a future session with browser tooling)
to actually click through it.

### Critical fix: Creator Studio entirely empty — wrong table name (2026-07-02)

User report: "Tous les tabs de l'universe studio sont vides" (all Creator Studio tabs are empty).

Root cause: `main_web.py` queried/wrote a table called `Connections` in `/api/creator/data` (GET)
and `/api/creator/save` (POST) — that table has never existed; the schema (`axiom/schema.py`)
calls it `Location_Connections`. On ANY universe with map data (confirmed against the bundled
`universes/Myria`), `GET /api/creator/data` raised `sqlite3.OperationalError: no such table:
Connections`, which 500'd the *entire* response — not just the Map tab's connections — because
all the per-tab data (stats, entities, rules, lore, etc.) is assembled into one dict in a single
try/except and returned together. One bad table name broke every tab.

Compounding it: `openCreatorStudio()` in `app.js` never checked `res.ok` before treating the
response as valid data (`fetch()` only rejects on network failure, not on 4xx/5xx) — so the 500's
`{"error": ...}` body was silently accepted as `STATE.creatorData`, every `fillCreator*()` read
`undefined` fields, and every tab rendered blank with **no error surfaced anywhere**. This is why
it looked like "empty tabs" rather than an obvious crash.

**Fix:** `Connections` → `Location_Connections` in both the read and write handlers (3 call sites);
`openCreatorStudio()` now checks `res.ok` and throws (surfaced via `alert()`) on a backend error
instead of silently proceeding with garbage data.

**Verified against real data** (not just synthetic fixtures): ran `main_web.py` in-process against
the bundled `universes/Myria` (11 entities, 18 locations, 7 connections, 4 rules, 15 lore entries,
44 files) — `/api/creator/data` now returns everything correctly where it 500'd before.

**Audit done while fixing:** cross-checked every SQL table name in `main_web.py` (13 distinct
names) against `axiom/schema.py`'s actual `CREATE TABLE` statements — `Location_Connections` was
the only mismatch.

New test: `test_creator_data_map_connections_round_trip` (GET returns locations+connections
correctly, POST /api/creator/save round-trips an added connection). 24/24 green.
