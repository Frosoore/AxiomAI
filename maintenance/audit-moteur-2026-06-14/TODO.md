# TODO — Audit moteur (2026-06-14)

Audit dans `RAPPORT.md`, corrections dans `CHANGELOG.md`. **Tout corrigé le 2026-06-14**
(feu vert « corrige tout »), suite 766 verte.

## Bugs
- [x] B1 — Lore Book RAG mort → réparé (lecture SQL `Lore_Book` + ranking mots-clés, +stopwords)
- [x] B2 — Overlay modifiers périmé → cache inter-tours `_stats_cache` supprimé
- [x] B3 — Message de rejet « the player » → utilise `entity_id`

## Architecture / scaling
- [x] A1 — `_load_history()` borné aux tours récents (fin du O(N²))
- [x] A2 — Snapshots périodiques câblés dans `resolve_tick` (tous les 25 tours)
- [x] A3 — Hot path lit State_Cache via `_read_state_cache()` (plus de rebuild/appel)

## Micro-optimisations
- [x] M1 — N+1 `Stat_Definitions` → `_load_defined_stats()` 1×/tour
- [x] M2 — `query()` `count()` au lieu de `get()`
- [x] M3 — Lectures noms+persona fusionnées en une connexion (partage helpers laissé hors-scope)
- [x] M4 — Imports hot path hissés (sauf `load_config`, gardé local pour les patchs de test)
- [x] M5 — `datetime.utcnow()` → `datetime.now(timezone.utc)`
