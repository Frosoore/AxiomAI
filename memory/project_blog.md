---
name: project-blog
description: Blog du site GitHub Pages (landing/) — système, conventions d'écriture et règle de signature par auteur
metadata:
  type: project
---

Le site `landing/` a un **blog** (ajouté 2026-06-20) en plus de la page Dev (roadmap +
changelog). But : news détaillées, vie du projet, deep-dives. Généré par
`landing/build_site.py` depuis des fichiers Markdown `landing/content/blog/*.md`
(front-matter TOML `+++` + corps Markdown rendu via `markdown-it-py`, déjà tiré par
`myst-parser`). Sortie : `landing/blog/index.html`, `landing/blog/<slug>.html`, flux RSS
`landing/feed.xml`. Styles Markdown prédéfinis au thème Catppuccin du site (classe `.post-body`).

**Conventions d'écriture des articles** (demande user) :
- **Anglais uniquement.**
- Ton **humain, détendu, façon Korben** (le blogueur tech) — pas guindé.
- **Interdiction des tirets cadratin `—`** (« font très IA ») : utiliser des virgules / parenthèses.
- **TL;DR en 3 points** au début de chaque article (champ `summary = [...]` du front-matter).
- RSS = **résumé (le TL;DR) + lien** vers l'article (pas l'article complet).

**Signature (byline) par auteur** :
- Les articles écrits côté utilisateur sont signés **« Pinpanicaille »** (son vrai pseudo ;
  il compte changer son pseudo GitHub bientôt, surveiller si ça doit être mis à jour).
- Si **Frosoore** écrit un article, il signe **en son propre nom** (« Frosoore »), pas Pinpanicaille.

**Guide d'écriture complet (réutilisable) dans le repo** : `landing/content/blog/README.md`
— template de front-matter, règles de style, table du Markdown supporté, étapes de preview/publish.
C'est LE document à relire avant d'écrire un nouvel article (le présent fichier mémoire n'est qu'un
pointeur + les règles clés). Template minimal :

```
+++
title = "..."
slug = "..."            # URL = blog/<slug>.html
date = "YYYY-MM-DD"
author = "Pinpanicaille"
summary = ["point 1", "point 2", "point 3"]   # TL;DR 3 points
+++
## Section
corps en Markdown (commence à ##, le titre vient du front-matter)
```

Voir aussi [[project-status-doc-convention]] (AXIOM_STATUS.md + dev-updates) : le blog est la
couche « prose/news », la page Dev reste le changelog terse.
