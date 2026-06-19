# TODO — Phase 2 (infra deux modes + faits)

## Item 1 — toggle memory_mode ✅ (volet config)
- [x] `config.py::memory_mode` ("lite" défaut) + helper `memory_mode_is_living`.
- [x] Court-circuit `lite` (le helper garde le LLM). [GUI + i18n différés au panneau Mémoire avec item 4.]

## Item 2 — table Facts + stockage + rollback (déterministe, zéro LLM) ✅
- [x] `schema.py` : `_DDL_FACTS` + index + `_ALL_DDL`/`_DDL_INDEXES`/`EXPECTED_TABLES` + `ensure_facts_table`.
- [x] `axiom/facts.py` : `insert_facts`/`get_facts`/`rollback_facts`/`count_facts` + dataclass `Fact`.
- [x] `CheckpointManager.rewind` : DELETE Facts turn_id > target (même transaction).
- [x] Tests `test_facts.py` (14) + rewind couvre les faits. Suite 829 ✅.

## Item 3 — extraction LLM (Mode Vivant) ✅ (2026-06-18)
- [x] `axiom/factextract.py` : prompt adapté Hindsight + `LLMBackend.complete(response_format="json")`.
- [x] Parsing robuste JSON → `list[Fact]` ; dégradation gracieuse (erreur → 0 fait, pas de crash).
- [x] Config `memory_fact_interval` (N, désactivable) + `memory_fact_model` (override). Tests mockés (11).

## Item 5 — faits dans la recherche ✅ (2026-06-18)
- [x] `_fetch_relevant_facts` (scène d'abord, puis récents, borné `max_turn_id`, dédup/cap, gracieux).
- [x] Fusion en tête de `rag_chunks` (`Known fact: …`) en `living` seul ; `lite` inchangé. Tests (4). Suite 844 ✅.

## Item 4 — job de fond + GUI (couche APP) ✅ (2026-06-18) → voir `ITEM4_HANDOFF.md`
- [x] Worker `workers/fact_worker.py` (modèle `vector_worker.py`) : `extract_facts`+`insert_facts` hors
      tour, buffer des N derniers tours, gardé par `memory_mode_is_living`. Mode `lite` = no-op total.
- [x] Bouton « extraire maintenant » (reset compteur, `extract_now_requested` → `extract_facts_now`) +
      onglet GUI « Mémoire » (mode/N/modèle/cross-encoder) dans `settings_dialog`, tout `doc()`-é.
- [x] **Régression corrigée** : `collect_config` ne réinitialise plus les 4 champs `memory_*`.
- [x] i18n ×10 (11 clés UI + 12 clés doc intégrée) ; `i18n_check` + `doc_check` ✅.
- [x] Tests : `test_fact_worker.py` (3) + 3 dans `test_settings_dialog.py`. Suite 850 ✅.

## ✅ Phase 2 COMPLÈTE (moteur items 1,2,3,5 + app item 4). Rien commité.
</content>
