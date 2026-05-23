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
