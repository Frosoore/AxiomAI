# B3 — Migration Populate* vers le moteur — DOC

L'authoring LLM d'univers vit désormais dans `axiom/populate.py` (zéro Qt) : sept
fonctions, une par générateur, registre `POPULATE_TARGETS`. Les tâches Qt de
`workers/db_tasks.py` ne sont plus que des coquilles (thread + signaux), même schéma que
l'import/export (.axiom) et le reste du Pilier 1.

Utilisable headless : `axiom populate <univers> -t entities -t lore [--text "consigne"]`.
Le LLM est injectable (`llm=`) — c'est comme ça que les tests tournent sans clé API.
