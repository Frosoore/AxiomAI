---
name: project-status-doc-convention
description: Tenir à jour AXIOM_STATUS.md (historique projet, à chaque commit) + la page mensuelle Dev updates du site
metadata:
  type: project
---

**Décidé le 2026-06-16.** Deux supports d'historique à maintenir, demandés par l'utilisateur :

1. **`AXIOM_STATUS.md`** (racine du repo) = historique narratif, plain-language, de ce qu'on
   **fait / fix / implémente / casse**. Compagnon de `Changelog.md` (lui plus machine).
   **🔴 RÈGLE : on ajoute une ligne en haut du « Log » à CHAQUE commit** (humain ou LLM), dans le
   même commit. Format : `- **AAAA-MM-JJ** · \`scope\` · type — description une ligne.`
   (scope = engine/ui/cli/docs/site/tests/ci/build ; type = add/fix/change/remove/break/chore).

2. **Page « Dev updates »** = `landing/dev-updates.html` : **une fois par mois**, un compte rendu de
   l'état du code par rapport au mois précédent, avec un **sélecteur de mois**. Les entrées vivent
   dans le tableau JS `DEV_UPDATES` (newest first) ; un bloc commentaire « HOW TO ADD A MONTHLY
   UPDATE » explique le schéma pour qu'un LLM puisse compléter. C'est la vue mensuelle publique du
   même historique que `AXIOM_STATUS.md`. Seedé avec l'entrée de juin 2026.

**Why:** l'utilisateur veut une trace vivante de l'avancement, lisible, qu'un LLM entretient seul.
**How to apply:** à chaque commit → 1 ligne dans `AXIOM_STATUS.md` ; en fin de mois → 1 objet en
tête de `DEV_UPDATES` dans `landing/dev-updates.html`. Statut projet = **early alpha** (PAS beta),
voir [[project-beta-launch]]. Le site vit dans `landing/` (Pages), cf. [[project-doc-chantier]].
