---
name: feedback-maintenance-workflow
description: Workflow obligatoire pour toute progression sur le projet AxiomAI — chaque étape a son propre dossier dans maintenance/
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 9df469a1-f1f0-4190-8cf3-7585d7adba1d
---

Avant de commencer toute feature, bugfix ou étape du plan d'upgrade, créer un sous-dossier dans `maintenance/<nom-etape>/` contenant trois fichiers : `TODO.md`, `CHANGELOG.md`, `DOC.md`.

**Why:** Le projet subit une grosse refactorisation par phases (P1–P7). L'utilisateur veut localiser les connaissances dans des fichiers petits et ciblés plutôt qu'un seul gros doc. Chaque étape doit être autonome et traçable.

**How to apply:**
- À chaque nouvelle étape : créer `maintenance/<nom-etape>/TODO.md`, `CHANGELOG.md`, `DOC.md` avant d'écrire du code.
- `TODO.md` : liste des tâches de l'étape.
- `CHANGELOG.md` : ce qui a été accompli (mis à jour au fil du travail).
- `DOC.md` : objectif, décisions techniques, comment utiliser ce qui a été fait.
- Mettre à jour le tableau dans `maintenance/README.md` pour référencer chaque nouvelle étape.
- Ne jamais mélanger plusieurs étapes dans le même dossier.
