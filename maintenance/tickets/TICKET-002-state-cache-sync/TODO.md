# TICKET-002 — State_Cache jamais mis à jour entre les tours

- [x] Vérifier le diagnostic par grep (où State_Cache est lu/écrit, cadence des snapshots)
- [x] Choisir l'approche : mise à jour incrémentale (pas de rebuild O(historique))
- [x] `EventSourcer.update_state_cache(save_id, events)` — UPSERT incrémental
- [x] Appel dans `ArbitratorEngine` après `append_events_batch`
- [x] Tests de régression (`tests/test_event_sourcing.py::TestUpdateStateCache`)
- [x] Suites arbitrator / checkpoint / modifier vertes
- [ ] Feu vert utilisateur avant commit
</content>
</invoke>
