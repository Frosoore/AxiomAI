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

## 2026-06-09 — Édition de save en place + ARCHITECTURE.md
- **`apply_correction`/`apply_correction_file`** (`axiom/saves.py`) : corrige une save **existante**
  sans réécrire le passé — events `manual_edit` append-only (rewind préservé) pour les stats, écriture
  directe inventaire (quantity 0 = retrait) / modifiers. CLI **`save-edit`**.
- Event type **`manual_edit`** ajouté à `_apply_event` + `update_state_cache` (patron `chronicler_update`).
- `ARCHITECTURE.md` : table « non migré » mise à jour (Authoring LLM `Populate*` clarifié vs `compile.py` ;
  ligne Import/Export `.axiom` → `axiom/package.py` fait, worker à brancher + avertissement découverte Hub).
- **Tests** : +6 (`test_saves_editing` : correction stats/inventaire/modifiers, append-only vs rewind,
  CLI save-edit). Régression large : **185 verts**, startup OK.

## 2026-06-09 — Retour de test GUI utilisateur : fix nom d'import + tickets 028-030
- **Verdict utilisateur** : les parcours GUI (partie séparée, reprise, export/import, Studio→texte,
  suppression) « marchent bien ». Trois demandes consignées en tickets : **TICKET-028** (GUI de
  gestion des saves : export/import/édition/fork — le moteur existe déjà, manquent les boutons),
  **TICKET-029** (onglet « Fichiers » au Creator Studio), **TICKET-030** (options Populate UaC).
- **Bug corrigé — nom d'univers à l'import** : le dossier d'installation prenait le nom du FICHIER
  archive ; or le dialogue d'export proposait `universe.axiom` par défaut → univers installé sous
  `universes/universe/`. Fix double : `unpack_universe` lit désormais le **nom déclaré dans
  l'archive** (v2 : `universe.toml [meta].name` ; v1 : `universe_meta.json universe_name`, repli
  stem) et le dialogue d'export du Hub propose `<Nom_de_l_univers>.axiom`. Tests mis à jour
  (+ assertion v1 `Legacy_World`). Suites packaging/savestore/play vertes, startup OK.

> Décisions utilisateur en début de session : TICKET-026 → résilient confirmé (clos, zéro code) ;
> TICKET-027 → à corriger ; finir le pilier (saves séparées, tout exportable, GUI connecté).

- **`Entities.origin` (definition|runtime)** — défaut découvert en repartant du hot reload Phase 7 :
  le sync aurait **supprimé l'entité joueur** (créée en jeu par `CreatePlayerEntityTask`, absente de
  la source) et écrasé ses stats de base. Colonne `origin` + migration **amnistiante** (sur une DB
  d'avant la colonne, les entités hors-source sont requalifiées `runtime` au premier refresh, pas
  supprimées). Le sync ne gère plus que les lignes `definition` ; une source qui revendique un id
  runtime le récupère. `CreatePlayerEntityTask` (×2 copies) marque `runtime` ;
  `PopulateEntitiesTask` = authoring Studio → reste `definition`.
- **§7.6 — saves séparées** (`axiom/savestore.py`, `axiom/paths.py::SAVES_DIR`/`get_saves_dir`).
  Modèle : save db **autonome** `saves/<clé univers>/save_<uuid>.db` = schéma complet + **copie des
  tables de définition** + table `Save_Meta` (lien univers, hash définition). Avantages : `Session`
  et tout le moteur **inchangés** (un seul chemin de db) ; une save = un fichier portable ; patch
  d'univers répercuté à l'ouverture via `refresh_save_definition` (refresh in-place — journal,
  joueur, inventaire intacts ; source cassée/disparue non bloquante : la save est autonome).
  Compat : saves legacy embarquées toujours listées (`list_saves` fusionne, `storage=
  embedded|separated`) et jouables. `delete_save` efface le fichier devenu vide ;
  `delete_universe_saves` accompagne la suppression d'univers. Fix en chemin :
  `refresh_definition` n'écrit plus le hash cache quand la cible n'est pas le cache par défaut.
