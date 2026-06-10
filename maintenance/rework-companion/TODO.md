# TODO - Rework Mode Companion

- [x] Valider la documentation (`DOC.md`) avec l'utilisateur.
- [x] Mettre à jour la logique des prompts (`axiom/prompts.py`).
- [x] Transmettre les variables de contexte dans `Session.take_turn` et `_get_hero_decision` (`axiom/session.py`).
- [x] Adapter les tests unitaires concernés (`tests/test_session.py`, `tests/test_arbitrator.py`).
- [x] Corriger la troncature de la réponse du Compagnon en augmentant sa limite de tokens (max_tokens).
- [x] Résoudre l'effacement des actions du joueur en mode Companion en identifiant explicitement le joueur et le compagnon dans les NARRATOR RULES.
- [x] Empêcher l'IA du compagnon de se substituer au narrateur en modifiant l'injection de l'historique narratif et en durcissant le HERO_SYSTEM_PROMPT.
- [x] Résoudre l'invisibilité du Compagnon en injectant son vrai nom au lieu de son UUID dans le bloc d'intentions du Narrateur (`ArbitratorEngine.process_turn`).
- [x] Gérer le conflit de pronoms (les deux acteurs utilisent "Je") en forçant le narrateur à traduire l'intent du joueur en "Vous" et l'intent du Compagnon en "Son nom".
