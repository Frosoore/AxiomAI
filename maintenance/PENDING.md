# PENDING — tickets à étudier

## TICKET-004 — Réviser le doc d'upgrade : §5.3 Étape 3 (abstraction Qt/paths)

**Contexte :** En attaquant le Pilier 1, le constat justifiant l'Étape 3 s'est révélé erroné.

**Corrections à apporter au doc `AXIOM_AI_UPGRADE_DETAILS.md` §5.3 :**
- « `core/paths.py` doit devenir abstrait [...] paths Qt-friendly » → **FAUX** : `core/paths.py` est
  du pur stdlib (os/sys/pathlib), aucune dépendance Qt, déjà importable headless. Idem `core/logger.py`.
- La vraie limite n'est pas Qt mais que les chemins sont **codés en dur à l'import** (`~/.config/AxiomAI`,
  `~/AxiomAI`), donc non injectables par un embedder.
- Le split `EngineConfig` / `AppConfig` est plus coûteux/risqué que présenté : `AppConfig` est déjà
  100 % Python sans Qt ; le scinder **change le schéma de `settings.json`** (migration) et casse des
  points existants (l'app importe `axiom.config.GLOBAL_DB_FILE` en constante ; `test_config.py` patche
  `axiom.config._CONFIG_FILE`/`_CONFIG_DIR`).

**Décision prise (validée utilisateur) :** l'Étape 3 ne bloque pas l'Étape 4. L'injection des chemins
sera portée par l'API `Session(..., data_dir=...)` (Étape 4), qui en est le point naturel. Le split de
config est reporté/abandonné sauf besoin avéré. → On passe directement à l'Étape 4.

**Priorité :** basse (révision documentaire).

---

## TICKET-003 — Supprimer les modules engine dépréciés (post-Pilier 1)

**Contexte :** Pilier 1 (étape B1) a extrait le moteur dans le package `axiom/`. Les anciens
modules ont été copiés, et tous les imports (app + tests + debug) basculés vers `axiom.*`.
Les anciennes copies ne sont donc plus importées nulle part, mais **conservées volontairement**
pour validation. Marqueurs : `core/DEPRECATED.md`, `database/DEPRECATED.md`, `llm_engine/DEPRECATED.md`.

**Fichiers à supprimer (après confirmation) :**
- `core/` : `arbitrator.py`, `chronicler.py`, `rules_engine.py`, `time_system.py`, `config.py`, `paths.py`, `logger.py`, `localization.py`
- `database/` : `event_sourcing.py`, `checkpoint.py`, `modifier_processor.py`, `schema.py`, `presets.py`
- `llm_engine/` : `base.py`, `prompt_builder.py`, `vector_memory.py`, `universal_client.py`, `gemini_client.py`, `ollama_client.py`
- `workers/db_helpers.py`
- (+ les 3 fichiers `DEPRECATED.md` une fois la suppression faite)

**Conditions de suppression (toutes requises) :**
1. La nouvelle solution `axiom/` est au moins équivalente à l'ancienne (parité fonctionnelle).
2. L'app démarre et tourne parfaitement (run réel, pas seulement imports).
3. Aucune perte de fonctionnalité constatée.
4. Suite de tests verte sur le périmètre engine (hors échecs pré-existants déjà identifiés :
   pytest-qt absent, segfault torch+Qt sur run complet, test_persona_global, 6 tests test_phase6
   `_sync_current_form` inexistant).

**Priorité :** moyenne — à faire une fois les étapes 3-4 du Pilier 1 terminées et l'app éprouvée.

---

## TICKET-002 — State_Cache jamais mis à jour entre les tours

**Contexte :** Découvert en A3. `State_Cache` est construit une fois au load de la session (`rebuild_state_cache`), puis JAMAIS mis à jour après les tours. Le `_stats_cache` (3.3) corrige le problème CÔTÉ ARBITRATOR (états corrects d'un tour à l'autre). Mais `LoadFullGameStateTask` / `LoadStatsTask` lisent toujours depuis `State_Cache` → la sidebar montre des stats figées au moment du load, pas les stats réelles.

**Ce qui serait à faire :**
- Ajouter un UPSERT sur `State_Cache` après chaque event `stat_change`/`stat_set` dans `append_event` ou `append_events_batch`, OU
- Appeler `rebuild_state_cache` (léger si Snapshot récent) avant chaque `load_full_game_state`, OU
- Alimenter la sidebar depuis `_stats_cache` de l'Arbitrator plutôt que la DB.

**Priorité :** haute — la sidebar affiche probablement des stats en retard depuis le début du projet.

---

## TICKET-001 — Rework tests : lisibilité, couverture et organisation

**Contexte :** Audit A1-1.10. Les `debug/test_*.py` sont conservés mais hors portée pytest. Les `tests/` couvrent bien l'engine mais manquent d'explicité (noms, docstrings, output verbose) et certains cas utiles existent en double (debug/ vs tests/).

**Ce qui serait à faire :**
- Rendre les noms de tests auto-documentants (ce qu'on teste, sous quelle condition, résultat attendu)
- Migrer les `debug/test_*.py` de type `unittest.TestCase` vers `tests/` une fois complétés/nettoyés, supprimer les doublons debug/
- S'assurer que tout ce qui sera ajouté (Piliers 1–7) a une couverture pytest dès le départ
- Évaluer pytest `--verbose` / `--tb=short` comme standard de run pour lisibilité output

**Priorité :** basse — à faire après stabilisation Phase A/B.
