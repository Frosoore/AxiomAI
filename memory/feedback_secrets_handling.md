---
name: feedback-secrets-handling
description: L'utilisateur gère ses secrets (tokens, clés API) lui-même — ne pas proposer de les écrire dans des fichiers via l'agent
metadata:
  type: feedback
---

Lors de la publication PyPI (2026-06-10), j'ai proposé de créer un `~/.pypirc` où coller son token ;
l'utilisateur a refusé : **« je vais le coller à la main c'est plus prudent »**.

**Why:** il préfère que les secrets ne transitent jamais par l'agent ni ne soient persistés dans des
fichiers créés par l'agent — saisie manuelle directe dans le terminal uniquement.

**How to apply:**
- Ne jamais proposer d'écrire un token/clé/mot de passe dans un fichier (`.pypirc`, `.env`, config…)
  ni de le passer en variable d'environnement via une commande que je lance.
- Pour les opérations authentifiées : préparer tout le reste, puis donner la commande exacte que
  l'utilisateur lance lui-même dans son terminal avec saisie interactive du secret.
- Rappeler les pièges de saisie (collage terminal = Ctrl+Shift+V, saisie invisible) plutôt que de
  contourner par un fichier. Voir [[feedback-user-handles-git]] (même esprit : il garde la main).
