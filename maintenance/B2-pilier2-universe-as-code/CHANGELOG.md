# CHANGELOG — B2 · Pilier 2 : Universe-as-Code

> Mis à jour au fil du travail (une entrée par lot/session).

## 2026-06-09 — Cadrage
- Étape créée. Évaluation santé codebase : garde-fous au vert (15 passed), branche propre, à jour avec `main`.
- Constat clé : le schéma se découpe déjà proprement définition/runtime ; `axiom/compile.py` n'existe pas (terrain vierge) ; le `.axiom` v1 est un zip de JSON géré par `import_export_worker.py` (Qt) ; pas d'écrivain TOML installé.
- Décisions actées avec l'utilisateur :
  - Périmètre = **MVP cœur** (compiler + decompiler + CLI + `.axiom` v2 + tests). GUI/hot-reload/séparation saves différés.
  - Writer TOML = **`tomlkit`** (style-preserving).
  - Tout cœur du pilier vit dans `axiom/` (zéro Qt) ; intégration Creator Studio portée plus tard avec logique côté moteur.
- TODO.md rédigé. Aucune ligne de code produite à ce stade.

## 2026-06-09 — MVP cœur implémenté (Phases 0→5)
- **Phase 0** : `tomlkit>=0.13.0` ajouté à `requirements.txt` + installé dans `.venv`.
- **Phase 1 — Compiler** (`axiom/compile.py`) : `compile_universe(src_dir, output_db, force)`.
  Parse universe.toml (meta/narrative/calendar/companion/[extra] passthrough), stats, entities (+stats),
  rules, locations+connections, lore (.md + frontmatter TOML), events, setup, items. Hash directory →
  skip si inchangé. Build atomique (tmp + WAL checkpoint + rename, nettoyage sidecars). Personas
  écartés (table de la **DB globale**, hors univers).
- **Phase 2 — Decompiler** (`axiom/decompile.py`) : `decompile_universe(db, out_dir)` + `read_definition(db)`
  (lecteur normalisé partagé). Écrit l'arbo via `tomlkit`. Normalise les fins de ligne en LF, écrit un
  `.gitignore` (`.axiom-cache/`).
- **Phase 3 — CLI** : `axiom compile` / `decompile` (+ `pack` / `import`) câblés dans `axiom/cli/main.py`
  via `axiom/cli/compile_cmd.py`.
- **Phase 4 — Packaging** (`axiom/package.py`) : `pack_universe` (zip arbo + cache embarqué),
  `unpack_universe` (v2 : hash check → réutilise/recompile ; v1 : JSON → .db → decompile → recompile),
  `detect_format`. **Tout côté moteur, zéro Qt.**
- **Phase 5 — Tests** (`tests/test_universe_as_code.py`, 21 tests) : compile, cache (skip/force/source-change),
  round-trip source↔source et db↔db, packaging v2, compat v1, CLI. **21/21 verts.**
- **Validation réelle** : round-trip sur `~/AxiomAI/universes/ST_Aglae.db` **100% lossless** (modulo
  normalisation LF, voulue). End-to-end CLI decompile→compile→pack→import OK.
- **Garde-fous** : `test_engine_headless` + `test_cli_play` + large sous-ensemble moteur (124 tests) verts,
  `debug/startup_check.py` OK.
- **Bug repéré** : `Universe.load` lit `name` au lieu de `universe_name` → consigné en **TICKET-023**.
- **Reste (différé, cf. TODO)** : rewire du worker Qt `import_export_worker.py` vers `axiom.package`
  (coquille fine), Creator Studio, hot reload `axiom dev`, séparation des saves (§7.6), migration `Populate*`.

