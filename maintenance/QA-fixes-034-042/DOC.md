# QA-fixes-034-042

Correction en lot des tickets QA du 2026-06-10 (voir constats détaillés dans `DONE.md`
après archivage). Tous des bugs contenus — aucun changement d'architecture : la frontière
moteur/Qt, le format Universe-as-Code et le modèle de saves sont inchangés.

Décisions notables :
- ids d'entités non-latins : fallback **déterministe** (`ent_<sha1(nom)[:12]>`), pas un uuid —
  l'idempotence des Populate (relance = reprise) repose sur la stabilité des ids.
- conversion .db plat : les entités runtime d'un db **d'avant la colonne `origin`** sont
  détectées par heuristique (type 'player' hors héros compagnon + ids vus dans des events
  `entity_create`) et marquées `origin='runtime'` avant decompilation.
- langues secondaires : seules les contaminations relevées sont corrigées (pas de
  retraduction complète — contenu, hors scope).
