# DOC — web-ui-continuation

## Objective

`main_web.py` + `web/` (Phase 19 of `Task.md`) is a second frontend for the Axiom engine,
alongside the Qt desktop app (`main.py`/`ui/`/`workers/`) and the terminal CLI (`axiom play`).
It is a plain HTTP/JSON server (`http.server.ThreadingHTTPServer`, stdlib only, no framework) that
serves a vanilla-JS single-page app mirroring every Qt screen: Hub, Story Setup, Tabletop (play),
Creator Studio, Settings, Diagnostic. It talks to the exact same `axiom/` engine as the Qt app —
per `ARCHITECTURE.md`'s golden rules, `main_web.py` plays the same role as a `workers/` shell: it
must call engine functions, not reimplement game/persistence logic.

Run it with `python main_web.py [port]` (default port **8000**) or `run.sh --web [port]` /
`run.bat --web [port]` (added 2026-07-02). It opens `http://127.0.0.1:<port>/` in a browser.

**Status vs the Qt app (2026-08-13):** Hub, Setup 3-tab lobby, Tabletop (chat + edit/
regenerate/variant-nav + nested inventory tree + spatial nav + rewind list + ambiance +
verbosity + canonize + SSE token stream + real cancel + lore-hits), Creator Studio (type
catalog + stat↔type links, no item catalog), Settings (Universal + Cloud per-provider
keys, Memory, Personas, wallpaper/prompts/tooltips), Diagnostic and Hardcore permadeath
are functionally ported. Save **Edit** is a structured tabbed editor on web; Qt still
uses the TOML dialog. Slices 1–4 and the living-game-state pass (19.28–19.31) are done.

## Design notes / known limitations

- **Single global session.** `ACTIVE_SESSION` is one process-wide `Session` instance (guarded by
  `ACTIVE_SESSION_LOCK`). There is no per-tab/per-user isolation — this is a local, single-player
  tool, same assumption as the Qt app (one window, one active game).
- **CORS wide open** (`Access-Control-Allow-Origin: *`). Fine for a `127.0.0.1`-only local server;
  would need tightening if ever exposed beyond localhost.
- **`/api/settings` returns the config verbatim**, including plaintext API keys. Acceptable for a
  same-machine localhost tool (the Qt Settings dialog has the same exposure locally), but do not
  put this server on a shared network.
- **Streaming.** The UI uses `POST /api/session/turn/stream` (SSE: `status` / `token` / `done`).
  Blocking `POST /api/session/turn` remains for tests and as a fallback.

## Endpoint reference

All JSON unless noted. Static routes: `GET /` → `web/index.html`, `GET /style.css`,
`GET /app.js`, `GET /assets/<rel_path>` → game illustrations under `~/AxiomAI/assets/`.

### Settings & i18n

| Method | Path | Params | Notes |
|---|---|---|---|
| GET | `/api/translations` | – | Active-language `tr()` dict (`core.localization.get_translations_dict()`), driven by `load_config().language`. |
| GET | `/api/settings` | – | Full `AppConfig.__dict__` (includes API keys). |
| POST | `/api/settings` | body = full config | Rebuilds `AppConfig(**payload)`, `save_config()`. |
| POST | `/api/settings/test-connection` | – | Builds the configured LLM backend and calls `.is_available()`. |

### Hub / universe library

| Method | Path | Params | Notes |
|---|---|---|---|
| GET | `/api/universes` | – | Scans `UNIVERSES_DIR`; for each entry (flat `.db` or folder) returns `{name, description, path, is_folder, saves[]}` via `load_saves()`. |
| POST | `/api/universes/create` | body `{name}` | `create_universe_db` + `provision_blank_universe`. |
| POST | `/api/universes/import` | body `{path}` (`.axiom` archive) | `axiom.package.unpack_universe`. |
| POST | `/api/universes/import-st` | body `{path}` (SillyTavern PNG/JSON card) | `core.st_parser.parse_st_card` → new universe DB, composite lore, first-message variants (incl. `character_book`/lorebook v2 entries), a starter save with the (randomly chosen) turn-0 greeting. |
| POST | `/api/universes/delete` | body `{path}` | **Added this session** (see CHANGELOG). Mirrors `ui/hub_view.py::_on_card_delete_requested`: deletes saves + their vector stores, then the universe (folder via `shutil.rmtree`, flat db + WAL/SHM sidecars via `os.remove`). |

### Story setup / save lifecycle

