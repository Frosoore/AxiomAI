# CHANGELOG — B1 Pilier 1

## Session 2026-05-23
- Audit initial (grep) : engine déjà quasi headless, seule fuite réelle = arbitrator → workers/db_helpers.
- Création du dossier d'étape + TODO.
- **Étape 1 terminée** : package `axiom/` créé par copie de 21 modules (engine + backends).
  - Dépendances non listées au doc découvertes et incluses : `axiom/localization.py` (tr/fmt_num),
    `axiom/presets.py`, `axiom/db_helpers.py` (résout la fuite arbitrator → workers).
  - `prompt_builder.py` copié en un seul `axiom/prompts.py` (split reporté).
  - Imports internes réécrits (top-level + lazy indentés + exemples docstrings) vers `axiom.*`.
  - Validation : 19/19 modules importent, `PySide6 chargé: False`. `gemini` échoue sur
    `google.genai` manquant — identique à l'original, dépendance optionnelle de l'env, hors scope.
  - App existante intacte (aucun fichier de core/database/llm_engine/ui/workers modifié).
  - `pyproject.toml` reporté à l'étape de split physique.
- **Étape 2 (bascule app) terminée** : imports de ui/, workers/, main.py, core/multiplayer_queue.py
  réécrits vers `axiom.*`. `core/__init__.py` vidé de ses ré-exports (arbitrator/rules/tr) — supprime
  au passage le cycle d'import à l'origine du hotfix A5.
  - Validation : 25/25 modules applicatifs importent via axiom.*, 115 tests engine verts (venv).
  - Constat env (pré-existant, hors scope) : pytest-qt absent (qtbot), segfault torch+Qt sur run
    complet, échec test_persona_global — tous contre les anciens modules non modifiés.
  - Anciennes copies dans core/database/llm_engine/workers désormais mortes (réf. uniquement par
    tests/ et debug/). Suppression + réécriture imports tests : EN ATTENTE de feu vert.
- **Tests + debug basculés vers axiom.*** : from-imports + cibles `patch("...")` par chaîne
  (config._CONFIG_FILE/_CONFIG_DIR, gemini.genai.Client, memory.SentenceTransformer...) + checks
  d'import de debug/startup_check.py. Suite engine : **314 passés**, 6 échecs PRÉ-EXISTANTS
  (test_phase6 `_sync_current_form` — méthode inexistante, sans rapport).
- **Dépréciation (sans suppression, choix utilisateur)** : ajout de `core/DEPRECATED.md`,
  `database/DEPRECATED.md`, `llm_engine/DEPRECATED.md` (tables de correspondance ancien→nouveau)
  et ouverture de **TICKET-003** (suppression conditionnée à parité fonctionnelle + run réel OK +
  zéro régression).
- **Étape 3 (abstraction Qt/paths) : reportée/absorbée** — constat doc erroné (paths déjà headless),
  split config risqué pour la persistance. **TICKET-004** ouvert (révision du doc). Décision validée :
  ne bloque pas l'Étape 4 ; l'injection des chemins passe par `Session(data_dir=...)`.
- **Étape 4 (API publique) terminée** :
  - `axiom/universe.py` — `Universe.load(path)` (lit `Universe_Meta` : nom + system_prompt), `list_saves()`.
  - `axiom/session.py` — `Session(universe_path, save_id, *, llm, vector_memory=None, data_dir=None, mode)`
    composant Arbitrator + EventSourcer + CheckpointManager + VectorMemory. Méthodes : `take_turn`
    (reconstruit l'historique depuis l'Event_Log, stream via `on_token`, synchrone), `rewind`,
    `list_checkpoints`, `current_stats` (rebuild State_Cache), propriété `turn_id`.
  - `axiom/__init__.py` — exposition paresseuse `from axiom import Session, Universe` (`__getattr__`,
    garde `import axiom` léger : pas de chromadb tant qu'on n'instancie pas).
  - `tests/test_session.py` — 5 tests verts (Universe.load, construction, état neuf à turn 0,
    mapping user_input/narrative_text → user/assistant, variante active).
  - Smoke test hors-pytest : Session/Universe OK contre vraie base SQLite, `PySide6 chargé: False`.
  - Non régression : sous-ensemble engine (test_arbitrator/event_sourcing/checkpoint/config) = 68 passés.
  - REPORTÉ : réécriture de `NarrativeWorker` en wrapper de `Session` (refacto app à risque) + CLI `axiom/cli/`.

