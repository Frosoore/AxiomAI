# TODO — B1 Pilier 1 : Extraction `axiom-engine` headless (§5)

Objectif : isoler le moteur (Arbitrator, Chronicler, EventSourcing, RulesEngine,
ModifierProcessor, VectorMemory, prompts, time) dans un package `axiom/`
sans aucune dépendance Qt.

Constat vérifié (grep, 2026-05-23) :
- Modules engine déjà quasi sans Qt (seul `core/multiplayer_queue.py` importe PySide6 — HORS migration).
- `core/paths.py` et `core/logger.py` sont du pur stdlib (le doc se trompe sur « paths Qt-friendly »).
- Seule vraie fuite : `core/arbitrator.py` importe `get_current_time` / `get_time_of_day_context` depuis `workers/db_helpers.py`.
- 22 fichiers de `ui/` + `workers/` importent l'engine (périmètre Étape 2).

## Étape 1 — Créer le package `axiom/` (COPIE, app intacte) ✅
- [x] `axiom/__init__.py`
- [x] `axiom/schema.py` ← `database/schema.py`
- [x] `axiom/paths.py` ← `core/paths.py`
- [x] `axiom/logger.py` ← `core/logger.py`
- [x] `axiom/events.py` ← `database/event_sourcing.py`
- [x] `axiom/checkpoint.py` ← `database/checkpoint.py`
- [x] `axiom/modifiers.py` ← `database/modifier_processor.py`
- [x] `axiom/rules.py` ← `core/rules_engine.py`
- [x] `axiom/time_system.py` ← `core/time_system.py`
- [x] `axiom/db_helpers.py` ← `workers/db_helpers.py` (résout la fuite arbitrator)
- [x] `axiom/localization.py` ← `core/localization.py` (dép découverte : tr/fmt_num)
- [x] `axiom/presets.py` ← `database/presets.py` (dép découverte : db_helpers/config)
- [x] `axiom/backends/base.py` ← `llm_engine/base.py`
- [x] `axiom/backends/universal.py` ← `llm_engine/universal_client.py`
- [x] `axiom/backends/gemini.py` ← `llm_engine/gemini_client.py`
- [x] `axiom/backends/ollama.py` ← `llm_engine/ollama_client.py`
- [x] `axiom/backends/__init__.py`
- [x] `axiom/memory.py` ← `llm_engine/vector_memory.py`
- [x] `axiom/prompts.py` ← `llm_engine/prompt_builder.py` (split en sous-modules : étape ultérieure)
- [x] `axiom/config.py` ← `core/config.py`
- [x] `axiom/arbitrator.py` ← `core/arbitrator.py`
- [x] `axiom/chronicler.py` ← `core/chronicler.py`
- [x] Réécrire les imports internes (top-level + lazy/indentés) → `axiom.*`
- [~] `pyproject.toml` du package — REPORTÉ à l'étape de split physique (dir racine dédié)
- [x] Vérif : 19/19 modules importent sans Qt (`PySide6 chargé: False`)
- [x] Vérif : aucun `from core|database|workers|llm_engine` résiduel dans `axiom/`

