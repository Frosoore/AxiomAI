# DOC — feature-packaging-pip

## Objectif

Le moteur `axiom/` devient un **package Python installable** (`pip install`) **sans quitter le repo**
(mono-repo conservé, décision 2026-06-10 — remplace le « split physique » du TICKET-009).

## Ce qui est en place

- **`pyproject.toml`** (racine) : package distribué sous le nom **`axiomai-engine`**, qui n'emballe
  **que** le dossier `axiom/` (l'app Qt — `ui/`, `workers/`, `core/` — n'est jamais embarquée).
  Installe la commande console `axiom` (le CLI existant). Version lue dynamiquement dans
  `axiom/__init__.py::__version__` (source de vérité unique).
  - Installation depuis le repo : `pip install git+<url-du-repo>` ou `pip install .` en local.
- **`axiom.help`** : objet d'aide intégré. Dans n'importe quel REPL (Thonny inclus) :
  `import axiom` puis `axiom.help` (ou `axiom.help()`) affiche un guide de démarrage rapide.
- **`export_engine.py`** (racine) : utilitaire qui clone le moteur dans un dossier prêt à publier
  sur PyPI. `python export_engine.py --help` pour les options :
  - bump de version automatique (`--bump patch|minor|major`, `--set-version X.Y.Z`) — réécrit
    `axiom/__init__.py` dans le repo puis exporte ;
  - garde anti-fuite : refuse d'exporter si un fichier importe l'app (PySide6, `ui`, `workers`, …) ;
  - `--build` : construit sdist + wheel dans le dossier exporté ;
  - affiche les commandes `twine` à lancer pour publier.

## Décisions

- **Pas de déplacement de `axiom/`** : un `pyproject.toml` racine avec une liste d'inclusion
  explicite suffit — zéro churn de merge avec la branche Gemini.
- Le `README.md` racine reste celui de l'app ; l'export écrit un README spécifique librairie.
- `help` n'est pas dans `__all__` (pour ne pas masquer le `help()` natif en cas de
  `from axiom import *`).
