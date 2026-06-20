# CHANGELOG — TICKET-002

## Session 2026-05-23

### Diagnostic (confirmé par grep)
- L'`ArbitratorEngine` calcule les stats correctes en mémoire (`_stats_cache`) et
  écrit les events dans `Event_Log` via `append_events_batch`, mais **n'écrit
  jamais dans la table `State_Cache`**.
- `State_Cache` n'est rafraîchie que par `rebuild_state_cache` (au load de session
  `axiom/session.py:162`, et au rewind `axiom/checkpoint.py:86`).
- La sidebar lit `State_Cache` (`LoadFullGameStateTask` / `LoadStatsTask` →
  `get_current_stats`) → stats figées au moment du load.
- **Snapshots jamais pris dans l'app** : `take_snapshot_async` / `take_snapshot`
  n'ont aucun site d'appel hors définition. Donc `rebuild_state_cache` rejoue
  toujours tout l'historique → l'appeler à chaque tour serait O(historique²).
  → approche **incrémentale** retenue (correcte ET performante).

### Implémentation
- `axiom/events.py` : nouvelle méthode `EventSourcer.update_state_cache(save_id, events)`.
  Reprend le batch d'events fraîchement appended, ne garde que les events
  pertinents (`entity_create` / `stat_change` / `stat_set`), réamorce un cache
  mémoire avec les valeurs de base courantes des entités touchées, rejoue le
  batch via `_apply_event` (gère les deltas chaînés intra-batch, ex. cascades
  du moteur de règles), puis UPSERT dans `State_Cache`
  (`ON CONFLICT(save_id, entity_id, stat_key) DO UPDATE`).
  Sémantique strictement équivalente à `rebuild_state_cache` sur les entités
  touchées (les modifiers restent appliqués à la lecture, pas stockés en cache).
- `axiom/arbitrator.py` : appel de `update_state_cache(save_id, _pending_events)`
  juste après `append_events_batch`.

### Tests
- `tests/test_event_sourcing.py::TestUpdateStateCache` (4 cas) :
  delta sur cache existant, deltas chaînés dans un batch, events non-stat ignorés,
  parité avec un `rebuild_state_cache(force_full=True)`.
- `test_event_sourcing` (23), `test_arbitrator` (+`test_checkpoint`,
  `test_modifier_processor`) : **55 passed**. Aucune régression.

### Hors scope (reporté → PENDING)
- Les events du Chronicler utilisent `event_type = "chronicler_update"` (avec
  delta/value), que `_apply_event` **ignore** : ces changements ne matérialisent
  jamais dans `State_Cache`, même sur rebuild. Bug distinct → nouveau ticket.
</content>
