# TODO — Phase 0d : Tour transactionnel & Époques de session

- [x] Créer la classe de staging `TurnWriteBatch` dans `axiom/turn_batch.py`
  - [x] Accumulation en mémoire des événements, changements de stats, inventaire, timeline, session lore, modifiers
  - [x] Méthode `commit_all(self, conn: sqlite3.Connection, save_id: str, turn_id: int) -> None` atomique
- [x] Adapter `ArbitratorEngine` (`axiom/arbitrator.py`)
  - [x] Ne plus écrire au fil de l'eau dans SQLite pendant `process_turn` / `resolve_turn`
  - [x] Stager toutes les mutations dans une instance `TurnWriteBatch` retournée dans `ArbitratorResult`
- [x] Mettre à jour `Session.take_turn` / `resolve_tick` (`axiom/session.py`)
  - [x] Valider la génération complète avant d'exécuter `batch.commit_all(...)`
  - [x] En cas de `GenerationCancelled` ou d'exception, abandonner le batch sans écriture disque
- [x] Gestion des époques de session (`SessionEpochManager`)
  - [x] Ajouter `self.epoch: int = 0` dans `Session`
  - [x] Incrémenter atomiquement `self.epoch` lors de `rewind`, `fork`, rechargement/changement de save
  - [x] Transmettre `captured_epoch = self.epoch` aux workers de living memory
  - [x] Vérifier `captured_epoch == session.epoch` avant toute écriture asynchrone différée
- [x] Validation complète avec `tests/test_golden_step.py`
