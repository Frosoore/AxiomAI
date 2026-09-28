# CHANGELOG — Phase 0a : Harnais « Golden Step »

## 2026-09-26
- Initialisation de la phase 0a.
- Cadrage et préparation des fichiers cibles.
- Implémentation du mock LLM déterministe `ScriptedLLMBackend` et de `SessionStateCanonicalizer` dans `axiom/testing/golden_harness.py`.
- Création de la commande CLI `axiom test` (`axiom/cli/test.py` et intégration dans `axiom/cli/main.py`).
- Fixes moteur pour la parité de cycle de vie :
  - Support de `container_id` et persistance atomique de `Session_Lore` dans `axiom/arbitrator.py`.
  - Autorisation du stat catégoriel `Location` dans la validation de l'Arbitrateur.
  - Rollback de `Session_Lore` au rewind dans `axiom/checkpoint.py`.
  - Troncature de `Session_Lore` et restauration des modificateurs historiques au fork dans `axiom/saves.py`.
- Implémentation complète du test d'intégration `tests/test_golden_step.py` (10 tours, S8 étalon, vérification rewind, fork et export/unpack sans aucune dérive).
- Validation pytest 100% passante sur `test_golden_step.py`, `test_engine_headless.py`, `test_web_server.py`.
