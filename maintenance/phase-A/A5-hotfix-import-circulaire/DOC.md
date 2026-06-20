# A5 — Hotfix import circulaire

**Objectif :** débloquer le démarrage cassé par A3.4.

**Décision :** la couche `database/` ne doit pas importer `core` au chargement
du module. On récupère le logger nommé déjà configuré
(`logging.getLogger("Axiom AI")`, mêmes handlers que
`core.logger.setup_logger()`) au lieu d'importer `core.logger`. Cela respecte
le sens de dépendance attendu (core → database, jamais l'inverse) et préfigure
la séparation de Phase B (Pilier 1).
