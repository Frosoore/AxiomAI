# TODO — Règles pour l'univers par défaut Myria

L'univers embarqué `universes/Myria/` n'a **aucune règle** (`rules/` absent) → le moteur de
règles déterministe (l'Arbitrator, l'argument phare d'Axiom) ne fait rien dans l'univers vitrine.

## Tâches
- [x] Créer `universes/Myria/rules/*.toml` — 4 règles thématiques (une par fichier).
- [x] Robustesse « stat absente = "0" » : seuils `>=` positifs pour les effets joueur ; vérifié
      qu'un PNJ sans Notoriety n'est pas touché.
- [x] Règles appuyées sur des stats réellement portées par le joueur (Health/Notoriety).
- [x] Sémantique Arbitrator respectée (`value` pour le delta, pas de `trigger_event`).
- [x] Cache recompilé, table `Rules` = 4 (source repo **et** copie installée de l'utilisateur).
- [x] Tests verts (783 lot principal ; rules/univers/arbitrator/bundled).

⚠ Rien commité — l'utilisateur gère git.
