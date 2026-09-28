# Documentation — Phase 0d : Tour transactionnel & Époques de session

## Objectif
Garantir l'intégrité absolue de la base de données et l'absence d'écriture corrompue en cas d'interruption ou d'annulation :
1. **Tour Transactionnel** : Aucune écriture SQL directe pendant la génération du tour. Toutes les mutations sont stagées en mémoire dans `TurnWriteBatch` et committées en bloc atomique en fin de tour.
2. **Époques de Session** : Mécanisme `session.epoch` pour invalider silencieusement toute écriture concurrente ou différée (living memory) si une opération de rewind ou de changement de save intervient entre-temps.

## Architecture

### 1. `TurnWriteBatch` (`axiom/turn_batch.py`)
- Maintient des listes d'opérations différées : `events`, `stat_changes`, `inventory_mutations`, `timeline_entries`, `lore_entries`, `modifier_mutations`, `fired_scheduled_events`, `post_commit_callbacks`.
- `commit_all(conn, save_id, turn_id)` : ouvre un bloc transactionnel SQLite unique (`with conn:`) et applique toutes les écritures dans l'ordre déterministe avant de générer les snapshots d'inventaire et de modificateurs du tour.
- En cas d'erreur ou d'annulation (`GenerationCancelled`), le batch est simplement ignoré et la base de données reste strictement intacte.

### 2. `SessionEpochManager` (`axiom/epoch.py`)
- Fournit un compteur d'époque atomique et thread-safe par session.
- Incrémenté à chaque opération invalidante : `rewind()`, `load()`, `fork()`.
- Fournit un `epoch_checker` transmis aux tâches de fond asynchrones (ex. Living Memory distillation) pour vérifier `epoch == epoch_checker()` avant de persister les faits ou mémoires extraites.