| Method | Path | Params | Notes |
|---|---|---|---|
| GET | `/api/setup/questions` | `universe` | `Story_Setup` rows for the wizard. |
| POST | `/api/saves/create` | body `{universe_path, player_name, player_persona, difficulty, setup_answers}` | `create_new_save`, then **writes the turn-0 opening narrative** (first_message variant + `@tag` substitution from `setup_answers`, mirroring `ui/tabletop_view.py::_show_first_message`; previously missing entirely). |
| POST | `/api/saves/delete` | body `{universe_path, save_id}` | `axiom.savestore.delete_save` + `VectorMemory` dir cleanup (fixed in Session 2 — previously called the wrong, wrong-arity `CheckpointManager.delete_save`, a 500 on every call; see CHANGELOG). |
| POST | `/api/saves/fork` | body `{universe_path, save_id, turn_id, name}` | `axiom.saves.fork_save` (fixed — previously a partial hand-rolled copy, see CHANGELOG). |
| GET | `/api/saves/export` | `universe`, `save_id` | `axiom.saves.export_save_state` → `{toml}`. Advanced tab + CLI. |
| POST | `/api/saves/edit` | body `{universe_path, save_id, original_toml, edited_toml}` | `axiom.saves.diff_save_states` + `apply_correction`, then `EventSourcer.rebuild_state_cache`. |
| POST | `/api/creator/infer-stats` | body `{stats, world_hint?}` | **19.34.** Classify temporary profiles (heal/buildup/duration). Does not persist. |
| GET | `/api/saves/state` | `universe`, `save_id` | **19.28.** Structured materialised state: entities + stats, inventory instances, session lore, modifiers, stat defs, type catalog. |
| POST | `/api/saves/state` | body `{universe_path, save_id, entities?, inventory?, session_lore?, modifiers?}` | **19.28 / 19.33.** `apply_structured_state` (full inventory/lore/modifier replace + stat corrections). Stat keys fold onto the authored name. |
| GET | `/api/personas` | – | **Added Session 2.** `Global_Personas` from `global.db` (`axiom.config._resolve_global_db_file()`, override-aware). Settings "Personas" tab + Setup wizard picker. |
| POST | `/api/personas` | body `{personas: [{persona_id, name, description}]}` | **Added Session 2.** Replaces the whole table (mirrors `SaveGlobalPersonasTask`). |

### Gameplay session (tabletop)

All of these operate on the single `ACTIVE_SESSION` global. `history` (returned by `start`/`turn`/
`rewind`/`variant`/`regenerate`/`edit-message`) is a turn_id-tagged raw event list
(`{turn_id, event_type, payload}`, mirrors `workers/db_tasks.py::LoadSessionHistoryTask`) rather
than role/content pairs, so the client can drive per-message edit/regenerate/variant-nav controls.

| Method | Path | Params | Notes |
|---|---|---|---|
| POST | `/api/session/start` | body `{universe_path, save_id, difficulty}` | Builds `Session(...)` (+ hero LLM if `difficulty == "Companion"`); returns `build_session_snapshot()`. |
| POST | `/api/session/turn` | body `{player_input}` | `Session.take_turn()`; snapshot + `narrative_text`, `image_path`, `game_state_tag` (drives ambiance), `hardcore_death` (bool). |
| POST | `/api/session/rewind` | body `{target_turn_id}` | `Session.rewind()`; returns a snapshot. |
| POST | `/api/session/variant` | body `{turn_id, variant_index}` | **Added Session 2.** Flips the active variant of a `narrative_text` event (`EventSourcer.update_event_payload`); returns a snapshot. |
| POST | `/api/session/regenerate` | body `{turn_id}` | **Added Session 2.** `Session.regenerate_variant` (appends + activates a new variant); temperature/top_p read from `Universe_Meta` (+0.1 temp, mirrors `_on_regenerate_requested`); returns a snapshot. |
| POST | `/api/session/edit-message` | body `{event_type, turn_id, new_text}` | **Added Session 2.** `user_input`: rewind to `turn_id-1` + resubmit as a new turn. `narrative_text`: patches the active variant in place + best-effort `VectorMemory.update_turn_narrative`. Returns a snapshot (+ `narrative_text`/`image_path`/`game_state_tag` for the `user_input` case). |
| POST | `/api/session/hardcore-delete` | – | **Added Session 2.** Irrevocable Hardcore-mode teardown (`perform_hardcore_deletion`: auto-backup, WAL flush, save+assets+vector deletion); 400 if the active session isn't Hardcore. |
| GET | `/api/session/checkpoints` | – | `Session.list_checkpoints()` (rewind slider range). |
| GET | `/api/session/lore` | `query` | Mini-Dico RAG search over `ACTIVE_SESSION._vector_memory`. |
| GET | `/api/session/inventory` | – | Nested tree `{tree, names}` (`axiom.inventory.load_inventory_tree`). Old flat map is gone. |
| POST | `/api/session/inventory/move` | `{instance_id, dest_holder_kind, dest_holder_id, quantity?}` | Move/split an instance (entity / location / container). |
| GET | `/api/audio/track` | `tag` | **Added Session 2.** Random bundled ambiance track for `tag` from `assets/audio/<tag>/` (mirrors `AmbianceManager._pick_random_file`; `{file: null}` when none bundled — the app ships with none by default). |
| POST | `/api/session/turn/stream` | same body as `/turn` | **Slice 1.** SSE: `status` / `token` / `done` / `error` / `cancelled`. |
| POST | `/api/session/cancel` | – | **Slice 1.** Arms `TURN_CANCEL` for the in-flight turn. |
| POST | `/api/session/verbosity` | `{level}` | **Slice 1.** Persists `llm_verbosity` on Universe_Meta. |
| GET | `/api/session/timeline` | – | **Slice 1.** Chronicler Timeline rows for the active save. |
| POST | `/api/session/canonize` | `{preview, text?}` | **Slice 1.** Headless `axiom.canonize.canonize_story`. |
| POST | `/api/session/canonize/apply` | `{staged_dir, src_dir, universe_db}` | **Slice 1.** Apply a previewed sandbox. |
| GET | `/api/models` | – | **Slice 1.** `list_models()` on the configured backend (`{models:[]}` on failure). |
| GET/POST | `/api/universe/params` | universe query or body | **Slice 1.** Per-universe temperature / top-p / verbosity. |
| GET | `/api/universes/export` | `universe` | **Slice 2.** Download `.axiom` (`pack_universe` / `export_db_to_axiom`). |
| GET | `/api/saves/pack` | `universe`, `save_id` | **Slice 2.** Download `.axiomsave`. |
| POST | `/api/saves/unpack` | `{path, universe_path, force}` or multipart | **Slice 2.** `unpack_save`; 409 + `needs_force` on universe-key mismatch. |
| POST | `/api/saves/duplicate` | `{universe_path, save_id, name?}` | **Slice 2.** `duplicate_save`. |
| POST | `/api/saves/rename` | `{universe_path, save_id, name}` | **Slice 2.** `rename_save`. |
| POST | `/api/universes/import` | multipart `file` or `{path}` | **Slice 2.** File picker or JSON path. |
| GET | `/api/session/integrity` | – | **Slice 4.** `EventSourcer.validate_integrity`. |
| GET | `/audio/<tag>/<file>` | – (static) | **Added Session 2.** Serves the picked track (traversal-guarded, same pattern as `/assets/`). |

