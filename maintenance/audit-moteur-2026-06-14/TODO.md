# TODO — Audit moteur (2026-06-14)

Audit = constat seul (cf. `RAPPORT.md`). Rien implémenté. À arbitrer par l'utilisateur,
item par item, avant correction.

## Bugs
- [ ] B1 — Lore Book RAG mort (jamais vectorisé + filtre `metadata`/`type` faux) → décision : retirer ou réparer
- [ ] B2 — Overlay modifiers périmé via `_stats_cache` (expiration non reflétée hors invalidation)
- [ ] B3 — Message de rejet « the player » codé en dur pour toute entité

## Architecture / scaling
- [ ] A1 — `_load_history()` charge tout l'Event_Log/tour (prompt n'en garde que 10) → O(N²)
- [ ] A2 — `take_snapshot_async` jamais appelé → `rebuild_state_cache` rejoue depuis tour 0
- [ ] A3 — `current_stats()` rebuild systématique alors que `State_Cache` est déjà frais

## Micro-optimisations
- [ ] M1 — N+1 `Stat_Definitions` dans `_validate_change` (charger le set 1×/tour)
- [ ] M2 — `query()` `collection.get()` de tous les chunks juste pour compter (`include=[]`)
- [ ] M3 — Multiples `get_connection()`/tour (partager une connexion sur les lectures)
- [ ] M4 — Imports locaux répétés sur le hot path (hisser en tête)
- [ ] M5 — `datetime.utcnow()` déprécié (db_helpers.py:155)