- **CLI** : `axiom play` crée/reprend via le savestore (resync à l'ouverture) ; `save-show/-export/
  -edit/-fork` résolvent la base réelle de la save ; `save-import` produit une save séparée
  (`new_save_container`/`finalize_save_container`). Nouveaux : **`save-pack`/`save-unpack`**.
- **Saves exportables** : `pack_save`/`unpack_save` — archive `.axiomsave` (zip `save.db` +
  `manifest.toml`). Save embarquée : extraite d'abord (copie complète définition + lignes runtime de
  la save, l'original reste). Import : refus cross-univers sans `force`, **ré-identification** du
  save_id en cas de collision (jamais d'écrasement), vector memory non transportée (décision D3).
- **GUI connecté** : `setup_view` — nouvelle partie → `create_save` (l'univers n'est plus touché),
  lancement d'une save existante → bonne base + `refresh_save_definition` ;
  `DbWorker.load_saves_async` → `list_saves` ; suppression d'univers au Hub → `delete_universe_saves` ;
  hardcore : sur save séparée, la mort efface le **fichier de save** et l'univers survit (en legacy
  embarqué, comportement historique inchangé). `Universe.list_saves` → savestore.
- **TICKET-027 résolu** — `axiom/library.py::sync_source_from_db`/`sync_source_if_any` : après
  chaque écriture de définition côté app (`save_full_universe`, `save_universe_meta`, les 7
  `Populate*Task`, `DeleteEntityTask`), l'arbo texte d'un univers-dossier est réécrite en miroir
  (decompile → copie + purge des orphelins ; `.axiom-cache/` et `.git/` protégés ; entités
  `runtime` exclues de l'export ; hash cache mis à jour → pas de recompil/refresh parasite qui
  écraserait l'édition Studio). Non bloquant : un échec de sync ne fait pas échouer la sauvegarde.
- **Tests** : `tests/test_savestore.py` (18) ; `test_dev_hotreload.py` 22→28 (origin/amnistie,
  sync Studio→source dont **worker Qt offscreen réel**, round-trip après sync) ; garde-fou global
  `conftest.py` : `AXIOM_DATA_DIR` isolé par test (plus aucune écriture possible dans `~/AxiomAI`).
  **Régression : 33/33 fichiers de tests verts**, startup OK, smoke CLI réel (nouvelle partie →
  fichier `saves/...`, reprise OK).
- **⚠ Reste à valider par l'utilisateur en GUI réelle** : parcours complet Hub → setup → partie
  (nouvelle + reprise), édition Creator Studio d'un univers-dossier (fichiers texte mis à jour),
  hardcore sur save séparée.

## 2026-06-09 — Phase 7 : finition du pilier (hot reload, rewire worker, découverte Hub)

> Objectif de session : « terminer universe as code » — tout le reste du §7 réalisable headless.

- **§7.7 Hot reload — `axiom/dev.py` + CLI `axiom dev <src> [--db] [--interval]`** :
  - `refresh_definition` : recompile la définition **in-place** dans un `.db` existant, dans une
    transaction unique (`defer_foreign_keys`), **tables runtime intactes**. Indispensable : tant que
    §7.6 (saves séparées) n'est pas fait, un `compile_universe` plein écraserait les parties en cours.
    Pour `Entities`/`Item_Definitions`/`Scheduled_Events` (enfants runtime en `ON DELETE CASCADE`),
    sync par UPDATE/INSERT/DELETE ciblés : les inventaires/modifiers/événements-tirés des lignes
    conservées survivent, ceux des lignes retirées de la source partent avec (texte = vérité).
  - `poll_once`/`watch_universe` : watch par polling de `hash_directory` (pas de dépendance watchdog).
    Une source momentanément malformée est signalée et **ne tue pas la boucle** ; pas de re-tentative
    tant que le contenu ne rechange pas (hash mémorisé). Validé en réel : boucle live, modif détectée,
    TOML cassé toléré, reprise après correction.
  - `ensure_compiled` : le chemin « rendre jouable » — no-op si cache à jour, compile si absent,
    **refresh in-place si périmé**. Branché dans `axiom/cli/play.py` (`play <dossier>`) et la
    découverte du Hub : rejouer un univers-dossier dont la source a changé ne perd plus les saves.
- **Export `.db` → `.axiom` v2** : `axiom.package.export_db_to_axiom` (decompile → pack, définition
  seule — même contrat que l'export v1). `axiom pack` accepte désormais un `.db` ou un dossier source.
- **`axiom/library.py`** (nouveau, zéro Qt) : `discover_universes` (bibliothèque = `*.db` plat legacy
  **+ dossiers source** compilés à la demande ; dossier cassé ignoré avec warning, le Hub affiche le
  reste) et `universe_root_for` (cache compilé → dossier source).
- **Ré-import sans écrasement** : `unpack_universe` uniquifie la destination (`<nom>_1`, …). Avant,
  ré-importer une archive du même nom faisait un `extractall` par-dessus l'univers installé → cache
  (et saves) écrasés silencieusement.
- **Rewire `workers/import_export_worker.py` en coquille fine** (règle ARCHITECTURE.md) :
  `_run_import` → `unpack_universe` (v1 converti, v2 dépaqueté+vérifié) ; `_run_export` →
  `pack_universe` pour un univers-dossier (l'arbo texte part telle quelle), `export_db_to_axiom`
  pour un `.db` plat. ~190 lignes de logique JSON/zip dupliquée supprimées (`_read_db`, ancien
  `_run_import`). Mode `import_st` (cartes SillyTavern) inchangé. `DbWorker.load_library` →
  `discover_universes`. `hub_view._on_card_delete_requested` : pour un univers-dossier, supprime le
  **dossier source complet** (supprimer le seul `.db` cache l'aurait fait réapparaître au refresh).
- **ARCHITECTURE.md** : ligne « Import/Export `.axiom` » retirée de la table « non migré » (migration
  faite). **TICKET-027** ouvert : Creator Studio sur un univers-dossier édite le cache, pas la source.
- **Tests** : `tests/test_dev_hotreload.py` (20 verts) — refresh (définition à jour, runtime préservé,
  cascade voulue sur entité retirée, TOML cassé sans dégât), watch (poll, arrêt, CLI), export db→.axiom
  (round-trip définition, saves non embarquées, CLI), ensure_compiled (no-op/refresh/play/discovery
  sans perte de saves), ré-import uniquifié, découverte mixte. + smoke worker Qt offscreen
  (import v1 → discovery → export v2). **Régression : 32/32 fichiers de tests verts**, startup OK.
- **⚠ Reste à valider par l'utilisateur en GUI réelle** : Hub (import v1/v2, export, delete d'un
  univers-dossier, cartes des deux formes).

## 2026-06-09 — Archivage DONE.md + santé de la suite de tests (TICKET-001/025/026)
- **Archivage** : recaps des tickets résolus (006/023/024/025) ajoutés à `maintenance/DONE.md`
  (n'avait pas été fait) ; index `PENDING.md` mis à jour (→ voir DONE.md).
- **TICKET-025** (vrai bug trouvé en investiguant le test rouge) : `DbWorker.save_global_personas`
  oubliait `self._setup_task(task)` → personas globales jamais sauvegardées. Corrigé (1 ligne).
- **TICKET-001 réellement complété** : la suite était laissée avec 3 groupes d'échecs « pré-existants ».
  Tous résolus → persona (TICKET-025), ambiance (install `pytest-qt` manquant du venv + fixture
  `QObject` + `pytest.approx`), phase6 (6 tests périmés réécrits sur de vrais widgets : API
  `_sync_stats_from_ui`/`_on_row_selected`), llm_base (2 tests alignés sur `parse_tool_call` résilient).
- **TICKET-026** ouvert : `parse_tool_call` renvoie `None` au lieu de lever `LLMParseError` sur JSON
  malformé (changement de contrat post-TICKET-001) — choix de design à valider par l'utilisateur.
- **Santé suite** : **31/31 fichiers de tests verts** (lancés fichier par fichier). Le segfault du run
  monolithique reste TICKET-008 (torch+Qt sous pytest, limite de harnais documentée).
