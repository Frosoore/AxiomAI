# DOC — Site de documentation de la lib `axiomai-engine`

**Objectif :** documentation publique de la librairie (façon devguide.python.org / PySide6),
hébergée sur GitHub Pages, **EN + FR** avec sélecteur de langue.

## Commandes utiles (depuis la racine du repo)

```bash
# Construire et prévisualiser
.venv/bin/sphinx-build -b html docs docs/_build/html/en                  # anglais
.venv/bin/sphinx-build -b html -D language=fr docs docs/_build/html/fr   # français
xdg-open docs/_build/html/en/index.html

# Après modification du contenu EN : rafraîchir les catalogues de traduction
.venv/bin/sphinx-build -b gettext docs docs/_build/gettext
cd docs && ../.venv/bin/sphinx-intl update -p _build/gettext -l fr

# Traduire = remplir les msgstr dans docs/locales/fr/LC_MESSAGES/*.po
# (vide = fallback anglais automatique). Nouvelle langue : -l es, -l de, …
```

## Architecture

- `docs/conf.py` — config Sphinx (Furo, MyST, autodoc avec deps lourdes **mockées**, gettext).
- Pages rédigées en **Markdown** ; référence API auto-générée depuis les **docstrings EN**
  (toute docstring publique du moteur doit désormais être écrite **en anglais**).
- `docs/locales/fr/LC_MESSAGES/*.po` — traductions FR (gettext). Non traduit → anglais.
- `docs/_templates/sidebar/language.html` — sélecteur EN/FR (bascule /en/↔/fr/ dans l'URL).
- `.github/workflows/docs.yml` — publie `https://frosoore.github.io/AxiomAI/` (racine →
  `/en/`) à chaque push sur `main`. **Prérequis une fois : Settings → Pages → Source =
  « GitHub Actions ».**

## Règles désormais

1. Nouvelle API publique ⇒ docstring **en anglais** (style Google : Args/Returns/Raises).
2. Nouveau module public ⇒ l'ajouter dans la page `docs/api/*.md` correspondante.
3. Modif des pages rédigées ⇒ refaire l'extraction gettext + compléter le `.po` FR.
4. Le build CI est strict (`-W`) : un warning Sphinx casse le déploiement — builder en local avant.
