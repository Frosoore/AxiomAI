# DOC — QA post-merge (Companion Mode + génération d'images)

**Objectif.** Après les deux merges du 2026-06-10 (`4bc313d` PR temps causal, `9814896`
origin/main → dev-0 avec résolutions de conflits manuelles), vérifier que le code est sain,
en particulier les features récentes venues de la branche Gemini : rework/upgrade du mode
Companion et génération d'images contextuelle.

**Verdict.** Le merge est globalement propre : aucune perte de code dev-0 dans les fichiers
en collision (`session.py`, `arbitrator.py`, `prompts.py`, `config.py`), API `intents=`
correctement propagée côté prod, frontière headless intacte, 580 tests verts.

**Un seul vrai cassage trouvé et corrigé ici** : un fake de test oublié par la migration
`intents=` qui gelait pytest (détail dans CHANGELOG.md).

**Six défauts de conception/finition relevés** (pas des cassages de merge) → TICKET-043 à
048 dans `maintenance/PENDING.md`, le plus important étant TICKET-043 (id joueur `"player"`
en dur dans `session.py`, qui vide silencieusement le contexte du Héros et des illustrations
quand l'id réel du joueur est dérivé de son nom).