## 2026-06-09 — `axiom play` étendu + saves éditables (design)
- **Vérifié** : `axiom play` fonctionne sur un univers compilé (charge, `first_message`, résolution
  joueur, boucle, `/quit`). « aucune stat matérialisée » sur save fraîche = comportement normal (les
  stats se matérialisent au 1er tour, identique à l'ancien système).
- **Amélioration vs ancien système** : `axiom/cli/play.py::_resolve_playable_db` — `play` accepte
  désormais un **`.db`**, un **dossier source** (compilé à la volée) ou une **archive `.axiom` v1/v2**
  (dépaquetée+compilée). Avant, `play` passait le chemin brut à SQLite → `.axiom`/dossier cassés
  malgré l'aide annonçant `.axiom/.db`. Chemin `.db` inchangé (zéro régression).
- **Tests** : +5 tests (résolution db/source/.axiom/absent + bout-en-bout `Session` réelle sur .db
  compilé). Suite UaC = **26 tests verts**.
- **Saves éditables** : feature demandée consignée en **Phase 6 (proposée)** du TODO avec proposition
  de format `save.toml` (état déclaratif LLM-friendly), API moteur `axiom/saves.py`, CLI, et les
  3 décisions à trancher (modèle / emplacement / vector). Pas encore implémenté (design à valider).

## 2026-06-09 — Phase 6 : éditeur de saves (1er jet)
- Décisions actées avec l'utilisateur : **D1** garder le journal (édition par découpe/fork +
  events de correction, pas d'édition de dérivés) ; **D2** dossier `saves/` séparé = cible, différé ;
  **D3** mémoire vectorielle vide à l'import. Sélecteur **tour + minute** dès maintenant (choix user).
- **`axiom/saves.py`** (zéro Qt) : `resolve_point` (tour|minute via `Timeline`), `materialize_state`
  (replay → état effectif base⊕rejoué, + inventaire + temps), `export_save_state`/`import_save_state`
  (`save_state.toml` ⇄ nouvelle save semée d'events genesis au tour 0), `fork_save` (journal tronqué
  à un point, source intacte).
- **`axiom/events.py`** : ajout `EventSourcer.state_at` (replay pur réutilisé par `take_snapshot`).
  **Correctif** : le replay incluait à tort le défaut `start_turn_id=0` de `get_events` (exclut le
  tour 0) → passé à `-1` pour matérialiser les events genesis. Validé : 176 tests sensibles verts.
- **CLI** : `save-show`, `save-export`, `save-import`, `save-fork` (`axiom/cli/saves_cmd.py`),
  acceptent l'univers sous toute forme (.db/dossier/.axiom).
- **Tests** : `tests/test_saves_editing.py` (14 verts) — résolution tour/minute, matérialisation,
  export↔import, save importée **jouable** via `Session`, import à la main (humain/LLM), FK invalide,
  fork + rewind toujours fonctionnel. End-to-end CLI OK. `startup_check` OK.
- **Bugs repérés** : **TICKET-024** (`Active_Modifiers` sans `save_id` → modifiers globaux, exclus du
  format de save pour l'instant).

## 2026-06-09 — Résolution TICKET-006 / 023 / 024
- **TICKET-006** (`chronicler_update` jamais matérialisé) : `EventSourcer._apply_event` +
  `update_state_cache` gèrent `chronicler_update` (payload `delta|value`, provenance conservée) ;
  `Session.take_turn` rematérialise `State_Cache` après le run du Chronicler.
- **TICKET-023** (`Universe.load`) : lit `universe_name` en priorité (repli `name`/stem). Validé sur
  `ST_Aglae.db` réel.
- **TICKET-024** (`Active_Modifiers` sans `save_id`) : colonne `save_id` + FK + migration
  (`migrate_active_modifiers_table`, branchée `create_new_save`/`load_saves`) + filtrage par save
  dans `modifiers.py`, `arbitrator.py`, `hardcore_worker.py` ; modifiers **réintégrés** à l'éditeur
  de saves.
- **Fichiers moteur partagés touchés** : `events.py`, `modifiers.py`, `arbitrator.py`, `session.py`,
  `schema.py`, `db_helpers.py`, `universe.py`, `workers/hardcore_worker.py` (déclarés dans EN_COURS).
- **Tests** : `tests/test_ticket_fixes.py` (9) + ajouts `test_saves_editing` (modifiers round-trip) +
  `test_modifier_processor` adapté (colonne `save_id`). **Régression : 245 tests verts**, startup OK.
