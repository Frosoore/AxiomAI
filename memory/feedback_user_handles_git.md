---
name: feedback-user-handles-git
description: L'utilisateur gère lui-même les commits et les branches sur AxiomAI — ne pas commit/stage/brancher
metadata:
  type: feedback
---

Sur AxiomAI, **ne pas s'occuper des commits, du staging (`git add`) ni des branches** :
l'utilisateur les fait lui-même. Implémenter, tester et documenter (cf. [[feedback-maintenance-workflow]]),
puis s'arrêter là — ne pas proposer ni exécuter de commit, et ne pas demander de « feu vert pour commit ».

**Why:** demandé explicitement (2026-06-04) après que j'aie tenté de committer le travail ;
l'utilisateur gère son historique git à sa façon.

**How to apply:**
- Laisser les modifications dans le working tree (modifiées, non indexées). Ne pas `git add -A`.
- Pas de `git commit`, pas de création/bascule de branche, pas de `git reset` spontané.
- `git status`/`git diff`/lecture d'historique restent OK pour situer le travail.
- Annuler un ancien réflexe : la doc d'étape mentionnait « attente feu vert commit » — désormais
  sans objet, on ne parle plus de commits du tout.
