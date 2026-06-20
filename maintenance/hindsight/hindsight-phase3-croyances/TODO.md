# TODO — Phase 3 (croyances / consolidation)

## Item 1 — table Observations + stockage + rollback (déterministe, zéro LLM) ✅
- [x] `schema.py` : `_DDL_OBSERVATIONS` + index + listes + `ensure_observations_table`.
- [x] `axiom/observations.py` : `Observation` + insert/get/count + `rollback_observations`.
- [x] `checkpoint.rewind` : rollback des croyances dans la même transaction.
- [x] `config.memory_beliefs_enabled` + `memory_beliefs_active` (living ET opt-in).
- [x] `savestore.py` : Facts + Observations dans l'export `.axiomsave` (garde table absente).
- [x] Test d'acceptation rollback (20 tours → rewind 10 → ≤ 10) + insert/get + intégration rewind.

## Item 2 — consolidateur LLM (Mode Vivant) ✅
- [x] `axiom/consolidate.py` : prompt adapté Hindsight, CREATE/UPDATE/DELETE, garde-fous, gracieux.
- [x] `observations.apply_consolidation` (déterministe). Tests via LLM mocké.

## Item 3 — recherche / contexte ✅
- [x] Injection des croyances en tête du contexte Arbitrator (hiérarchie croyances → faits → chunks).
- [ ] ⏳ `proof_count_boost` dans `memory.query` : **neutre chez nous** (les croyances ne sont pas dans le
      store vectoriel, elles sont injectées via SQL) → non pertinent tel quel. Reporté/écarté.

## Item 4 — couche app (worker + GUI) ✅
- [x] `FactExtractWorker(consolidate_beliefs=…)` : chaîne `consolidate`+`apply_consolidation` hors tour.
- [x] Toggle GUI « Croyances évolutives » (onglet Mémoire, grisé hors Vivant) + i18n + doc ×10.

## ✅ Phase 3 COMPLÈTE (moteur 1-3 + app 4). Suite 872 ✅. Rien commité.
Reste : **Phase 4** (raffinements). Idée B-3 (mission de croyance par perso/univers) à étudier.
