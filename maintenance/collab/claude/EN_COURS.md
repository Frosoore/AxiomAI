# EN_COURS — côté Claude (utilisateur)

> Écrit **uniquement par Claude Code**. Le pote (Gemini) le **lit**, ne l'édite jamais.
> Tenir à jour : déclarer ici les fichiers/modules en cours de modif **avant** d'y toucher ;
> retirer la ligne une fois mergé (pas de réservation périmée).

**Branche courante :** `dev-0`
**Chantier :** Packaging pip du moteur (TICKET-009 version légère, mono-repo conservé)

## Fichiers / modules que je touche en ce moment

| Fichier / module        | Type de modif        | Depuis (date) | Note pour le pote |
|-------------------------|----------------------|---------------|-------------------|
| `pyproject.toml`        | création (racine)    | 2026-06-10    | n'emballe QUE `axiom/` ; n'affecte pas l'app. **Package PyPI publié : `axiomai-engine`** — nouvelle dep moteur ⇒ l'ajouter ici AUSSI |
| `axiom/__init__.py`     | + `__version__` + objet `help` | 2026-06-10 | additive, lazy imports inchangés. `__version__` se bump via `export_engine.py`, pas à la main |
| `export_engine.py`      | création (racine)    | 2026-06-10    | utilitaire d'export PyPI, hors package |
| `tests/test_packaging.py` | création           | 2026-06-10    | nouveau fichier de tests |
| `README.md` + `ARCHITECTURE.md` | MAJ doc (librairie PyPI + features récentes) | 2026-06-10 | ARCHITECTURE : nouvelle section « Packaging & distribution » |
| `axiom/compile.py`      | création (arbo→.db)  | 2026-06-09    | nouveau module moteur, zéro Qt |
| `axiom/decompile.py`    | création (.db→arbo)  | 2026-06-09    | nouveau module moteur, zéro Qt |
| `axiom/package.py`      | création (.axiom v2 + compat v1) | 2026-06-09 | zéro Qt ; touche le **format `.axiom`** |
| `axiom/cli/compile_cmd.py` | création (sous-cmd compile/decompile/pack/import) | 2026-06-09 | nouveau |
| `axiom/cli/main.py`     | + sous-cmd compile/decompile/pack/import | 2026-06-09 | n'ajoute que des sous-parsers |
| `requirements.txt`      | + `tomlkit`          | 2026-06-09    | nouvelle dépendance (écriture TOML) |
| `tests/test_universe_as_code.py` | création (26 tests) | 2026-06-09 | nouveau fichier de tests |
| `axiom/saves.py`        | création (éditeur de saves Phase 6) | 2026-06-09 | zéro Qt ; lit Event_Log/State_Cache/Timeline |
| `axiom/events.py`       | + `state_at` + fix replay tour 0 | 2026-06-09 | **fichier moteur partagé** — `start_turn_id=-1` dans le replay (inclut genesis). Préviens si tu touches l'event-sourcing |
| `axiom/cli/saves_cmd.py`| création (sous-cmd save-*) | 2026-06-09 | nouveau |
| `axiom/cli/play.py`     | + `_resolve_playable_db` (db/dossier/.axiom) | 2026-06-09 | `play` accepte toutes les formes d'univers |
| `tests/test_saves_editing.py` | création (15 tests) | 2026-06-09 | nouveau fichier de tests |
| `axiom/schema.py`       | + `save_id` à `Active_Modifiers` + migration | 2026-06-09 | **schéma partagé** (TICKET-024) — colonne ajoutée, FK Saves. Préviens si tu touches le schéma |
| `axiom/modifiers.py`    | filtrage par `save_id` partout | 2026-06-09 | TICKET-024 ; `apply/tick/add/_fetch` scopés save |
| `axiom/arbitrator.py`   | `_fetch_effective_stats` filtre modifiers par `save_id` | 2026-06-09 | **fichier moteur partagé** (1 requête) |
| `axiom/session.py`      | rebuild State_Cache après run Chronicler | 2026-06-09 | **temps-causal-adjacent** (TICKET-006) — 2 lignes après `chronicler.run` |
| `axiom/universe.py`     | `Universe.load` lit `universe_name` | 2026-06-09 | TICKET-023 (1 ligne) |
| `axiom/db_helpers.py`   | branche `migrate_active_modifiers_table` | 2026-06-09 | dans create_new_save/load_saves |
| `workers/hardcore_worker.py` | DELETE modifiers par `save_id` | 2026-06-09 | TICKET-024 |
| `tests/test_ticket_fixes.py` | création (9 tests) | 2026-06-09 | nouveau (006/023/024) |
| `axiom/events.py`       | + event type `manual_edit` | 2026-06-09 | **moteur partagé** — édition de save en place (append-only) |
| `axiom/cli/saves_cmd.py`| + sous-cmd `save-edit` | 2026-06-09 | édition en place |
| `ARCHITECTURE.md`       | table « non migré » MAJ | 2026-06-09 | Populate* clarifié + ligne import/export |
| `workers/db_worker.py`  | fix `save_global_personas` (dispatch manquant) | 2026-06-09 | TICKET-025 — 1 ligne |
| `tests/test_persona_global.py` | (vert via fix db_worker) | 2026-06-09 | TICKET-025 |
| `tests/test_ambiance_manager.py` | fixture QObject + approx | 2026-06-09 | TICKET-001 (ambiance) |
| `tests/test_phase6.py`  | 6 tests sync réécrits (vrais widgets) | 2026-06-09 | TICKET-001 (phase6) |
| `tests/test_llm_base.py`| 2 tests alignés sur parse résilient | 2026-06-09 | TICKET-026 |
| `axiom/dev.py`          | création (hot reload §7.7 : refresh définition in-place + watch) | 2026-06-09 | zéro Qt ; écrit dans les tables de **définition** d'un .db existant sans toucher aux tables runtime |
| `axiom/library.py`      | création (découverte d'univers : *.db plat + dossiers source) | 2026-06-09 | zéro Qt ; utilisé par le Hub via DbWorker |
| `axiom/package.py`      | + `export_db_to_axiom` (db → .axiom v2 via decompile) | 2026-06-09 | format `.axiom` (zone déclarée) |
| `axiom/cli/compile_cmd.py` | + sous-cmd `dev` ; `pack` accepte aussi un .db | 2026-06-09 | |
| `axiom/cli/main.py`     | + sous-parser `dev`     | 2026-06-09    | n'ajoute qu'un sous-parser |
| `workers/import_export_worker.py` | refonte : coquille fine sur `axiom.package` (.axiom v2) | 2026-06-09 | **format `.axiom`** (zone de collision déclarée) ; mode `import_st` inchangé |
| `workers/db_worker.py`  | `load_library` → `axiom.library.discover_universes` | 2026-06-09 | le Hub voit les univers-dossiers |
| `ui/hub_view.py`        | delete/export adaptés aux univers-dossiers | 2026-06-09 | validation GUI par l'utilisateur à prévoir |
| `tests/test_dev_hotreload.py` | création | 2026-06-09 | nouveau fichier de tests |
| `axiom/cli/play.py`     | `play <dossier>` passe par `ensure_compiled` ; saves via savestore | 2026-06-09 | refresh in-place si source modifiée (préserve les saves) |
| `axiom/package.py`      | + `unpack_universe` uniquifie la destination | 2026-06-09 | ré-import = installation fraîche, jamais d'écrasement |
| `axiom/savestore.py`    | création (§7.6 : saves séparées + .axiomsave) | 2026-06-09 | zéro Qt ; saves sous `saves/<univers>/save_<uuid>.db`, legacy embarquées toujours gérées |
| `axiom/schema.py`       | + colonne `Entities.origin` + migration | 2026-06-09 | **schéma partagé** — provenance definition/runtime, défaut 'definition'. Préviens si tu touches Entities |
| `axiom/paths.py`        | + `SAVES_DIR` / `get_saves_dir()` | 2026-06-09 | additive |
| `axiom/dev.py`          | sync origin-aware + `ensure_compiled` + fix hash | 2026-06-09 | le hot reload ne touche jamais le joueur/PNJ runtime |
| `axiom/library.py`      | + `sync_source_from_db` (TICKET-027) | 2026-06-09 | Studio → arbo texte réécrite |
| `axiom/universe.py`     | `list_saves` → savestore | 2026-06-09 | 2 lignes |
| `axiom/cli/saves_cmd.py`| save-* résolvent la save séparée ; + `save-pack`/`save-unpack` | 2026-06-09 | |
| `workers/db_tasks.py`   | origin runtime (CreatePlayer ×2) + hook sync source (Populate*/DeleteEntity) | 2026-06-09 | 1 ligne par tâche |
| `workers/db_worker.py`  | `load_saves_async`→savestore ; hook sync source (saves Studio) | 2026-06-09 | |
| `ui/setup_view.py`      | nouvelle partie → save séparée ; lancement → bonne base + resync | 2026-06-09 | **flux de lancement de partie** |
| `ui/hub_view.py`        | delete univers → supprime aussi `saves/<univers>/` | 2026-06-09 | |
| `tests/conftest.py`     | + isolation `AXIOM_DATA_DIR` par test | 2026-06-09 | aucun test n'écrit dans ~/AxiomAI |
| `tests/test_savestore.py` | création (18 tests) | 2026-06-09 | nouveau fichier |
| `axiom/package.py`      | import nommé d'après le nom DANS l'archive | 2026-06-09 | fix « universes/universe/ » |
| `ui/hub_view.py`        | dialogue export propose `<Nom>.axiom` | 2026-06-09 | |
| `axiom/savestore.py`    | + `duplicate_save` (TICKET-028) | 2026-06-09 | zéro Qt |
| `axiom/saves.py`        | + `diff_save_states` (TICKET-028) | 2026-06-09 | zéro Qt ; pur calcul de patch |
| `workers/db_tasks.py`   | fix Delete/Rename saves séparées + tâches pack/unpack/duplicate/edit | 2026-06-09 | TICKET-028 |
| `workers/db_worker.py`  | + signaux/méthodes gestion de saves | 2026-06-09 | TICKET-028 |
| `ui/setup_view.py`      | panneau gestion des saves (boutons + dialogue d'édition) | 2026-06-09 | TICKET-028, validation GUI utilisateur à prévoir |
| `database/backup_manager.py` | checkpoint WAL avant copie (backup 1 fichier) | 2026-06-09 | TICKET-028 cosmétique |
| `axiom/localization.py` | + clés EN/FR panneau saves + onglet Fichiers | 2026-06-09 | additive |
| `axiom/library.py`      | + `convert_flat_db_to_folder` (TICKET-029) | 2026-06-09 | zéro Qt ; .db plat → univers-dossier, original en .bak |
| `workers/db_tasks.py`   | + `RefreshDefinitionTask`/`ConvertFlatDbTask` | 2026-06-09 | TICKET-029 |
| `workers/db_worker.py`  | + signaux/méthodes refresh définition + conversion | 2026-06-09 | TICKET-029 |
| `ui/widgets/universe_files_tab.py` | création (onglet Fichiers du Studio) | 2026-06-09 | TICKET-029, validation GUI utilisateur à prévoir |
| `ui/creator_studio_view.py` | + onglet « Fichiers » (10e) + slots refresh/convert | 2026-06-09 | TICKET-029 |
| `tests/test_backup_manager.py` | création (3 tests) | 2026-06-09 | TICKET-028 |
| `axiom/library.py`      | + `diff_source_trees`/`apply_staged_source` (TICKET-030) | 2026-06-09 | zéro Qt |
| `axiom/prompts.py`      | + `build_canonize_prompt` (TICKET-030) | 2026-06-09 | additive (nouveau prompt) |
| `workers/db_tasks.py`   | + sandbox preview + tâches Preview/Apply/Canonize | 2026-06-09 | TICKET-030 |
| `workers/db_worker.py`  | + signaux/méthodes preview/apply/canonize | 2026-06-09 | TICKET-030 |
| `ui/widgets/populate_tab.py` | + case preview, signal 4 args | 2026-06-09 | TICKET-030 — **signature du signal `populate_requested` changée** |
| `ui/widgets/diff_preview_dialog.py` | création | 2026-06-09 | TICKET-030 |
| `ui/creator_studio_view.py` | flux preview Populate | 2026-06-09 | TICKET-030 |
| `ui/tabletop_view.py`   | + toggle « Canon auto » + bouton « Canoniser… » | 2026-06-09 | TICKET-030 — touche la top bar et `_on_turn_complete` (1 ligne) |
| `tests/test_source_preview.py` | création (10 tests) | 2026-06-09 | TICKET-030 |
| `axiom/backends/gemini.py`  | retry 429 + ralentisseur + modèle de secours | 2026-06-10 | TICKET-031 — **backend partagé** (narration/timekeeper aussi), comportement par défaut inchangé hors 429 |
| `axiom/config.py`       | + `llm_requests_per_minute` / `gemini_fallback_model` | 2026-06-10 | additive |
| `workers/db_tasks.py`   | Populate entités : commit par chunk (reprise) | 2026-06-10 | TICKET-031 |
| `ui/settings_dialog.py` | + 2 champs onglet Gemini | 2026-06-10 | TICKET-031 |
| `axiom/populate.py`     | création (migration Populate* depuis workers) | 2026-06-10 | B3 — zéro Qt, LLM injectable |
| `workers/db_tasks.py`   | Populate*Task → coquilles fines sur `axiom.populate` | 2026-06-10 | B3 — API des tâches inchangée |
| `axiom/cli/main.py` + `axiom/cli/populate_cmd.py` | + sous-commande `populate` | 2026-06-10 | B3 |
| `ARCHITECTURE.md`       | ligne « non migré » Populate* → migrée | 2026-06-10 | B3 |
| `axiom/localization.py` | + `canonical_verbosity` (TICKET-032) | 2026-06-10 | additive |
| `ui/creator_studio_view.py` | combo verbosité : canonique en itemData | 2026-06-10 | TICKET-032 |
| `ui/tabletop_view.py`   | lecture verbosité normalisée | 2026-06-10 | TICKET-032 (3 lignes) |
| `axiom/backends/base.py` | + `GenerationCancelled` + hooks on_status/cancel_event | 2026-06-10 | TICKET-033 — additive |
| `axiom/backends/gemini.py` | retry 429 : compte à rebours + attente interruptible | 2026-06-10 | TICKET-033 |
| `axiom/populate.py`     | + param `cancel` (annulation coopérative) | 2026-06-10 | TICKET-033 |
| `workers/db_tasks.py`   | + signal cancelled + registre générations actives | 2026-06-10 | TICKET-033 |
| `ui/main_window.py`     | + bouton « Annuler la génération » (barre de statut) | 2026-06-10 | TICKET-033 |
| `axiom/db_helpers.py`   | + `create_player_entity` | 2026-06-10 | B4 — additive |
| `axiom/regenerate.py` + `axiom/mini_dico.py` + `axiom/multiplayer.py` | création (portage workers) | 2026-06-10 | B4 — zéro Qt |
| `axiom/session.py`      | + méthode `regenerate_variant` | 2026-06-10 | B4 — additive |
| `workers/regenerate_worker.py` + `workers/mini_dico_worker.py` + `core/multiplayer_queue.py` | refonte en coquilles fines | 2026-06-10 | B4 — API/signaux conservés |
| `ARCHITECTURE.md`       | table « non migré » vidée | 2026-06-10 | B4 |
| `workers/chronicler_worker.py` | **supprimé** (mort, feu vert utilisateur) | 2026-06-10 | B4 |
| `ui/tabletop_hardcore.py` | fix chemin de mort (worker retiré + garde isRunning) | 2026-06-10 | B4 |

## Fichiers chauds que je m'apprête à toucher en profondeur (préviens avant)

- _(rien)_

## Fini / mergé récemment (info pour le pote)

- _(rien)_
