# TODO — TICKET-062 item 1 : univers par défaut (câblage premier lancement)

Contexte : l'univers `universes/Myria/` (Universe-as-Code, 40 fichiers) a été
créé lors d'une session précédente mais n'était **installé nulle part** —
l'utilisateur ne le trouvait pas dans l'app (il ne voyait que son vieux
`~/AxiomAI/universes/Myria.db` de test, vide). C'est le « Reste : câblage
premier lancement » du ticket.

- [x] Module d'installation `core/bundled_universes.py` : copier les univers
      embarqués du repo (`universes/<nom>/`) vers la bibliothèque du Hub
      (`~/AxiomAI/universes/<nom>/`), une seule fois (marqueur), sans jamais
      écraser un dossier existant, cache exclu (recompilé par la découverte)
- [x] Brancher dans `main.py` au démarrage
- [x] Tests unitaires (8, `tests/test_bundled_universes.py`)
- [x] Vérification réelle sur la machine : installé dans `~/AxiomAI/universes/
      Myria/`, découverte Hub OK (11 entités, 15 lore, 18 lieux, 2 événements)
- [x] Crash « Edit » du 2026-06-12 corrigé (double bug : texte libre dans
      `world_tension_level` de Myria → 0.6 ; Studio blindé via `_meta_float`)
      — découverte TICKET-065 (clé tension en deux casses, curseur sans effet)
- [ ] ⚠ Validation GUI par l'utilisateur (Hub → Myria s'ouvre dans le Studio
      et est jouable) + relecture canon de l'univers (toujours en attente)
- [ ] Décision utilisateur : supprimer le vieux `~/AxiomAI/universes/Myria.db`
      de test (vide) qui fait doublon de nom dans le Hub ?

Hors scope ici : items 2-5 du ticket (clés Fireworks, Windows, diagnostic,
assets de com').
