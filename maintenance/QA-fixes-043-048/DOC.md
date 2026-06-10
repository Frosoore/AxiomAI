# DOC — QA-fixes 043→048

**Objectif.** Corriger en lot les 6 tickets ouverts par la QA post-merge du 2026-06-10
(`maintenance/QA-post-merge-companion-images/`) sur les features Companion Mode et
génération d'images.

**Décisions techniques notables :**
- L'id de l'entité joueur n'est **jamais** supposé être `"player"` : il se résout depuis
  les intents du tick (premier acteur ≠ héros), règle désormais commune à `Session` et à
  l'arbitrator.
- Un backend d'images réel qui échoue ne produit **rien** (`None`) ; l'image mock 1×1
  n'existe que pour le backend de test `"mock"`.
- Les illustrations (`assets/<save_id>/turn_<n>.png`) font partie de la save : elles
  suivent duplication, suppression, export/import `.axiomsave` et rewind. Le format
  d'archive reste compatible (anciennes archives importables, entrées assets ignorées
  par les anciens lecteurs).
- Tranché : la génération d'images est un service de `Session` ; le chemin multijoueur
  `ActionQueue` n'en produit pas.

**Usage :** rien de nouveau à apprendre côté utilisateur — les réglages de l'onglet
« Illustration » sont désormais traduits via le système i18n standard, et les images
suivent automatiquement les opérations sur les saves.
