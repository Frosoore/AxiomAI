# CHANGELOG — Modèles mentaux (Hindsight §7.8)

## 2026-06-20 — Port des modèles mentaux (TICKET-082 partiel)

Dernière feature Hindsight retenue (décision user : **modèles mentaux seuls** ;
directives §7.9 et extraction temporelle §7.5 laissées fermées, redondantes / peu
pertinentes pour un jeu en temps de jeu). Un **modèle mental** = une fiche
synthétique vivante par sujet (personnage, ou `""` pour le monde), au sommet de la
hiérarchie de rappel : modèles → croyances → faits → chunks.

### Moteur
- **Schéma** : table `Mental_Models` (`model_id, save_id, subject, summary, sources,
  created/updated_turn_id, stale`, `UNIQUE(save_id, subject)`) + index
  `idx_mental_models_save_turn` + `ensure_mental_models_table` (auto-migration) ;
  ajoutée aux listes DDL / `EXPECTED_TABLES`.
- **`axiom/mental_models.py`** (stockage déterministe) : `upsert_mental_model`
  (un modèle par sujet, UPDATE en place, `created_turn_id` préservé), `get_mental_models`
  (borné `max_turn_id`, filtre `subject`, `LIMIT` SQL sans filtre), `count_mental_models`,
  `stale_subjects` (pour re-générer après rewind), `rollback_mental_models`
  (supprime les modèles créés après la cible, marque les survivants `stale`).
- **`axiom/reflect.py`** (couche LLM, graceful → "") : `reflect(llm, subject, beliefs)`
  écrit un profil 2-4 phrases à partir des croyances (seuil `MIN_BELIEFS_FOR_MODEL=3`,
  cap `_MAX_BELIEFS_PER_REFLECT=40`) ; `affected_subjects(actions)` = sujets touchés
  par un batch de consolidation (dédup, create/update seulement).
- **`config.py`** : `memory_mental_models_enabled` (défaut False) +
  `memory_mental_models_active` (exige croyances actives **et** opt-in).
- **`checkpoint.py`** : `rollback_mental_models` appelé dans la transaction de rewind
  (atomique avec faits/croyances/events).
- **`savestore.py`** : `Mental_Models` ajouté à l'export `.axiomsave`.
- **`arbitrator.py`** : `_fetch_relevant_mental_models` (priorise on-scene → récents,
  borné `max_turn_id`) ; injection `Profile:` en **tête** de hiérarchie (cap 4),
  gardée par `memory_mental_models_active` (lite/croyances-off inchangés).
- **`workers/fact_worker.py`** : après consolidation, `_do_refresh_models` régénère les
  modèles des sujets touchés + stale (cap `_MAX_MODEL_REFRESH=3`), isolé (un échec ne
  touche pas les croyances). Flag `refresh_mental_models` câblé depuis `tabletop_view`.

### App / doc
- **GUI** : case « Profils vivants » dans Réglages → Mémoire (grisée tant que les
  croyances ne sont pas cochées), round-trip load/save ; onglet « Profils » (lecture
  seule) dans le memory browser, en tête.
- **i18n** : `memory_mental_models_label` + doc `doc_settings_memory_mental_models{,_t,_d}`
  + 3 clés `memory_browser_*` → **×10 langues** (i18n_check 732/732, doc_check 288).
- **Doc Sphinx** : section *Mental models* dans `docs/guides/memory.md` (+ hiérarchie /
  tableau des modes mis à jour) ; modules ajoutés à `docs/api/memory.md` ; traduction
  **FR** du guide via gettext (`.po` traduit, entrées API laissées EN par convention) ;
  builds **EN + FR strict (-W) EXIT 0**.

### Tests
- `tests/test_mental_models.py` (upsert/get/count/stale, rollback, intégration rewind,
  injection arbitrator, gating config), `tests/test_reflect.py` (affected_subjects,
  reflect : trim / seuil / graceful), `tests/test_fact_worker.py` (+2 : refresh on/off).
- Périmètre touché : **244 passed**.

### Restant (PENDING, non porté volontairement)
- TICKET-082 : directives §7.9 (redondant avec Basic Prompt / personas / missions),
  extraction temporelle §7.5 (peu pertinent en temps de jeu).

⚠ **Non commité** — attente feu vert utilisateur.
