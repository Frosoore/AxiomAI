# PENDING — tickets à étudier

## TICKET-002 — State_Cache jamais mis à jour entre les tours

**Contexte :** Découvert en A3. `State_Cache` est construit une fois au load de la session (`rebuild_state_cache`), puis JAMAIS mis à jour après les tours. Le `_stats_cache` (3.3) corrige le problème CÔTÉ ARBITRATOR (états corrects d'un tour à l'autre). Mais `LoadFullGameStateTask` / `LoadStatsTask` lisent toujours depuis `State_Cache` → la sidebar montre des stats figées au moment du load, pas les stats réelles.

**Ce qui serait à faire :**
- Ajouter un UPSERT sur `State_Cache` après chaque event `stat_change`/`stat_set` dans `append_event` ou `append_events_batch`, OU
- Appeler `rebuild_state_cache` (léger si Snapshot récent) avant chaque `load_full_game_state`, OU
- Alimenter la sidebar depuis `_stats_cache` de l'Arbitrator plutôt que la DB.

**Priorité :** haute — la sidebar affiche probablement des stats en retard depuis le début du projet.

---

## TICKET-001 — Rework tests : lisibilité, couverture et organisation

**Contexte :** Audit A1-1.10. Les `debug/test_*.py` sont conservés mais hors portée pytest. Les `tests/` couvrent bien l'engine mais manquent d'explicité (noms, docstrings, output verbose) et certains cas utiles existent en double (debug/ vs tests/).

**Ce qui serait à faire :**
- Rendre les noms de tests auto-documentants (ce qu'on teste, sous quelle condition, résultat attendu)
- Migrer les `debug/test_*.py` de type `unittest.TestCase` vers `tests/` une fois complétés/nettoyés, supprimer les doublons debug/
- S'assurer que tout ce qui sera ajouté (Piliers 1–7) a une couverture pytest dès le départ
- Évaluer pytest `--verbose` / `--tb=short` comme standard de run pour lisibilité output

**Priorité :** basse — à faire après stabilisation Phase A/B.