- **Étape 5 (injection des chemins, Problème P) terminée** — cf. doc §5.3-bis :
  - `axiom/paths.py` : ajout de `configure(data_dir=, config_dir=)`, `reset()`, getters paresseux
    (`get_vector_dir`, `get_log_dir`, `get_config_dir`, `get_settings_file`, `get_global_db_file`,
    `has_config_override`) + support des vars d'env `AXIOM_DATA_DIR` / `AXIOM_CONFIG_DIR`. Les
    constantes existantes restent les défauts machine-globaux ; la résolution n'est plus gelée.
  - `axiom/logger.py` : file handler résolu paresseusement via `paths.get_log_dir()` + nouvelle
    fonction `reconfigure(log_dir=None)` qui re-pointe le handler. Emplacement par défaut inchangé
    (racine CACHE_DIR, comportement legacy).
  - `axiom/config.py` : `load_config`/`save_config` passent par `_resolve_config_file/dir/global_db`
    qui honorent un override config si présent, sinon les globals `_CONFIG_FILE`/`_CONFIG_DIR`
    (patchés par les tests). Hybride acté : config machine-globale par défaut.
  - `axiom/session.py` : avec `data_dir`, logs → `<data_dir>/logs` (reconfigure) et vector →
    `<data_dir>/vector/<save_id>` ; sans, getters (honorent env). Plus de recalcul ad hoc.
  - App : `ui/tabletop_view.py`, `ui/tabletop_hardcore.py`, `workers/db_tasks.py` routés vers
    `paths.get_vector_dir()` (honorent l'override/env). GUI inchangée en l'absence d'override.
  - Tests : `tests/test_session.py` +2 (sandbox vector+logs sous data_dir ; config machine-globale
    sans override). Résultats : test_session 7/7, test_config 14/14, engine subset 54/54.
  - Smoke headless : défaut inchangé, env overrides effectifs, `PySide6 chargé: False`.
  - Limites notées (TODO) : override `data_dir` process-global (logger singleton) ; `UNIVERSES_DIR`
    non routé (source d'univers, hors périmètre données par-partie).
  - **Reste du Pilier 1** : Étape 6 (parité `Session` : héros Companion + historique), Étape 7
    (adoption worker, run-testé), Étape 8 (CLI).

## Session 2026-05-24
- **Étape 6 (parité `Session`, Problème U pré-requis) terminée** — sans bascule (app inchangée) :
  - `axiom/db_helpers.py` : `load_active_entities(db_path)` — entités actives + stats, forme identique
    à `db_worker.load_entities_and_rules`. `Session` charge donc les entités lui-même (l'UI les
    fournissait au worker).
  - `axiom/session.py` : décision du héros Companion portée depuis `NarrativeWorker`
    (`_get_hero_id_from_metadata`, `_find_hero_entity` avec replis id→'hero'→nom→NPC, `_get_hero_decision`).
    Backend héros injectable (`hero_llm=`), défaut = build local `extraction_model` (parité worker).
    `take_turn` calcule `hero_action` en mode Companion s'il n'est pas fourni explicitement.
  - Hooks de progression headless `on_status` / `on_hero_decision` sur `take_turn` (remplacent les
    signaux Qt) + helper `_emit`. Ordre des statuts aligné sur le worker (Generating→Consulting→Hero→Ready).
  - Source d'historique : **Event_Log retenu comme canonique** (cf. DOC.md) ; le worker s'y ralliera
    en Étape 7.
  - Tests : `tests/test_session.py` +5 de parité (forme entités, résolution héros méta + 3 replis,
    décision via hero_llm injecté/strip/prompt, None si pas de héros). **12/12 verts.**
  - Non-régression : arbitrator + event_sourcing + checkpoint + config = **72/72**. Smoke headless
    `PySide6 chargé: False`.
  - **Reste** : Étape 7 (NarrativeWorker → coquille de threading autour de `Session`, run-testé),
    Étape 8 (CLI).

- **Étape 7 (adoption worker, Problème U) — code terminé, run réel à valider par l'utilisateur** :
  - `workers/narrative_worker.py` réécrit en pure coquille de threading : `__init__(session, action,
    *, temperature, top_p, verbosity)`, `run()` délègue à `Session.take_turn` et mappe
    on_token/on_status/on_hero_decision → signaux Qt. **Contrat de signaux inchangé** (la GUI garde
    ses connexions). Gestion d'erreur (LLMConnectionError / générique) identique.
  - `ui/tabletop_view.py` : `_on_send_message` construit une `Session` (db_path, save_id, llm,
    vector_memory, mode) au lieu de `ArbitratorEngine` + worker à gros constructeur ; `reload_llm`
    perd la ligne morte `_narrative_worker.llm`. Compteur de tour / temps / liste UI inchangés.
  - Décisions vérifiées (pas de supposition) : `turn_id` reste cohérent (Session reconstruite par tour
    s'ancre sur `get_max_turn_id`, qui avance d'1/envoi car `user_input` est écrit même sur échec) ;
    `global_lore`/`current_time` du worker étaient déjà morts ; un seul site construit le worker ;
    régénération = `RegenerateWorker` distinct, hors scope.
  - Changement de comportement assumé (Event_Log canonique) : le message courant n'apparaît plus en
    double dans le prompt (l'ancien worker mappait la liste UI qui le contenait déjà). Documenté DOC.md.
  - Tests : `tests/test_narrative_worker.py` (3, délégation + erreurs). Suite complète **355 passed**,
    7 failed + 5 errors = set pré-existant connu. `tabletop_view` importe OK.
  - **⏳ Run réel GUI+LLM** non faisable dans cet env (pas de display, segfault torch+Qt connu) →
    checklist de validation utilisateur dans TODO.md.
  - **Reste** : Étape 8 (CLI sur `Session`).

## Session 2026-05-24 (bis) — validation live headless de l'Étape 7
- Ajout d'un harnais `debug/run_step7_live.py` : reproduit le chemin de tour de l'app SANS Qt
  (construit une `Session` comme `tabletop_view._on_send_message`, exécute le vrai
  `NarrativeWorker.run()` synchrone en capturant les signaux), tape sur le backend réel (Gemini),
  VectorMemory remplacée par un stub léger.
- Le harnais a **validé le câblage Étape 7** (worker→Session→arbitrator→prompt→backend, reconstruction
  d'historique Event_Log, avance du `turn_id`, gestion d'erreur sans crash) et **révélé 2 bugs Gemini
  PRÉ-EXISTANTS** (indépendants des étapes 6/7) → corrigés, cf. **TICKET-007** :
  1. `extraction_model` ("llama3.1:8b") envoyé tel quel à l'API Gemini → 404. Fix : helper
     `config.resolve_extraction_model(cfg)` (gemini→`gemini_model`, sinon `extraction_model`), adopté
     par `session._get_hero_decision` + les 7 appels de `workers/db_tasks.py`.
  2. >5 `stop_sequences` envoyés à Gemini (l'arbitrator en construit 6) → 400 INVALID_ARGUMENT.
     Fix : `gemini._clamp_stop_sequences` (plafond API = 5) dans `complete()` et `stream_tokens()`.
- Après fix : la requête est bien formée (400/404 disparus) ; reste un **429 RESOURCE_EXHAUSTED**
  (quota free-tier épuisé côté compte Gemini, `limit: 0`) — **pas un bug de code**. Le pipeline est
  donc prouvé correct jusqu'à l'appel LLM réel ; la génération narrative effective reste à confirmer
  par l'utilisateur quand son quota Gemini le permettra (ou via Ollama, indispo ici : carte AMD).
- Tests ajoutés (vérifiables sans quota) : `test_gemini_client` +2 (clamp), `test_config` +2
  (resolve_extraction_model). Suite complète **359 passed**, 7 failed + 5 errors = set pré-existant connu.
- Nettoyage : sauvegardes de test créées dans `~/AxiomAI/universes/Myria.db` supprimées (univers
  restauré à 0 save / 0 event, son état d'origine).

## Session 2026-06-04 — segfault torch+Qt au 1er tour (TICKET-008)
- Run réel GUI utilisateur (import carte SillyTavern → envoi message) → `Erreur de segmentation`.
- Reproduit en **headless avec Qt** (`QT_QPA_PLATFORM=offscreen`) ; backtrace `faulthandler` :
  le 1er encode du modèle d'embedding, exécuté sur un QThread, importe `torch._dynamo` → `triton`
  qui `dlopen()` `libtriton.so` **hors thread principal** sous Qt → SIGSEGV natif. **Pré-existant**
  (threading vectoriel identique avant/après l'étape 7 ; vérifié sur l'ancien worker à HEAD).
- Le cross-thread torch/chromadb **sans** Qt ne crashe pas (prouvé) → c'est bien l'interaction Qt.
- Fix : `axiom/memory.py::preload_embedding_runtime()` appelé sur le **thread principal** au
  démarrage (`main.py`), force le `dlopen` triton sur le main thread ; usage cross-thread ensuite OK.
- Test : `tests/test_vector_threading.py` (+ `tests/_vector_qthread_scenario.py`) rejoue le threading
  d'un tour GUI en sous-process ; `nopreload`→139 (segfault), `preload`→0. À dents, vérifié.
- ⏳ Reste : confirmation en **GUI réelle** par l'utilisateur (le headless ne couvre pas le rendu Qt).
  Détail complet : **TICKET-008** (PENDING.md).
- **Validé par l'utilisateur** : après bascule du modèle Gemini sur `gemini-2.5-flash-lite` (le seul
  avec du quota free-tier sur sa clé ; `gemini-2.0-flash` = `limit: 0`, cf. notes), le tour GUI génère
  bien la narration. Plus de crash, plus d'erreur LLM. **L'étape 7 est confirmée en run réel.**

## Session 2026-06-04 (bis) — Étape 8 : CLI `axiom play` ✅
- Package `axiom/cli/` créé : `main.py` (dispatch argparse, point d'entrée `axiom.cli:main` prêt pour
  le futur console_script `axiom`), `__main__.py` (`python -m axiom.cli`), `play.py` (commande `play`).
- `play.py` : boucle de jeu terminal posée sur l'API publique `Session` (zéro Qt). Découpé en
  `run_play` (câblage : résolution univers [chemin direct ou ~/AxiomAI/universes, extension optionnelle],
  choix de save `--save`/`--new`/reprise auto de la plus récente, LLM, mode), `play_loop` (REPL,
  read/out/err injectables → testable sans stdin/LLM) et `_handle_command` (`/help` `/stats`
  `/checkpoints` `/rewind` `/quit`). Streaming via `on_token`, statuts via `on_status`→stderr, et les
  erreurs de tour (LLMConnectionError/générique) sont rattrapées sans casser la boucle.
- Pas de couplage aux internes : le CLI n'importe ni `prompts` ni `memory` directement → le split
  physique / le split de `prompts.py` / le passage de `memory` en Protocol ne le réécriront pas.
- Tests : `tests/test_cli_play.py` (14, fausse `Session`, zéro Qt/LLM/stdin). Import headless
  `PySide6 chargé: False`. Smoke e2e contre copie jetable d'un univers réel (Universe.load →
  create_new_save → Session avec vraie VectorMemory → play_loop, exit 0).
- **Pilier 1 terminé côté fonctionnel** : moteur entièrement pilotable hors Qt (GUI = un frontend
  parmi GUI/CLI). Reste le **packaging** (split physique en `axiom-engine/` + `pyproject.toml`
  pip-installable) — non ordonnancé : **TICKET-009** ouvert (dépend de TICKET-003).
