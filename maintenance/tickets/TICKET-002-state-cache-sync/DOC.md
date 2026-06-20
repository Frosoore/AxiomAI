# DOC — TICKET-002

**Objectif :** garder `State_Cache` (vue matérialisée des stats de base) en phase
avec les changements de chaque tour, pour que les lectures DB (sidebar) ne soient
plus figées au load de session.

**Décision technique :** mise à jour **incrémentale** (`update_state_cache`) plutôt
que `rebuild_state_cache` à chaque tour — aucun snapshot n'est pris dans l'app,
donc un rebuild rejouerait tout l'historique (O(n²) sur une partie).

**Invariant conservé :** `State_Cache` = stats de **base**. Les modifiers
(`Active_Modifiers`) restent appliqués à la lecture (`_fetch_effective_stats`),
jamais écrits en cache.
</content>
