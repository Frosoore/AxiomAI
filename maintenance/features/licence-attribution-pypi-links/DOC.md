# DOC — Licence : AGPL conservée + obligation de citation + liens PyPI

**Objectif final (après aller-retour, 2026-06-11).** Le projet **reste sous AGPL-3.0-or-later**
et gagne : (1) une **obligation de citation** pour quiconque redistribue le code, (2) des
**liens vers le repo GitHub** sur la page PyPI de `axiomai-engine` (introuvable sinon).

**Historique de la décision.** L'utilisateur a d'abord demandé un passage en GPL v3 (fait puis
annulé) : son doute sur l'AGPL venait d'une mauvaise lecture de l'en-tête du fichier LICENSE —
le « changing it is not allowed » protège le *texte de la licence* (copyright FSF), pas le
logiciel. Une fois clarifié, retour à l'AGPL, qui couvre en plus le cas SaaS (héberger une
version modifiée en service réseau oblige à publier les sources — protection que la GPL n'a pas).

**Comment la citation est rendue obligatoire.** L'**article 7(b)** de l'AGPL v3 (identique à
celui de la GPL v3, vérifié dans le texte) autorise un terme additionnel exigeant la
préservation des attributions d'auteurs. C'est le rôle du fichier **`NOTICE`** : toute
redistribution (source ou binaire, modifiée ou non) doit le conserver et créditer
« Based on Axiom AI (https://github.com/Frosoore/AxiomAI) by 17h59 and Frosoore ». Le NOTICE
voyage partout : repo, wheel PyPI (`license-files`), export `export_engine.py`.

**Liens PyPI.** `[project.urls]` dans `pyproject.toml` (Homepage / Repository / Issues →
github.com/Frosoore/AxiomAI) = encadré « Project links » de la page PyPI ; + section « Projet »
dans le README généré de la lib.

**Validité.** Le terme additionnel d'attribution nécessite l'accord des deux titulaires du
copyright (17h59 **et** Frosoore). La 0.1.0 déjà sur PyPI n'a ni le NOTICE ni les liens →
republier.
