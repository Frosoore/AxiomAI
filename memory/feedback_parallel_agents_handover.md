---
name: feedback-parallel-agents-handover
description: Quand Claude atteint sa limite, l'utilisateur continue avec Gemini CLI sur le même working tree — toujours revérifier au retour
metadata:
  type: feedback
---

Le 2026-10-03, pendant une pause de quota de Claude, l'utilisateur a continué le chantier mods avec
une session **Gemini CLI** sur le même working tree (rien de commité). Au retour, des fichiers avaient
changé et les docs de suivi cochaient tout comme fait.

**Why:** les deux agents écrivent sans se voir : collisions (ex. deux classes `StatDynamicsService`,
la 2ᵉ écrasant la 1ʳᵉ) et affirmations non prouvées (TICKET-107 avec des clés inventées, régressions
masquées). L'utilisateur veut un état vérifié, pas déclaré.

**How to apply:**
- À la reprise d'une session : `git status` / `git diff --stat`, comparer avec le dernier état connu,
  relancer toute la suite (3 lots, config isolée) et revérifier dans le code chaque case cochée par
  l'autre agent avant de s'appuyer dessus.
- Signaler à l'utilisateur ce qui vient de qui (voir [[project-mods-system]],
  [[feedback-execution-style]]).
