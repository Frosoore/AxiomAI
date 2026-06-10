# TODO — feature-packaging-pip

Rendre le moteur `axiom/` pip-installable **sans le sortir du repo** (TICKET-009 résolu en version légère),
plus un utilitaire d'export PyPI et un objet `axiom.help`.

- [x] `pyproject.toml` à la racine : package `axiomai-engine`, n'emballe QUE `axiom/`, deps moteur (zéro Qt),
      entry point console `axiom = axiom.cli.main:main`, version dynamique lue dans `axiom/__init__.py`
- [x] `axiom/__init__.py` : ajouter `__version__` (source de vérité unique)
- [x] `axiom/__init__.py` : objet `axiom.help` (affichable ET appelable — `axiom.help` / `axiom.help()` / `print(axiom.help)`)
- [x] `export_engine.py` (racine) : clone `axiom/` + pyproject + LICENSE + README librairie dans un dossier
      prêt pour PyPI ; bump de version auto (`--bump patch|minor|major` / `--set-version`) ; garde anti-import
      app (ui/workers/core/database/PySide6) ; `--build` (sdist+wheel) ; récap des étapes twine
- [x] Tests `tests/test_packaging.py` (help, export, garde, bump) — 15 tests
- [x] Vérification réelle : wheel construite et inspectée (uniquement `axiom/`), installée dans un venv
      vierge, `import axiom` + `axiom.help` + `axiom --help` OK ; export autonome reconstruit
- [x] Doc : DOC.md léger + maintenance/README.md (ligne) + PENDING/DONE (TICKET-009) + memory MAJ

- [x] **Publication PyPI réelle : FAIT le 2026-06-10** — `axiomai-engine` 0.1.0 en ligne
      (https://pypi.org/project/axiomai-engine/), vérifiée par install externe.
      (Péripéties de nommage : `axiom-engine`/`axiom` pris, `axiomai` refusé par la règle de
      similarité PyPI vs `axiom-ai` → nom final `axiomai-engine`, import inchangé `axiom`.)
- [x] Doc générale à jour : `ARCHITECTURE.md` (section Packaging & distribution) +
      `README.md` (badge PyPI, section librairie, features récentes)
