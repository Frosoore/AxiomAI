# DOC — TICKET-056 : messages user-facing du moteur en anglais

## Objectif
Le moteur publié `axiomai-engine` ne doit exposer **aucun texte français** à l'utilisateur : messages
d'exception, events (`axiom dev`), statuts surfacés → **anglais**. Prolonge TICKET-054 (données/clés)
et TICKET-055 (CLI).

## Règle pour la suite
- Toute exception levée par `axiom/*.py` avec un message destiné à l'utilisateur s'écrit **en anglais**.
- Idem pour les callbacks `on_event` / `on_status` et les libellés écrits comme données surfacées.
- Restent légitimement en français (hors périmètre) : commentaires/docstrings internes, logs
  `logger.*` (diagnostic), et la couche **app** (`ui/`, `workers/`) qui, elle, est localisée via
  `core.localization` (i18n).

## Piège à connaître
Le français **sans accent** (« invalide », « introuvable », « impossible », « requis ») échappe à un
grep d'accents. Pour auditer : lister tous les `raise … ("…")` et juger au contenu, pas aux accents.