### Creator Studio

| Method | Path | Params | Notes |
|---|---|---|---|
| GET | `/api/creator/data` | `universe` | Full studio dataset: metadata (+ parsed `calendar_config`), `entity_types`, stats (`applies_to`), entities (+ initial stats), locations, connections, rules, scheduled events, setup questions, lore book, stat presets, and (folder-backed only) the source file list. No inventory catalog. |
| POST | `/api/creator/save` | `universe` (query) + body = full dataset | Replaces every studio table for the universe in one transaction (including `Entity_Types` / `Stat_Type_Links`); if folder-backed, re-decompiles the DB back into the source tree. |
| GET | `/api/creator/file` | `universe`, `rel_path` | Reads one source file (folder-backed only). |
| POST | `/api/creator/file` | `universe`, `rel_path` (query) + body `{content}` | Writes the file, then hot-recompiles (`axiom.compile.compile_universe(force=True)`). |
| POST | `/api/creator/convert` | body `{universe_path}` | Flat `.db` → folder-backed Universe-as-Code (`axiom.library.convert_flat_db_to_folder`). |
| POST | `/api/creator/populate` | `universe` (query) + body `{targets[], prompt, preview}` | AI-assisted content generation (`axiom.populate.POPULATE_TARGETS`); `preview=true` runs against a scratch copy (`temp_populate.db`) instead of the live DB. |
| POST | `/api/creator/populate/apply` | `universe` (query) | Promotes `temp_populate.db` over the live DB (only meaningful after a `preview=true` populate run). |

### Diagnostics & misc

| Method | Path | Params | Notes |
|---|---|---|---|
| GET | `/api/diagnostic` | `tests` (`"true"`/`"false"`) | `tools.diagnostic.run_diagnostics(run_tests=...)` + `format_report()` → `{report}`. |
| POST | `/api/audio/volume` | body `{volume}` | No-op / acked; actual volume is applied client-side to the ambiance `<audio>` elements (see `setAmbianceVolume`). |

## Bugs found and fixed

See `CHANGELOG.md` for the full running log and `TODO.md` for the checklist. Summary across both
sessions: several endpoints the frontend called but the backend never defined (`/api/universes/
delete`, `/api/diagnostic`); the entire gameplay loop (`session/start|turn|rewind`) crashing on a
nonexistent `Session` attribute; new saves starting on a blank chat (no opening narrative
injected); `saves/fork` and `saves/delete` each calling the wrong engine function (one reimplemented
a subset with raw SQL, the other called a wrong-arity Hardcore-only method that 500'd every time).
