---
name: project-engine-split-strategy
description: Stratégie moteur/app d'AxiomAI — mono-repo CONSERVÉ mais moteur pip-installable depuis le 2026-06-10 (pyproject racine, TICKET-009 clos sans split physique)
metadata:
  type: project
---

**Décision (2026-06-10, remplace celle du 2026-06-04) : le moteur est pip-installable SANS split
physique.** On reste en **mono-repo** (séparation logique `axiom/` = moteur headless zéro Qt ;
`ui/`+`workers/`+`core/` = app), mais un **`pyproject.toml` à la racine** déclare le package
**`axiomai-engine`** qui n'emballe **que** `axiom/` (liste d'inclusion explicite). TICKET-009 est
**clos** (DONE.md) — le « split physique » (déplacer `axiom/` sous `axiom-engine/`) s'est avéré
inutile pour l'objectif distribution.

**Why:** l'utilisateur veut distribuer le moteur (`pip install git+<repo>`, plus tard PyPI) tout en
gardant l'app dans le même repo comme vitrine du moteur (dev simultané app+moteur). Le pyproject
racine donne la distribution sans le churn de merge d'un déplacement (dev parallèle Gemini toujours
actif). Tout le portage features app→moteur était déjà fini (B4, table « non migré » vide).

**Ce qui est en place (étape `maintenance/feature-packaging-pip/`) :**
- `pyproject.toml` racine : deps moteur zéro Qt, console_script `axiom = axiom.cli.main:main`,
  version dynamique lue dans `axiom/__init__.py::__version__` (source de vérité unique, 0.1.0).
- `axiom.help` : guide REPL intégré (affichable/appelable, aucun import lourd).
- `export_engine.py` (racine, hors package) : export PyPI-ready dans `dist/axiomai-engine/`
  (`--bump patch|minor|major`, `--set-version`, `--build`, garde anti-import app).
- 15 tests `tests/test_packaging.py` ; vérifié en venv vierge (wheel = uniquement `axiom/`).

**How to apply:**
- Règle inchangée : une seule source de vérité par feature, logique dans `axiom/`, worker Qt =
  coquille fine. **Jamais d'import `axiom/` → `ui`/`workers`/`core`/`database`/PySide6** — c'est
  désormais vérifié mécaniquement (garde de `export_engine.py` + test `test_check_headless_engine_is_clean`).
- Nouvelle dépendance moteur ⇒ l'ajouter dans `pyproject.toml` (deps du package) ET `requirements.txt` (app).
- Publier : `python export_engine.py --bump <part> --build` puis `twine upload` (compte PyPI requis).
  Nom PyPI = **`axiomai-engine`** (`axiom-engine`/`axiom` pris, `axiomai` refusé « too similar »
  vs `axiom-ai` — la règle de similarité PyPI ignore les tirets et ne se teste qu'à l'upload) ;
  le nom d'import reste `axiom`. **0.1.0 PUBLIÉE le 2026-06-10** et vérifiée depuis l'extérieur
  (`pip install axiomai-engine` → import + CLI OK). README + ARCHITECTURE.md documentent le packaging.
- Voir [[feedback-user-handles-git]] (l'utilisateur gère ses commits).
