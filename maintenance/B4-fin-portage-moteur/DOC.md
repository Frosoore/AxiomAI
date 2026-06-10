# B4 — Fin du portage moteur — DOC

La table « non migré » d'ARCHITECTURE.md est **vide** : toute la logique métier vit dans
`axiom/` (zéro Qt), les workers/`core` ne sont plus que des véhicules de thread + signaux.

Derniers portages : création d'entité joueur (`axiom/db_helpers.py`), régénération de
variante (`axiom/regenerate.py` + `Session.regenerate_variant`), Mini-Dico
(`axiom/mini_dico.py`), file multijoueur (`axiom/multiplayer.py::ActionQueue`).

Conséquence pratique : tout est pilotable headless (tests, CLI, futur serveur), et le
TICKET-009 (split packaging `axiom-engine`) n'a plus de prérequis de migration.
`workers/chronicler_worker.py` est mort (jamais instancié) — suppression sur feu vert.
