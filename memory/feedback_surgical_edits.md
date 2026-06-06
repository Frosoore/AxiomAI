---
name: feedback-surgical-edits
description: Édition de code en dev parallèle — éviter le reformatage gratuit hors-scope, mais ne pas brider les grosses modifs justifiées
metadata:
  type: feedback
---

En contexte de dev parallèle à deux ([[project-parallel-dev-handover]]), la règle d'« édition ciblée »
qui réduit les conflits de merge **ne doit pas devenir un bridage timide**.

**Why:** certaines modifications nécessitent légitimement d'aller fort sur le code (grosses refontes),
et c'est important de pouvoir le faire. L'utilisateur préfère assumer d'éventuels problèmes de merge
plutôt que de s'interdire les changements profonds utiles.

**How to apply:**
- Interdire seulement le bruit **gratuit hors-scope** : reformatage, réindentation, réordonnancement
  d'imports, renommages **sur des lignes sans rapport avec la tâche** (ça fabrique des conflits inutiles).
- **Autoriser** les grosses modifs / refontes quand le travail les justifie — ne pas les freiner au nom
  de la réduction de conflits.
- Filet de sécurité retenu par l'utilisateur : « au pire on gère les problèmes quand ils arrivent ».