## Étape 2 — Réécrire les imports de l'app (ui/ + workers/) vers `axiom.*`
- [x] Réécriture des imports dans ui/, workers/, main.py, core/multiplayer_queue.py
- [x] `core/__init__.py` vidé de ses ré-exports morts (supprime aussi le cycle d'import du hotfix A5)
- [x] Validation : 25/25 modules applicatifs importent via axiom.*, 115 tests engine passent
- [x] Réécriture des imports de tests/ et debug/ vers axiom.* (from-imports + cibles patch/string)
- [x] Tests engine relancés contre axiom.* : **314 passés** / 6 échecs pré-existants (test_phase6 `_sync_current_form`)
- [x] Suppression NON faite (choix utilisateur) → README `DEPRECATED.md` dans core/, database/, llm_engine/ + TICKET-003
- [ ] (différé) Suppression effective des anciens modules : voir TICKET-003 (conditions de validation)

Note env : pytest-qt absent → tests Qt (qtbot) en erreur de setup ; segfault torch+Qt sur run
complet ; échec test_persona_global. Tous PRÉ-EXISTANTS (tests tournent contre les anciens modules
non modifiés), sans rapport avec la bascule.

## Étape 3 — Abstraction des fuites Qt / paths — REPORTÉE / ABSORBÉE PAR L'ÉTAPE 4
- Constat : doc erroné (paths déjà headless) ; split config = risque persistance. Voir TICKET-004.
- Décision (validée) : ne bloque pas l'Étape 4 ; l'injection des chemins passera par `Session(data_dir=...)`.
- [~] Split EngineConfig/AppConfig : abandonné sauf besoin avéré (settings.json inchangé).

## Étape 4 — API publique `Session`
- [x] `axiom/session.py` : `Session.take_turn / rewind / list_checkpoints / current_stats / turn_id`
- [x] `axiom/universe.py` : `Universe.load`, `list_saves`
- [x] Exposition paresseuse `from axiom import Session, Universe` (`__getattr__`, import léger)
- [x] `tests/test_session.py` : 5 tests (Universe.load, construction, état neuf, mapping historique, variante active) — verts
- [x] Smoke test headless hors-pytest : Session/Universe OK contre vraie base, `PySide6 chargé: False`
- [ ] (suite, refacto app à part) `NarrativeWorker` réécrit en wrapper threading autour de `Session` — voir note
- [ ] (optionnel/plus tard) `axiom/cli/` : `play`, `compile`, `test_runner`

Note : l'app pilote encore l'engine en direct (ArbitratorEngine + NarrativeWorker), ce qui marche.
Faire adopter `Session` par le worker est une refacto applicative à risque de régression → reportée
(hors « no refacto hors scope »), à traiter en étape dédiée quand on voudra le mode CLI.

## Étape 5 — Injection des chemins (Problème P) — cf. doc §5.3-bis
Objectif : que la racine de données soit injectable (vector + logs), sans geler les
chemins à l'import. Hybride config acté : `settings.json`/`global.db` machine-globaux
par défaut, surcharge explicite (`config_dir`) pour isolement total. App GUI inchangée.

Constat vérifié (grep/lecture, 2026-05-23) :
- `paths.py` calcule CONFIG_DIR/CACHE_DIR/DATA_DIR + dérivés une fois à l'import.
- `config.py:20-25` capture CONFIG_DIR/SETTINGS_FILE/GLOBAL_DB_FILE à l'import ; `logger.py:12-14`
  capture CACHE_DIR et crée le singleton à l'import (`logger.py:53`).
- `logger.py` écrit en fait à la RACINE de CACHE_DIR (`_LOG_DIR = CACHE_DIR`), pas dans `LOG_DIR`.
- Lecteurs directs de VECTOR_DIR (à router) : `ui/tabletop_view.py:290-291`,
  `ui/tabletop_hardcore.py:94-96`, `workers/db_tasks.py:225-226`.
- `tests/test_config.py` patche `axiom.config._CONFIG_FILE`/`_CONFIG_DIR` → NE PAS casser.

- [x] `paths.py` : `configure(data_dir=, config_dir=)` + getters paresseux (`get_vector_dir`,
      `get_log_dir`, `get_config_dir`, `get_settings_file`, `get_global_db_file`, `has_config_override`)
      + vars d'env `AXIOM_DATA_DIR`/`AXIOM_CONFIG_DIR` + `reset()`. Constantes conservées (défauts).
- [x] `logger.py` : résolution paresseuse via `get_log_dir()` + `reconfigure(log_dir=None)`
      (re-pointe le file handler). Défaut inchangé (CACHE_DIR).
- [x] `config.py` : load/save passent par `_resolve_config_file/dir/global_db` (honorent l'override
      config, sinon les globals `_CONFIG_FILE`/`_CONFIG_DIR` patchés par les tests). Comportement défaut intact.
- [x] `session.py` : si `data_dir` → logs sous `<data_dir>/logs` (reconfigure logger) + vector sous
      `<data_dir>/vector/<save_id>` ; sinon getters (honorent env). Plus de recalcul ad hoc.
- [x] App : router les 3 lecteurs VECTOR_DIR vers `paths.get_vector_dir()` (honore env override).
- [x] `tests/test_session.py` : 2 tests (sandbox vector+logs sous data_dir ; config reste
      machine-globale sans override). Verts. Non-régression : test_config (21) + engine subset (54) OK.

Limites connues (notées pour la suite) :
- `paths.configure(data_dir=)` est un override **process-global** ; deux Sessions avec data_dir
  différents dans le même process partageraient les logs (le logger est un singleton). Session
  calcule son vector localement (pas d'état global), seul le logger est re-pointé. OK pour GUI/CLI/tests.
- `UNIVERSES_DIR` (bibliothèque d'univers, `ui/hub_view.py`) NON routé : c'est la source d'univers
  côté utilisateur (analogue à `universe_path`), hors périmètre « données par-partie ».

## Étape 6 — Parité de `Session` (pré-requis Problème U) — cf. doc §5.3-bis ✅
Objectif : faire absorber par `Session` ce qui lui manquait vs `NarrativeWorker`, SANS bascule
(l'app pilote toujours l'engine en direct). Risque moyen, isolé aux tests.

Constat vérifié (lecture, 2026-05-24) :
- Écart héros Companion : `take_turn` recevait `hero_action`/`hero_entity_id` déjà calculés sans
  jamais les décider, alors que le worker fait `_get_hero_id_from_metadata`/`_find_hero_entity`/
  `_get_hero_decision` (`narrative_worker.py:97-194`) à partir de `self._entities` (fourni par l'UI).
- Source d'historique : worker mappe la liste UI ; `Session._load_history` reconstruit depuis l'Event_Log.
- `build_llm_from_config(cfg, model_override=cfg.extraction_model)` = modèle local forcé pour le héros.

- [x] `axiom/db_helpers.py` : `load_active_entities(db_path)` (mêmes colonnes + stats que
      `db_worker.load_entities_and_rules`) → `Session` charge les entités lui-même (plus de dépendance UI).
- [x] `axiom/session.py` : décision héros portée — `_get_entities` (cache), `_get_hero_id_from_metadata`,
      `_find_hero_entity` (id méta → repli 'hero' → nom → premier NPC), `_get_hero_decision`
      (hero_llm injectable, défaut = build local via `extraction_model`). En mode Companion, `take_turn`
      calcule `hero_action` si non fourni (override explicite court-circuite).
- [x] Hooks de progression headless : `on_status` / `on_hero_decision` sur `take_turn` (remplacent les
      signaux Qt `status_update` / `hero_decision_received`). Helper module `_emit`.
- [x] Source d'historique : **Event_Log canonique** (décision actée, cf. DOC.md) — `Session` y reste ;
      à l'adoption (Étape 7) le worker déléguera et héritera de cette source.
- [x] `tests/test_session.py` +5 tests de parité (shape entités, résolution héros par méta + 3 replis,
      décision via hero_llm injecté + strip + contenu prompt, None si pas de héros). 12/12 verts.
- [x] Non-régression : arbitrator+event_sourcing+checkpoint+config = 72/72. Smoke headless `PySide6=False`.

Reste du Pilier 1 : Étape 7 (adoption worker, run-testé), Étape 8 (CLI).
