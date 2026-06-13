# DOC — TICKET-062 item 1 : univers par défaut au premier lancement

## Objectif

Qu'un bêta-testeur qui lance Axiom AI pour la première fois trouve un univers
jouable (Myria) dans son Hub, sans aucune manipulation.

## Fonctionnement

- Le repo embarque l'univers en source Universe-as-Code : `universes/Myria/`.
- Au démarrage (`main.py`), `core/bundled_universes.py::install_bundled_universes()`
  copie chaque dossier de `universes/` contenant un `universe.toml` vers la
  bibliothèque `~/AxiomAI/universes/`, puis le Hub fait le reste (la découverte
  compile les dossiers source à la volée).
- **Une seule offre par univers, à vie** : marqueur
  `~/.config/AxiomAI/installed_bundles.txt`. Supprimer l'univers de sa
  bibliothèque est respecté. Un dossier homonyme existant n'est jamais écrasé.
- Le cache `.axiom-cache/` n'est pas copié (recompilé localement) ; `.git`
  non plus.

## Ajouter un futur univers embarqué

Déposer son dossier source dans `universes/` (avec `universe.toml`) et
l'exclure du `.gitignore` comme Myria — rien d'autre à câbler : les
utilisateurs existants le recevront à leur prochain lancement (leur marqueur
ne contient pas encore son nom).

## Limite connue (acceptée pour la bêta)

Les mises à jour du contenu de Myria dans le repo ne sont pas propagées aux
bibliothèques déjà installées (le marqueur bloque toute ré-offre). Si besoin
plus tard : versionner le bundle (hash dans le marqueur) + proposer la mise à
jour quand la copie locale n'a pas divergé.
