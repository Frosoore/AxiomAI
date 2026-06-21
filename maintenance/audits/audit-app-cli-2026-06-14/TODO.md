# TODO — Audit app GUI + CLI (2026-06-14)

Constat dans `RAPPORT.md`, corrections dans `CHANGELOG.md`. **Tout corrigé le 2026-06-14**
(feu vert « corrige tout »), suite 767 verte.

## Bugs
- [x] App-B1 — `DbWorker.load_full_universe` dédoublé (mort/cassé) → supprimé
- [x] App-B2 — Label « Regenerate » jamais traduit → `tr("regenerate")`

## Architecture
- [x] App-A1 — Pattern « TempTask inline » → 9 vraies tâches dans `db_tasks.py`
- [x] App-A2 — `take_snapshot_async`/`SnapshotTask` orphelins → supprimés (le moteur fait les snapshots)

## Micro-optimisations
- [x] App-M1 — N+1 stats → requête `Entity_Stats` groupée (`_read_stats_by_entity`)
- [x] App-M2 — Migrations idempotentes → gatées par db_path (`ensure_universe_migrations`)
- [x] App-M3 — `get_current_time` hors main thread → `ArbitratorResult.in_game_time`
- [x] App-M4 — `tr()`→`load_config()` par appel → langue mémorisée (invalidée au save settings)

## Latent / à surveiller (non corrigé — risque faible, sérialisé par l'UI)
- [ ] `VectorMemory` partagé entre threads sans verrou (embed/rollback). Aucun bug observé : l'UI
      désactive l'envoi pendant tour/variante/rewind. À traiter si une opération vectorielle doit
      un jour tourner en parallèle d'un tour.
