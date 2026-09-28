# CHANGELOG — Phase 0d : Tour transactionnel & Époques de session

## 2026-09-26
- Initialisation de la phase 0d.
- Création de `axiom/turn_batch.py` : classe `TurnWriteBatch` pour stager en mémoire toutes les mutations d'un tour (événements, stats, inventaire, timeline, session lore, modificateurs) et exécuter un `commit_all` atomique en transaction SQLite unique.
- Création de `axiom/epoch.py` : gestionnaire `SessionEpochManager` pour suivre et incrémenter thread-safe les époques de session (`session.epoch`).
- Mise à jour de `axiom/schema.py` : support de réentrance pour `_ClosingConnection` avec compteur de profondeur `_enter_depth`.
- Mise à jour de `axiom/arbitrator.py` : support de `auto_commit` (défaut True pour compatibilité, False pour Session). Staging complet dans `TurnWriteBatch` sans écriture prématurée dans SQLite.
- Mise à jour de `axiom/session.py` :
  - Intégration de `SessionEpochManager` (`session.epoch`).
  - `rewind()`, `load()`, et `fork()` incrémentent atomiquement l'époque de session.
  - `resolve_tick()` ne committe le batch `result.batch.commit_all(...)` qu'une fois la génération et les tâches associées validées avec succès. En cas d'annulation (`GenerationCancelled`) ou d'exception, rollback en mémoire et aucune trace sur disque.
  - Transmission de l'époque et d'un vérificateur d'époque (`epoch_checker`) à la pipeline de living memory.
- Mise à jour de `axiom/living_memory.py` : propagation et vérification de validité de l'époque avant toute écriture différée en base de données.
- Tests d'intégration ajoutés dans `tests/test_golden_step.py` :
  - `test_transactional_turn_atomicity_on_cancellation` : vérification qu'aucune ligne n'est écrite en cas d'annulation de tour.
  - `test_session_epoch_bump_and_stale_worker_discard` : vérification du bump d'époque et du rejet des écritures des workers asynchrones obsolètes.
