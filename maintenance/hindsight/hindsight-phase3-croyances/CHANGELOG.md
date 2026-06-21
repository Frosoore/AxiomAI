# CHANGELOG — Phase 3 (croyances / consolidation)

## 2026-06-18 — Démarrage
- Création de l'étape (DOC/TODO/CHANGELOG).
- Prérequis tracé : investigation temps causal ↔ tours → TICKET-074/075/076 dans PENDING. Conclusion :
  Phase 3 vit sur l'axe `turn_id` (axe sûr du rewind), zéro contact avec les sous-systèmes en minutes.

### Item 1 — table Observations + stockage + rollback ✅ (déterministe, zéro LLM)
- `schema.py` : **`_DDL_OBSERVATIONS`** (observation_id, save_id, subject, statement, proof_count,
  `sources` JSON `[{fact_id,turn_id}]`, history JSON, created/updated_turn_id, stale ; FK→Saves CASCADE),
  index `idx_observations_save_turn`, ajout aux listes + **`ensure_observations_table`** (auto-migration).
- `axiom/observations.py` (nouveau) : dataclass **`Observation`** + `insert_observation`/`get_observations`
  (filtres `max_turn_id` sur `created_turn_id`, `subject`, `limit`) / `count_observations` +
  **`rollback_observations(conn, …)`** (clé de rollback = `created_turn_id` + sources `turn_id`) :
  `created > N` → DELETE ; sinon garde sources `≤ N`, recompute `proof_count`, clamp `updated_turn_id`,
  flag `stale`. Variante standalone pour tests.
- `checkpoint.rewind` : **rollback des croyances dans la même transaction** que Event_Log/Facts → events,
  faits et croyances reculent atomiquement.
- `config.memory_beliefs_enabled` (off) + helper **`memory_beliefs_active`** (living ET opt-in).
- `savestore.py` : **`Facts` ET `Observations` ajoutés à l'export `.axiomsave`** (oubli de Phase 2
  rattrapé pour les faits) + garde « table absente côté source » (vieilles saves robustes).
- Tests : `tests/test_observations.py` (insert/get/filtres + rollback unitaire + **test d'acceptation**
  « 20 tours → rewind 10 → ne reflète que ≤ 10 » + intégration `checkpoint.rewind` + gate config).

### Item 2 — consolidateur LLM ✅ (Mode Vivant, testé via mock)
- `axiom/consolidate.py` (nouveau) : `consolidate(llm, new_facts, existing, mission=…)` → liste
  d'**actions CREATE/UPDATE/DELETE**. Prompt adapté de Hindsight (préférer UPDATE, une facette/croyance,
  DELETE conservateur, pas d'arithmétique). Parsing robuste, **dégradation gracieuse** (→ `[]`),
  garde-fous : fact_ids hallucinés rejetés (seuls ceux montrés), update/delete sur croyance inconnue rejetés.
- `observations.apply_consolidation(db_path, save_id, turn_id, actions, fact_turn_map)` (déterministe) :
  CREATE (sources taguées turn), UPDATE (fusion dédupliquée des sources + history), DELETE.
- Tests : `tests/test_consolidate.py` (consolidate mocké + apply CREATE/UPDATE/DELETE + apply→rollback).

### Item 3 — injection des croyances dans le contexte ✅ (moteur pur)
- `axiom/arbitrator.py` : **`_fetch_relevant_beliefs`** (perso en scène d'abord puis récents, borné
  `max_turn_id`, dédup). En `living` + croyances actives, **hiérarchie de rappel** : `Belief:` (synthèse)
  → `Known fact:` → chunks narratifs bruts. `lite` et `living` sans croyances : chemin inchangé.
- Tests : `tests/test_observations.py::TestArbitratorBeliefInjection`.

### Item 4 — couche app ✅ (worker + GUI + i18n)
- `workers/fact_worker.py` : `FactExtractWorker(consolidate_beliefs=…)` — après `insert_facts`, si actif,
  **chaîne la consolidation** (facts tagués de leur fact_id+turn, `get_observations` existantes,
  `consolidate`, `apply_consolidation`) dans le **même thread de fond**. Isolé : un échec consolidation ne
  défait pas les faits ni ne casse le tour.
- `ui/tabletop_view.py` : passe `consolidate_beliefs=memory_beliefs_active(cfg)`.
- `ui/settings_dialog.py` : case **« Croyances évolutives »** dans l'onglet Mémoire (grisée hors Vivant),
  load/collect/refresh/retranslate ; `doc()`-ée (`settings.memory_beliefs` + détail `_d`).
- i18n ×10 : `memory_beliefs_label` + `doc_settings_memory_beliefs(_t/_d)`. `i18n_check` ✅, `doc_check` ✅.
- Tests : `tests/test_fact_worker.py` (chaînage croyances on/off).

### Phase 3 COMPLÈTE (moteur items 1-3 + app item 4). **Suite 872 ✅.** Rien commité.
Reste : **Phase 4** (raffinements — modèles mentaux, directives/persona, extraction temporelle, prompt
caching Gemini pour le coût). Croyances exposables : mission par perso/univers (B-3) à étudier plus tard.
