# DOC — TICKET-054 : séparation i18n moteur / GUI

## Objectif
Le moteur (`axiom/`, lib pip `axiomai-engine`) ne doit **rien traduire** : il émet des données et des
clés stables, en anglais par défaut. Toute la localisation multilingue vit côté frontend.

## Où vit quoi (après)
- **Moteur `axiom/`** : `axiom/textfmt.py::fmt_num` (langue-neutre) ; `TimeSystem.get_time_components`
  (données + clé de phase) ; `TimeSystem.get_time_string` (anglais par défaut). **Aucun** catalogue.
- **App** : `core/localization.py` (`tr`, `SUPPORTED_LANGUAGES`, `canonical_verbosity`,
  `format_time`, `compute_coverage`, ré-export `fmt_num`) + `core/locales/<lang>.toml` (10 langues).

## Règles pour la suite
- **Ajouter une clé de traduction** = éditer `core/locales/*.toml` (plus jamais dans `axiom/`).
- **Le moteur ne doit jamais importer `core.localization`** (contrat headless : le moteur ne dépend
  pas de l'app). S'il doit produire un texte, c'est de l'anglais/des clés.
- **Afficher du temps dans le GUI** : `core.localization.format_time(time_system, minutes)` —
  ne pas appeler `get_time_string` (qui est le rendu anglais du moteur).

## Outils
- `python tools/i18n_check.py [--show-keys] [-r fr] [--strict]` : audit de couverture des 10 langues.
